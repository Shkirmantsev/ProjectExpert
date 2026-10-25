"""Role-aware pinned Qwen GGUF embeddings over a local llama.cpp server."""
from __future__ import annotations
import base64
import mimetypes
import json
import math
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from pi_platform.ports.retrieval.embedding_model import EmbeddingModelPort, EmbeddingModelError, EmbeddingRequest, EmbeddingRole
from pi_platform.ports.retrieval.embedding_profile import EmbeddingProfile
from .gguf_artifacts import MODEL_ID, REVISION, SHA256, MODEL_ALIAS, RUNTIME_VERSION
from .qwen3_embedding_model import QUERY_INSTRUCTION
from .gguf_artifacts import GEMMA_MODEL_ID, GEMMA_REVISION, GEMMA_SHA256, GEMMA_PROJECTOR_SHA256, GEMMA_MODEL_ALIAS
from .embeddinggemma2_embedding_model import TASK_PROMPTS, _format_document_text
from pi_platform.ports.retrieval.embedding_model import EmbeddingTask

GGUF_PROFILE = EmbeddingProfile(
    provider='llama.cpp-qwen3-q4_k_m', model_id=MODEL_ID, model_revision=REVISION,
    modality='text', output_dimension=1024, normalization='l2',
    instruction_profile='project-expert-qwen-query-v2',
    tokenizer_id=f'{MODEL_ID}@{REVISION}',
    strategy_version=f'llama.cpp-{RUNTIME_VERSION}-q4_k_m-last-{SHA256}',
)


GEMMA_GGUF_PROFILE = EmbeddingProfile(
    provider='llama.cpp-embeddinggemma2-q8_0', model_id=GEMMA_MODEL_ID, model_revision=GEMMA_REVISION,
    modality='text-image', output_dimension=512, normalization='l2',
    instruction_profile='gemma-task-search-document-v2', tokenizer_id=f'{GEMMA_MODEL_ID}@{GEMMA_REVISION}',
    strategy_version=f'llama.cpp-{RUNTIME_VERSION}-q8_0-mean-mrl512-{GEMMA_SHA256}-{GEMMA_PROJECTOR_SHA256}',
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Runtime redirects are not permitted")


class LlamaCppEmbeddingModel(EmbeddingModelPort):
    def __init__(self, *, device='cpu', endpoint=None, key_file=None, timeout=120, model_alias="qwen-gguf"):
        if model_alias not in {"qwen-gguf", "gemma-gguf"}:
            raise EmbeddingModelError("Unknown GGUF profile")
        self.is_gemma = model_alias == "gemma-gguf"
        self.runtime_alias = GEMMA_MODEL_ALIAS if self.is_gemma else MODEL_ALIAS
        self._profile = GEMMA_GGUF_PROFILE if self.is_gemma else GGUF_PROFILE
        if device not in {'cpu', 'cuda', 'vulkan', 'auto'}:
            raise EmbeddingModelError('GGUF supports cpu, cuda or vulkan')
        self.device = device
        self.endpoint = (endpoint or os.environ.get('PI_LLAMA_ENDPOINT', 'http://127.0.0.1:8769')).rstrip('/')
        parsed = urllib.parse.urlparse(self.endpoint)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise EmbeddingModelError('PI_LLAMA_ENDPOINT must be an HTTP(S) endpoint without credentials or query')
        self.key_file = key_file or os.environ.get('PI_LLAMA_API_KEY_FILE', '/models/llama-api-key')
        self.timeout = timeout
        self._calls = 0
        self._ready = False

    def _request(self, path, payload=None):
        try:
            token = Path(self.key_file).read_text().strip()
            if len(token) < 32:
                raise ValueError('invalid runtime key')
            body = None if payload is None else json.dumps(payload).encode()
            req = urllib.request.Request(self.endpoint + path, data=body,
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+token})
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError('embedding response exceeds size limit')
                return json.loads(raw)
        except (OSError, ValueError) as exc:
            # Never include headers, tokens, remote error bodies or query text.
            self._ready = False
            raise EmbeddingModelError(f'GGUF runtime unavailable or invalid ({type(exc).__name__}); start the selected accelerator deployment') from exc

    def embed_requests(self, requests):
        if not self.is_gemma and any(request.image_path for request in requests):
            raise EmbeddingModelError("Qwen GGUF is text-only; select Gemma for images")
        if not requests:
            return []
        models = self._request('/v1/models')
        try:
            identities = {item['id'] for item in models['data']}
        except (KeyError, TypeError) as exc:
            self._ready = False
            raise EmbeddingModelError('Invalid GGUF model identity response') from exc
        if self.runtime_alias not in identities:
            self._ready = False
            raise EmbeddingModelError('GGUF runtime model identity differs from the selected pinned GGUF profile')
        output = []
        # Bound one request per sequence: avoids server context/batch overflow
        # and preserves exact document order for mixed-role inputs.
        for request in requests:
            text = request.text
            if self.is_gemma:
                text = (TASK_PROMPTS.get(request.task, TASK_PROMPTS[EmbeddingTask.SEARCH]) + text
                        if request.role == EmbeddingRole.QUERY else _format_document_text(text, request.title))
            elif request.role == EmbeddingRole.QUERY:
                text = f'Instruct: {QUERY_INSTRUCTION}\nQuery: {text}'
            if request.image_path:
                path = Path(request.image_path)
                if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                    raise EmbeddingModelError('Image is missing or exceeds the 16 MiB GGUF input limit')
                mime = mimetypes.guess_type(path.name)[0] or 'image/png'
                # Images travel as bytes, never paths the remote runtime must resolve.
                uri = 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
                text = {'content': [{'type':'text', 'text':text}, {'type':'image_url', 'image_url':{'url':uri}}]}
            result = self._request('/v1/embeddings', {'model': self.runtime_alias, 'input': [text], 'encoding_format': 'float'})
            try:
                data = result['data']
                if len(data) != 1 or data[0]['index'] != 0:
                    raise ValueError('invalid response cardinality')
                vector = data[0]['embedding']
                if len(vector) != (768 if self.is_gemma else 1024) or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
                    raise ValueError('invalid embedding values or dimensions')
                vector = vector[:self.dimension()]
                norm = math.sqrt(sum(x*x for x in vector))
                if not math.isfinite(norm) or norm <= 0:
                    raise ValueError('invalid embedding norm')
                output.append([x/norm for x in vector])
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                self._ready = False
                raise EmbeddingModelError('Invalid GGUF embedding response') from exc
            self._calls += 1
        self._ready = True
        return output

    def embed_request(self, request):
        return self.embed_requests([request])[0]

    def embed(self, text):
        return self.embed_request(EmbeddingRequest(text, EmbeddingRole.DOCUMENT))

    def embed_batch(self, texts):
        return self.embed_requests([EmbeddingRequest(text, EmbeddingRole.DOCUMENT) for text in texts])

    def dimension(self): return self._profile.output_dimension
    def model_version(self): return self._profile.identity()
    def license_id(self): return 'Apache-2.0'
    def profile(self): return self._profile
    def stats(self):
        return {'calls': self._calls, 'backend': 'llama.cpp', 'real_binding': '1' if self._ready else '0', 'requested_device': self.device}
