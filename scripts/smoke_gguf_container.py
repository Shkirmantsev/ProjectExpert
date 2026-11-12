#!/usr/bin/env python3
"""Real optional-runtime contract on CPU; does not certify physical GPUs."""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pi_platform.cli.gguf_setup import prepare
from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_MODEL_ALIAS, GEMMA_PROJECTOR_FILENAME
from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel
from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole, EmbeddingModelError
from pi_platform.core.inference.launch import build_server_argv


def exercise(adapter, *, backend='cpu', device=None):
    deadline = time.monotonic()+240
    while True:
        try:
            vectors = adapter.embed_requests([EmbeddingRequest('invoice billing',EmbeddingRole.QUERY),
                EmbeddingRequest('Invoices are reconciled by billing',EmbeddingRole.DOCUMENT)])
            break
        except EmbeddingModelError:
            if time.monotonic() >= deadline: raise
            time.sleep(2)
    assert all(len(v)==adapter.dimension() and math.isclose(sum(x*x for x in v),1,abs_tol=1e-5) for v in vectors)
    wide = 'ledger ' * 1500
    from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import _format_document_text
    tokens = adapter._request('/tokenize', {'content': _format_document_text(wide, None)})['tokens']
    assert 1049 < len(tokens) < 4096, 'Wide-input fixture must exercise the former batch limit'
    vector = adapter.embed_request(EmbeddingRequest(wide, EmbeddingRole.DOCUMENT))
    assert len(vector) == adapter.dimension() and math.isclose(sum(x*x for x in vector), 1, abs_tol=1e-5)
    print(f'PASS: {len(tokens)}-token document with shipped runtime capacity defaults')
    # A real PNG fixture without adding host Pillow as a prerequisite.
    import struct, zlib
    def chunk(tag, data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    def png(rgb):
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,2,0,0,0))
                +chunk(b'IDAT',zlib.compress((b'\x00'+bytes(rgb)*64)*64))+chunk(b'IEND',b''))
    import tempfile
    with tempfile.TemporaryDirectory() as raw:
        image_path=Path(raw)/'square.png'
        image_path.write_bytes(png((255,0,0)))
        red=adapter.embed_request(EmbeddingRequest('colored square',EmbeddingRole.DOCUMENT,image_path=str(image_path)))
        image_path.write_bytes(png((0,0,255)))
        blue=adapter.embed_request(EmbeddingRequest('colored square',EmbeddingRole.DOCUMENT,image_path=str(image_path)))
        assert len(red)==512 and math.isclose(sum(x*x for x in red),1,abs_tol=1e-5)
        assert sum(x*y for x,y in zip(red,blue)) < .999, 'Image pixels must affect embeddings'
        print('PASS: real Gemma multimodal projector, pixel-sensitive image vectors and 512d normalization')
    assert adapter.stats()['real_binding']=='1'
    print(f'PASS: pinned local GGUF checksums, model identity, authenticated real inference, dimensions and normalization ({backend}, device={device or "none"})')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=ROOT/'tmp/local/gguf-validation')
    parser.add_argument('--model', choices=('gemma','gemma-gguf'), default='gemma')
    parser.add_argument('--endpoint', help='In-network validation client mode; starts no containers')
    parser.add_argument('--key-file', default='/models/llama-api-key')
    parser.add_argument('--client-image', help='Production dependency image for an in-network smoke client')
    parser.add_argument('--network', help='Existing isolated Docker network for egress-denied acceptance')
    parser.add_argument('--backend', choices=('cpu','vulkan'), default='cpu')
    parser.add_argument('--device', help='Actual device reported by the pinned runtime, required for Vulkan acceptance')
    parser.add_argument('--keep-running', action='store_true', help='leave a successfully verified runtime for subsequent integration tests')
    parser.add_argument('--name', help='explicit isolated Docker container name')
    parser.add_argument('--port', type=int, help='explicit loopback port')
    args = parser.parse_args()
    if args.backend == 'vulkan' and not args.device:
        parser.error('--backend vulkan requires an explicitly probed --device')
    if args.endpoint:
        exercise(LlamaCppEmbeddingModel(endpoint=args.endpoint, key_file=args.key_file, timeout=120), backend=args.backend, device=args.device)
        return
    if args.network and not args.client_image:
        parser.error('Isolated network acceptance requires --client-image; host port access is not a valid isolated-network client')
    model = prepare(args.cache.resolve(), args.model)
    lock = json.loads((ROOT/'distribution/deployment/accelerator-lock.json').read_text())
    image = lock['linux']['vulkan']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    port = args.port or port
    name = args.name or f'pi-gguf-smoke-{os.getpid()}'
    succeeded = False
    try:
        argv = build_server_argv(model_path=f'/models/{model.name}',
            projector_path='/models/' + GEMMA_PROJECTOR_FILENAME, alias=GEMMA_MODEL_ALIAS,
            backend=args.backend, device=args.device, host='0.0.0.0', api_key_file='/models/llama-api-key')
        isolation = ['--network', args.network] if args.network else []
        if args.backend == 'vulkan': isolation += ['--device', '/dev/dri:/dev/dri']
        published = [] if args.network else ['-p',f'127.0.0.1:{port}:8769']
        subprocess.run(['docker','run','-d','--name',name,*isolation,*published,
            '-v',f'{model.parent}:/models:ro',image,*argv],check=True,stdout=subprocess.DEVNULL)
        adapter = LlamaCppEmbeddingModel(endpoint=f'http://127.0.0.1:{port}',
            key_file=str(model.parent/'llama-api-key'), timeout=120, model_alias=GEMMA_MODEL_ALIAS)
        if args.network:
            client = ['docker','run','--rm','--network',args.network,'--entrypoint','python',
                '-v',f'{model.parent}:/models:ro','-v',f'{Path(__file__).resolve()}:/validation/smoke.py:ro',
                args.client_image,'/validation/smoke.py','--endpoint',f'http://{name}:8769',
                '--key-file','/models/llama-api-key','--backend',args.backend]
            if args.device: client += ['--device', args.device]
            subprocess.run(client,check=True)
        else:
            exercise(adapter, backend=args.backend, device=args.device)
        succeeded = True
    finally:
        if not (args.keep_running and succeeded):
            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,check=False)


if __name__ == '__main__': main()
