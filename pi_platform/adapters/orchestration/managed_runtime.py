"""Apply explicit UI choices to the bounded embedding sidecar controller."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import statistics
import tempfile
import time
import urllib.error
import urllib.request

from pi_platform.core.inference.backend import BackendCandidate
from pi_platform.core.inference.benchmark import BENCHMARK_TEXTS
from pi_platform.core.inference.profile import select_profile


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def save_json(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary=tempfile.mkstemp(prefix='.runtime-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_json(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def selection_path(repo):
    return Path(repo)/'.project-intelligence-cache'/'runtime-selection.json'


def request_json(url, method='GET', body=None, timeout=400):
    key_path=os.environ.get('PI_LLAMA_API_KEY_FILE', '')
    key=Path(key_path).read_text().strip() if key_path else ''
    headers={'Content-Type':'application/json'}
    if key:
        headers['Authorization']='Bearer '+key
    request=urllib.request.Request(url, method=method, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            return json.loads(response.read(1024*1024))
    except urllib.error.HTTPError as error:
        # Controller diagnostics are bounded and contain no credentials.
        detail=''
        if url.endswith('/runtime'):
            try:
                detail=json.loads(error.read(4096)).get('error', '')
            except (ValueError, AttributeError):
                pass
        raise RuntimeError(f'Embedding runtime HTTP {error.code}. {detail}') from None
    except (OSError, ValueError):
        raise RuntimeError('Embedding controller unavailable. Upgrade the deployment kit and check embeddings logs.') from None


def transport(method, body=None):
    base=os.environ.get('PI_RUNTIME_CONTROL_URL', '').rstrip('/')
    return request_json(base+'/runtime', method, body, timeout=400 if method == 'PUT' else 25)


def observed_execution(saved):
    """Read current child state; never label a historical profile as live."""
    try:
        state=transport('GET')
    except RuntimeError:
        return {**saved, 'mode':'Unknown', 'source':'managed controller unreachable',
                'reason':'Cannot confirm the live embedding process. Check embeddings logs.'}
    backend='cpu' if state['device'] == 'none' else state['backend']
    changed=state['generation'] != saved.get('generation')
    return {**saved, 'mode':('CPU' if backend == 'cpu' else 'Hybrid') if state['ready'] else 'not ready',
            'backend':backend, 'device':state['device'], 'source':'live managed embedding process',
            'reason':('Runtime restarted or changed; Apply verifies your saved selection again.' if changed
                      else saved.get('reason', 'Healthy embedding process'))}


def _measure():
    endpoint=os.environ['PI_LLAMA_ENDPOINT'].rstrip('/')+'/v1/embeddings'
    latencies=[]
    for index in range(5+len(BENCHMARK_TEXTS)*3):
        start=time.perf_counter()
        response=request_json(endpoint, 'POST', {'input':BENCHMARK_TEXTS[index % len(BENCHMARK_TEXTS)]})
        if not response.get('data'):
            raise RuntimeError('Embedding benchmark returned no vectors')
        if index >= 5:
            latencies.append((time.perf_counter()-start)*1000)
    return statistics.median(latencies)


def apply_selection(cache, model, requested, *, transport=transport, measure=_measure):
    if model != 'gemma' or not os.environ.get('PI_RUNTIME_CONTROL_URL'):
        return None
    state=transport('GET')
    cached=load_json(Path(cache)/'managed-runtime-state.json')
    if (cached.get('requested_device') == requested and cached.get('generation') == state['generation']
            and cached.get('device') == state['device'] and state['ready']):
        return cached
    backend=state['backend']
    cpu=BackendCandidate('cpu', True, 0, '')
    gpu=BackendCandidate(backend, True, 0, state.get('devices', ''))
    profile=select_profile([cpu, gpu], prefer=(backend, 'cpu') if requested == 'auto' else (requested,))
    if requested not in ('auto', 'cpu') and profile.backend != requested:
        raise RuntimeError(f'Requested GPU backend {requested} has no usable device in this container. '
                           'Enable GPU passthrough and install the matching runtime, or select CPU/Auto.')
    measurements={}
    if requested == 'auto' and profile.backend != 'cpu':
        transport('PUT', {'device':'none', 'fit_target':192})
        measurements['cpu']=measure()
        try:
            transport('PUT', {'device':profile.device, 'fit_target':profile.fit_target_mib})
            measurements[backend]=measure()
            profile=select_profile([cpu, gpu], measurements=measurements)
        except RuntimeError:
            profile=select_profile([cpu], prefer=('cpu',))
    state=transport('PUT', {'device':profile.device or 'none', 'fit_target':profile.fit_target_mib})
    if not state['ready'] or state['device'] != (profile.device or 'none'):
        raise RuntimeError('Embedding controller did not confirm the requested device')
    actual='cpu' if state['device'] == 'none' else state['backend']
    result=dict(mode='CPU' if actual == 'cpu' else 'Hybrid', backend=actual,
        device=state['device'], requested_device=requested, generation=state['generation'],
        source='live managed embedding process', reason=profile.reason,
        rejected=list(profile.rejected), measurements_ms=measurements)
    save_json(Path(cache)/'managed-runtime-state.json', result)
    return result


def capabilities():
    models=[]
    if os.environ.get('PI_LLAMA_ENDPOINT'):
        models.append(dict(value='gemma', label='EmbeddingGemma 2 · GGUF Q8_0 (managed runtime)'))
    if importlib.util.find_spec('torch') and importlib.util.find_spec('transformers'):
        models.append(dict(value='gemma-torch', label='EmbeddingGemma 2 · native Transformers (downloads separate weights)'))
    managed=bool(os.environ.get('PI_RUNTIME_CONTROL_URL'))
    devices={'gemma':['auto','cpu','vulkan','cuda'], 'gemma-torch':['auto','cpu']}
    if any(model['value'] == 'gemma-torch' for model in models):
        import torch
        if torch.cuda.is_available():
            devices['gemma-torch'].append('cuda')
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            devices['gemma-torch'].append('mps')
    return dict(models=models, managed_control=managed,
        devices=devices,
        message=('Apply restarts the embedding process, verifies its health and rebuilds the index. '
                 'Auto compares CPU and available GPU latency; GPU uses a CPU projector (Hybrid).'
                 if managed else 'Remote runtime has no live controller. Change its host deployment to switch hardware, '
                 'or upgrade the managed deployment kit. Native Transformers uses the selected device directly.'))
