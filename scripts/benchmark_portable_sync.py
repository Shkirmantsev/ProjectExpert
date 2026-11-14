#!/usr/bin/env python3
"""Reproducible synthetic portability benchmarks; never touches a user checkout.

Production mode uses the same real SQLite/Git fixture as the regression suite,
with hashing embeddings. Format mode measures the bounded text writer/reader.
Neither certifies real-model or physical deployment performance.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def format_benchmark(count):
    from pi_platform.adapters.sync.portable_format import add_record, encode, read_snapshot, sha, spool, write_snapshot
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with spool(root) as db:
            for i in range(count):
                raw = encode({'id': f'chunk-{i}', 'rawText': f'Synthetic canonical chunk {i}',
                              'contentHash': sha(str(i).encode())})
                add_record(db, 'payload', sha(raw), {'raw': raw.decode()})
            staged = time.monotonic()
            write_snapshot(db, root / 'knowledge')
            written = time.monotonic()
        with spool(root) as db:
            report = read_snapshot(root / 'knowledge', db)
            if db.execute('SELECT count(*) FROM records').fetchone()[0] != count:
                raise RuntimeError('Benchmark record count mismatch')
        verified = time.monotonic()
        maximum = max(p.stat().st_size for p in (root / 'knowledge').rglob('*') if p.is_file())
    try:
        import resource
        # macOS reports bytes; Linux reports KiB.
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_bytes = rss if sys.platform == 'darwin' else rss * 1024
    except ImportError:
        rss_bytes = None
    return {'mode': 'format-only', 'records': count, 'files': report['fileCount'],
            'bytes': report['totalBytes'], 'maximumFileBytes': maximum,
            'spoolSeconds': round(staged - started, 3), 'writeSeconds': round(written - staged, 3),
            'verifySeconds': round(verified - written, 3), 'peakProcessRssBytes': rss_bytes}


def production_benchmark():
    from tests.test_portable_canonical_sync import PortableProductionTests, git
    fixture = PortableProductionTests()
    fixture.setUp()
    rows = []
    try:
        for i in range(48):
            (fixture.root / f'source-{i:02}.md').write_text(
                f'# Service {i}\nProcess payment category {i} reliably.\n', encoding='utf-8')
        git(fixture.root, 'add', '.')
        git(fixture.root, 'commit', '-m', '50 source corpus')
        def build(label, root=None):
            started = time.monotonic()
            runtime = fixture.build(root)
            rows.append({'scenario': label, 'seconds': round(time.monotonic() - started, 3),
                'parserCalls': runtime.extra['source_parse_misses'],
                'parseHits': runtime.extra['source_parse_hits'],
                'documentEmbeddings': runtime.extra['indexing_report'].embedded_count,
                'vectorHits': runtime.extra['indexing_report'].reused_count,
                'activeChunks': len(runtime.extra['chunk_ids']),
                'sourceWorkerLimit': runtime.extra['source_admission'].get('cpu_worker_limit'),
                'peakPendingSourceWorkers': runtime.extra['source_admission'].get('peak_pending_workers')})
            return runtime
        first = build('initial')
        fixture.publish_runtime(first)
        full = fixture.stage(vectors=True)
        fixture.publish(full)
        git(fixture.root, 'add', 'project-knowledge')
        git(fixture.root, 'commit', '-m', 'full snapshot')
        full_clone = fixture.base / 'full-clone'
        git(fixture.base, 'clone', str(fixture.root), str(full_clone))
        build('warm')
        build('cold-clone-full-vectors', full_clone)
        standard = fixture.stage()
        fixture.publish(standard)
        git(fixture.root, 'add', 'project-knowledge')
        git(fixture.root, 'commit', '-m', 'standard snapshot')
        plain_clone = fixture.base / 'plain-clone'
        git(fixture.base, 'clone', str(fixture.root), str(plain_clone))
        build('cold-clone-no-vectors', plain_clone)
        git(fixture.root, 'switch', '-c', 'five-changes')
        for i in range(5):
            (fixture.root / f'source-{i:02}.md').write_text(
                f'# Service {i}\nChanged cancellation handling category {i}.\n', encoding='utf-8')
        git(fixture.root, 'add', '-u')
        git(fixture.root, 'commit', '-m', 'five changes')
        build('branch-5-of-50')
        git(fixture.root, 'switch', 'main')
        build('return-to-main')
        return {'mode': 'production-hashing-fixture', 'scenarios': rows,
            'fullSnapshotBytes': full['totalBytes'], 'standardSnapshotBytes': standard['totalBytes'],
            'fullSnapshotFiles': full['fileCount'], 'standardSnapshotFiles': standard['fileCount'],
            'gitObjects': git(fixture.root, 'count-objects', '-v')}
    finally:
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('format', 'production'))
    parser.add_argument('--records', type=int, default=10000)
    args = parser.parse_args()
    if not 1 <= args.records <= 1000000:
        parser.error('--records must be 1 through 1000000')
    report = format_benchmark(args.records) if args.mode == 'format' else production_benchmark()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
