"""Describe effective embedding execution separately from requested settings."""
import os
from urllib.parse import urlparse


def embedding_execution_status(model):
    stats = model.stats()
    requested = stats.get('requested_device', 'unknown')
    actual = stats.get('effective_device')
    if actual:
        mode = 'CPU' if actual == 'cpu' else 'GPU'
        return dict(mode=mode, backend=actual, requested_device=requested,
                    source='loaded embedding adapter', reason=stats.get('device_selection_reason', 'Loaded model device'))
    if stats.get('backend') == 'llama.cpp':
        backend = os.environ.get('PI_INFERENCE_BACKEND', '')
        source = 'selected deployment profile'
        # Older managed kits already set PI_EMBEDDING_DEVICE in the selected
        # CPU/CUDA/Vulkan overlay. A later UI Auto override does not change
        # that serving-container environment. Never infer arbitrary remotes.
        if not backend and urlparse(os.environ.get('PI_LLAMA_ENDPOINT', '')).hostname == 'embeddings':
            backend = os.environ.get('PI_EMBEDDING_DEVICE', '')
            source = 'selected managed backend (legacy kit environment)'
        if backend in {'cpu', 'cuda', 'vulkan'}:
            return dict(mode='CPU' if backend == 'cpu' else 'Hybrid', backend=backend,
                        requested_device=requested, device='' if backend == 'cpu' else os.environ.get('PI_GPU_DEVICE', ''),
                        source=source,
                        reason=('CPU-only embedding runtime.' if backend == 'cpu' else
                                'GPU embedding backend with CPU multimodal projector; memory-fit may also offload model work to CPU. This describes the deployment profile, not a measured GPU layer count.'))
    return dict(mode='Unknown', backend=stats.get('backend', 'unknown'), requested_device=requested,
                source='no effective device evidence', reason='The remote runtime does not report its device. Update the deployment kit to publish the selected backend; Auto is not an actual device.')
