"""Local synthetic managed workspace acceptance; no installed deployment changes.

Uses a cached application image containing the new modules and a built native
helper. Produces storage-only timings, not inference or Windows speed claims.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time


def run(args, *, env=None, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, env=env, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', default='projectexpert:fast-workspace-test')
    parser.add_argument('--agent', default='/tmp/workspace-agent-linux-amd64')
    parser.add_argument('--report', type=Path, default=Path('tmp/local/fast-workspace-acceptance.json'))
    parser.add_argument('--files', type=int, default=30000)
    args = parser.parse_args()
    report = {'files': args.files, 'image': args.image, 'image_id': run(['docker', 'image', 'inspect', args.image, '--format', '{{.Id}}']), 'benchmark_scope': 'native Linux enumerate/read/hash only; inference, Windows and GPU performance not measured'}
    with tempfile.TemporaryDirectory(prefix='projectexpert-fw-acceptance-') as temporary:
        root = Path(temporary)
        repo, kit = root / 'source', root / 'source' / '.project-intelligence-deploy'
        kit.mkdir(parents=True)
        for i in range(args.files):
            path = repo / 'src' / str(i // 500) / f'file-{i}.md'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'# Evidence {i}\nStable source evidence for file {i}.\n')
        excluded = repo / 'database-dumps'
        excluded.mkdir()
        with (excluded / 'huge.dump').open('wb') as stream:
            stream.truncate(2 * 1024**3)
        (repo / '.projectexpert-workspaceignore').write_text('database-dumps/\n*.tar\n')
        (repo / 'image.tar').write_bytes(b'ignored archive')
        (repo / '.env').write_text('DO_NOT_COPY=private-test-marker')
        env = {**os.environ, 'PI_IMAGE': args.image, 'PI_RUNTIME_BACKUP_DIR': str(root / 'backups')}
        def agent(action, extra=()):
            return run([args.agent, action, '--repo', str(repo), '--kit', str(kit), *extra], env=env)
        agent('prepare')
        config = json.loads((kit / 'workspace-agent.json').read_text())
        volumes = [config['Workspace'], config['Runtime']]
        try:
            started = time.perf_counter()
            agent('sync')
            report['initial_import_seconds'] = round(time.perf_counter() - started, 4)
            first_status = json.loads((kit / 'workspace-status.json').read_text())
            report['initial_source_bytes'] = first_status['transferred_bytes']
            context = config['Context']
            def docker_script(script, *, bind=False, runtime=False, writable=False):
                mount = f'type=bind,src={repo},dst=/repo,readonly' if bind else f'type=volume,src={config["Workspace"]},dst=/repo' + ('' if writable else ',readonly')
                command = ['docker', '--context', context, 'run', '--rm', '--network', 'none', '--mount', mount]
                if runtime:
                    command += ['--mount', f'type=volume,src={config["Runtime"]},dst=/repo/.project-intelligence-cache']
                command += ['--entrypoint', 'python', args.image, '-c', script]
                return run(command)
            verify = '''import pathlib,json
r=pathlib.Path('/repo');m=json.loads((r/'.projectexpert-workspace/applied-generation.json').read_text());assert len([p for p in m['files'] if p.startswith('src/')])==%d
assert not (r/'database-dumps').exists();assert not (r/'image.tar').exists();assert not (r/'.env').exists()
print(m['generation'])''' % args.files
            docker_script(verify)
            started = time.perf_counter()
            agent('sync')
            report['unchanged_reconcile_seconds'] = round(time.perf_counter() - started, 4)
            report['unchanged_transferred_bytes'] = json.loads((kit / 'workspace-status.json').read_text())['transferred_bytes']
            assert report['unchanged_transferred_bytes'] == 0
            changed = repo / 'src/0/file-0.md'
            changed.write_text(changed.read_text().replace('Stable', 'Edited'))
            started = time.perf_counter()
            agent('sync')
            report['one_file_update_seconds'] = round(time.perf_counter() - started, 4)
            report['one_file_transferred_bytes'] = json.loads((kit / 'workspace-status.json').read_text())['transferred_bytes']
            assert report['one_file_transferred_bytes'] == changed.stat().st_size
            for i in range(20):
                path = repo / f'src/0/file-{i}.md'
                path.rename(path.with_name(f'renamed-{i}.md'))
            agent('sync')
            docker_script("from pathlib import Path; r=Path('/repo/src/0'); assert all(not (r/f'file-{i}.md').exists() and (r/f'renamed-{i}.md').is_file() for i in range(20))")
            # Real same-host per-file I/O comparison; fixed bytes, same image,
            # no parser/model/device differences hidden in a storage measurement.
            measure = '''import pathlib,hashlib,time,json
start=time.perf_counter();paths=sorted(pathlib.Path('/repo/src').rglob('*.md'));size=0
for p in paths: size+=len(p.read_bytes());hashlib.sha256(p.read_bytes()).digest()
print(json.dumps({'seconds':time.perf_counter()-start,'files':len(paths),'bytes':size}))'''
            for mode in ('bind', 'volume'):
                values = [json.loads(docker_script(measure, bind=mode == 'bind')) for _ in range(3)]
                report[mode + '_enumerate_read_hash_median_seconds'] = round(statistics.median(v['seconds'] for v in values), 4)
                assert all(v['files'] == args.files for v in values)
            # Seed a real multi-artifact runtime snapshot, then exercise actual
            # Docker stream export, host verification and inactive-volume restore.
            seed = '''from pathlib import Path
import sqlite3,json,os
from pi_platform.adapters.fs.container_identity import prepare_project_user
os.environ['PI_RUN_AS_PROJECT_OWNER']='1';prepare_project_user('/repo')
from pi_platform.core.sync.version_snapshot import *
r=Path('/repo/.project-intelligence-cache');r.mkdir(exist_ok=True)
RuntimeSnapshotService(cache_root=r).commit(active=PersistedActiveVersion(project_version='v',branch='main',head='abc',working_tree_fingerprint='fp',manifest_snapshot_hash='mh',source_snapshot_hash='sh',embedding_profile_identity='profile',active_index_generation='generation',last_refresh_id='refresh'),manifest=ManifestSnapshot(snapshot_hash='mh',chunk_ids=(),graph_node_ids=()),source=SourceSnapshot(snapshot_hash='sh',source_ids=(),content_hashes={}))
for name in ['runtime.db','embeddings.sqlite','documents-v2.sqlite']:
 c=sqlite3.connect(r/name);c.execute('PRAGMA journal_mode=WAL');c.execute('CREATE VIRTUAL TABLE evidence USING fts5(text)');c.execute("INSERT INTO evidence VALUES ('recoverable evidence')");c.commit();c.close()
(r/'ingestion.json').write_text('{}');(r/'settings.json').write_text('{"secret":"never-backup"}')
(r/'readiness.json').write_text('{"consistent":true,"in_progress":false}')
'''
            docker_script(seed, runtime=True)
            agent('backup')
            status = json.loads((kit / 'workspace-backup-status.json').read_text())
            backup = Path(status['path'])
            assert (backup / 'runtime.db').is_file() and (backup / 'embeddings.sqlite').is_file()
            assert not (backup / 'settings.json').exists()
            agent('restore', ['--backup', str(backup)])
            selected = json.loads((kit / 'workspace-agent.json').read_text())['Runtime']
            volumes.append(selected)
            assert selected != config['Runtime']
            config['Runtime'] = selected
            docker_script("import sqlite3; from pathlib import Path; r=Path('/repo/.project-intelligence-cache'); assert (r/'restored-checkpoint.json').is_file(); c=sqlite3.connect(r/'embeddings.sqlite'); assert len(c.execute(\"SELECT * FROM evidence WHERE evidence MATCH 'recoverable'\").fetchall())==1", runtime=True)
            report['checks'] = [f'{args.files}-file import', 'secret/huge dump/archive exclusion', 'zero unchanged source bytes', 'same-size edit', '20 renames/deletes', 'WAL/FTS checkpoint', 'host verification', 'inactive restore', 'old volume preserved']
        finally:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2))
            for volume in volumes:
                run(['docker', '--context', config['Context'], 'volume', 'rm', volume])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
