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
from pi_platform.adapters.retrieval.gguf_artifacts import MODEL_ALIAS, GEMMA_MODEL_ALIAS, GEMMA_PROJECTOR_FILENAME
from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel
from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole, EmbeddingModelError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=ROOT/'tmp/local/gguf-validation')
    parser.add_argument('--model', choices=('qwen-gguf','gemma-gguf'), default='qwen-gguf')
    args = parser.parse_args()
    gemma = args.model == 'gemma-gguf'
    model = prepare(args.cache.resolve(), args.model)
    lock = json.loads((ROOT/'distribution/deployment/accelerator-lock.json').read_text())
    image = lock['linux']['vulkan']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    name = f'pi-gguf-smoke-{os.getpid()}'
    try:
        subprocess.run(['docker','run','-d','--name',name,'-p',f'127.0.0.1:{port}:8769',
            '-v',f'{model.parent}:/models:ro',image,'--model',f'/models/{model.name}',
            '--alias',GEMMA_MODEL_ALIAS if gemma else MODEL_ALIAS,'--embeddings','--pooling','mean' if gemma else 'last','--ctx-size','8192',
            '--batch-size','8192','--ubatch-size','8192','--parallel','1',
            '--device','none','--n-gpu-layers','0','--host','0.0.0.0','--port','8769',
            '--api-key-file','/models/llama-api-key',
            *(['--mmproj','/models/'+GEMMA_PROJECTOR_FILENAME,'--no-mmproj-offload'] if gemma else [])],check=True,stdout=subprocess.DEVNULL)
        adapter = LlamaCppEmbeddingModel(endpoint=f'http://127.0.0.1:{port}',
            key_file=str(model.parent/'llama-api-key'), timeout=120, model_alias=args.model)
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
        if gemma:
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
        print('PASS: pinned GGUF download, model identity, authenticated real inference, dimensions and normalization (CPU)')
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,check=False)


if __name__ == '__main__': main()
