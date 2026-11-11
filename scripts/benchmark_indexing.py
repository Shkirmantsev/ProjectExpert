#!/usr/bin/env python3
"""Reproducible local fixture timings; never a production-model speedup claim."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(args):
    from pi_platform.core.control.retrieval_settings import RetrievalSettings
    from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
    from pi_platform.core.orchestration.repository_indexing import index_repository
    from pi_platform.adapters.runtime.sqlite_ingestion_cache import indexing_progress
    from pi_platform.adapters.runtime.host_resources import probe_cpu_capacity
    # This harness deliberately measures the local fixture engine with hashing.
    # Production/model/Windows reports must use a separate actual environment.
    env = {'PI_STARTUP_PROFILE': 'minimal', 'PI_EMBEDDING_MODEL': 'hashing',
           'PI_DENSE_INDEX': 'flat', 'PI_DOCLING_ENABLED': '0', 'PI_EMBED_BATCHING': '1'}
    previous = {key: os.environ.get(key) for key in env}
    previous.update({key: os.environ.get(key) for key in ('PI_INDEX_ENGINE', 'PI_INDEX_PARALLEL')})
    results = []
    args.work_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix='fixture-', dir=args.work_root))
    try:
        os.environ.update(env)
        source = workspace / 'source'
        source.mkdir()
        for number in range(args.files):
            (source / f'component-{number:05}.md').write_text(
                f'# Component {number}\n' + '\n'.join(
                    f'## Rule {paragraph}\nCustomer payment refund and shipping parcel {number} {paragraph}.'
                    for paragraph in range(args.sections)), encoding='utf-8')
        inventory = RepositorySourceDiscovery().discover(source)
        expected = None
        for engine, parallel in (('legacy', '0'), ('resumable', '0'), ('resumable', '1')):
            os.environ.update(PI_INDEX_ENGINE=engine, PI_INDEX_PARALLEL=parallel)
            cache = workspace / f'{engine}-{parallel}'
            for attempt in range(args.repeats):
                start = time.perf_counter()
                runtime = index_repository(target=source, cache_root=cache, inventory=inventory,
                    previous_inventory=None, settings=RetrievalSettings())
                elapsed = time.perf_counter() - start
                identity = (runtime.extra['source_generation'], runtime.extra['chunk_ids'])
                if expected is None:
                    expected = identity
                elif identity != expected:
                    raise RuntimeError('Fixture canonical generation differs between modes')
                results.append({'engine': engine, 'parallel': parallel == '1', 'attempt': attempt + 1,
                    'cache_state': 'cold' if attempt == 0 else 'warm', 'wall_seconds': elapsed,
                    'sources_per_second': len(inventory.entries) / elapsed,
                    'sources': len(inventory.entries), 'chunks': len(runtime.extra['chunk_ids']),
                    'embedding': asdict(runtime.extra['indexing_report']),
                    'progress': indexing_progress(cache / 'indexing-state.sqlite')})
        report = {'evidence_scope': 'local generated Markdown fixture; hashing embeddings; no production speedup claim',
            'python': platform.python_version(), 'platform': platform.platform(),
            'effective_cpus': probe_cpu_capacity(), 'fixture': str(workspace), 'runs': results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
        print(f'PASS: {len(results)} fixture runs, identical canonical generations; report: {args.output}')
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', type=int, default=50)
    parser.add_argument('--sections', type=int, default=8)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--work-root', type=Path, default=ROOT / 'tmp/local/indexing-benchmark')
    parser.add_argument('--output', type=Path, default=ROOT / 'tmp/local/indexing-benchmark/report.json')
    args = parser.parse_args()
    if min(args.files, args.sections, args.repeats) < 1:
        parser.error('files, sections and repeats must be positive')
    run(args)


if __name__ == '__main__':
    main()
