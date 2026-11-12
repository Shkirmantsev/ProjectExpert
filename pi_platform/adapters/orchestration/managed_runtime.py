"""Apply explicit UI choices to the bounded embedding sidecar controller."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
import time
import urllib.error
import urllib.request

from pi_platform.core.inference.backend import BackendCandidate
from pi_platform.core.inference.benchmark import BENCHMARK_TEXTS, query_workload_identity
from pi_platform.core.inference.stage_resources import StageResourceEvidence, StageResourcePlanner
from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_MODEL_ALIAS
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
    if changed:
        saved={**saved, 'stage_resources': {'stage':'query_embedding',
            'scope':'live-controller-comparison', 'runtime_generation':state['generation'],
            'decision':None, 'evidence':[], 'reason':'runtime generation changed; evidence invalidated'}}
    return {**saved, 'mode':('CPU' if backend == 'cpu' else 'Hybrid') if state['ready'] else 'not ready',
            'backend':backend, 'device':state['device'], 'source':'live managed embedding process',
            'reason':('Runtime restarted or changed; Apply verifies your saved selection again.' if changed
                      else saved.get('reason', 'Healthy embedding process'))}


def _normalized_probe(vector):
    if (not isinstance(vector, (list, tuple)) or len(vector) != 512
        or any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in vector)):
        raise ValueError('invalid fixed-probe vector')
    norm=math.sqrt(sum(value*value for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError('invalid fixed-probe norm')
    return [value/norm for value in vector]


def _probe_parity(cpu_vectors, gpu_vectors):
    """Numerical and same-probe ranking check, not retrieval relevance proof."""
    try:
        if (not isinstance(cpu_vectors, (list, tuple)) or not isinstance(gpu_vectors, (list, tuple))
            or len(cpu_vectors) != len(BENCHMARK_TEXTS) or len(gpu_vectors) != len(BENCHMARK_TEXTS)):
            raise ValueError('missing fixed probes')
        cpu=[_normalized_probe(vector) for vector in cpu_vectors]
        gpu=[_normalized_probe(vector) for vector in gpu_vectors]
    except ValueError:
        return {'validated':False, 'reason':'missing or invalid fixed-probe numerical parity evidence'}
    cosine=lambda left,right:sum(a*b for a,b in zip(left,right))
    minimum=min(cosine(left,right) for left,right in zip(cpu,gpu))
    maximum=max(abs(a-b) for left,right in zip(cpu,gpu) for a,b in zip(left,right))
    # Require each CPU query's corresponding GPU probe to remain a top match,
    # allowing ties among near-identical fixed probes. These are public fixture
    # queries, not a labeled document corpus or a downstream relevance suite.
    ranking=all(cosine(cpu[index],gpu[index]) + 0.01 >= max(cosine(cpu[index],other) for other in gpu)
                for index in range(len(cpu)))
    valid=minimum >= 0.999 and maximum <= 0.01 and ranking
    return {'validated':valid, 'reason':'fixed-probe numerical and ranking checks passed' if valid
            else 'fixed-probe numerical or ranking parity failed',
            'minimum_cosine':minimum, 'maximum_absolute_difference':maximum,
            'same_probe_ranking':ranking, 'minimum_cosine_required':0.999,
            'maximum_absolute_difference_allowed':0.01}


def _measure():
    """Retain actual repeated query-corpus throughput after warmup."""
    endpoint=os.environ['PI_LLAMA_ENDPOINT'].rstrip('/')+'/v1/embeddings'
    latencies=[]
    round_elapsed=[]
    elapsed=0.0
    probes={}
    for index in range(5+len(BENCHMARK_TEXTS)*3):
        text='task: search result | query: '+BENCHMARK_TEXTS[index % len(BENCHMARK_TEXTS)]
        start=time.perf_counter()
        response=request_json(endpoint, 'POST', {'model': GEMMA_MODEL_ALIAS, 'input':[text],
                                                 'encoding_format':'float'})
        duration=time.perf_counter()-start
        data=response.get('data')
        vector=data[0].get('embedding') if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict) else None
        if (not isinstance(vector, list) or len(vector) != 768
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in vector)
            or sum(value*value for value in vector) <= 0 or duration <= 0):
            raise RuntimeError('Embedding benchmark returned an invalid vector or duration')
        if index >= 5:
            try:
                probes[index % len(BENCHMARK_TEXTS)]=_normalized_probe(vector[:512])
            except ValueError as exc:
                raise RuntimeError('Embedding benchmark returned an invalid projected vector') from exc
            latencies.append(duration*1000)
            elapsed += duration
            if (index-5+1) % len(BENCHMARK_TEXTS) == 0:
                round_elapsed.append(elapsed)
                elapsed=0.0
    return {'median_ms':statistics.median(latencies), 'latencies_ms':latencies,
            'completed_per_second':[len(BENCHMARK_TEXTS)/elapsed for elapsed in round_elapsed],
            'workload_identity':query_workload_identity(), 'stage':'query_embedding',
            'probe_vectors':[probes[index] for index in range(len(BENCHMARK_TEXTS))]}


def apply_selection(cache, model, requested, *, transport=transport, measure=_measure):
    if model != 'gemma' or not os.environ.get('PI_RUNTIME_CONTROL_URL'):
        return None
    state=transport('GET')
    cached=load_json(Path(cache)/'managed-runtime-state.json')
    cached_stage=cached.get('stage_resources') or {}
    cached_parity_usable=(not cached_stage.get('evidence') or cached.get('backend') == 'cpu'
                          or (cached_stage.get('fixed_probe_parity') or {}).get('validated') is True)
    if (cached_parity_usable and cached.get('requested_device') == requested and cached.get('generation') == state['generation']
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
    query_evidence=[]
    stage_decision=None
    probes_by_backend={}
    parity_summary=None
    # Comparison-scoped identity: a controller restart invalidates the cache.
    # This is not an immutable image/driver digest or cross-run evidence key.
    comparison_identity=hashlib.sha256(json.dumps({"controller":os.environ.get("PI_RUNTIME_CONTROL_URL"),
        "generation":state["generation"], "model":GEMMA_MODEL_ALIAS}, sort_keys=True).encode()).hexdigest()
    def collect(backend):
        result=measure()
        if not isinstance(result, dict):
            measurements[backend]=result
            return
        measurements[backend]=result["median_ms"]
        probes_by_backend[backend]=result.get("probe_vectors")
        query_evidence.append(StageResourceEvidence(
            stage=result["stage"], backend=backend, runtime_identity=comparison_identity,
            workload_identity=result["workload_identity"],
            completed_per_second=tuple(result["completed_per_second"]),
            quality_validated=backend == "cpu",
            quality_reason="GPU fixed-probe parity has not been checked" if backend != "cpu" else "",
        ))
    if requested == 'auto' and profile.backend != 'cpu':
        transport('PUT', {'device':'none', 'fit_target':192})
        try:
            collect('cpu')
        except RuntimeError as exc:
            raise RuntimeError(f'CPU query benchmark baseline failed; Auto cannot compare backends: {exc}') from exc
        try:
            transport('PUT', {'device':profile.device, 'fit_target':profile.fit_target_mib})
            collect(backend)
            if len(query_evidence) == 2:
                parity_summary=_probe_parity(probes_by_backend.get('cpu'), probes_by_backend.get(backend))
                query_evidence=[replace(item, quality_validated=parity_summary['validated'],
                    quality_reason=parity_summary['reason']) if item.backend != 'cpu' else item
                    for item in query_evidence]
                stage_decision=StageResourcePlanner().select('query_embedding', query_evidence,
                    runtime_identity=comparison_identity, workload_identity=query_workload_identity())
                selected=select_profile([cpu, gpu], prefer=(stage_decision.backend,))
                profile=replace(selected, reason=stage_decision.reason)
            else:
                # Existing scalar-injected callers keep their legacy policy;
                # never manufacture repeated samples from a single median.
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
        rejected=list(profile.rejected), measurements_ms=measurements,
        execution_shape='cpu' if actual == 'cpu' else 'gpu-backbone-cpu-projector',
        stage_resources={
            'stage':'query_embedding', 'scope':'live-controller-comparison',
            'runtime_generation':state['generation'],
            'decision':asdict(stage_decision) if stage_decision is not None else None,
            'evidence':[asdict(item) for item in query_evidence],
            'fixed_probe_parity':parity_summary,
        })
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
