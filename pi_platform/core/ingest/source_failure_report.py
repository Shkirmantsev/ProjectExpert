"""Private diagnostics for the latest finished source-processing stage."""

import json
from pathlib import Path

from pi_platform.core.canonical.durable_write import atomic_write_bytes


REPORT_NAME = 'source-failures.json'


def write_source_failures(cache_root, *, job_id, eligible, attempted, failures):
    path = Path(cache_root) / REPORT_NAME
    if not failures and not path.exists():
        return
    payload = {
        'schemaVersion': 1,
        'jobId': job_id,
        'eligibleSources': eligible,
        'attemptedSources': attempted,
        'failedSources': len(failures),
        'unattemptedSources': eligible - attempted,
        'failures': failures,
    }
    atomic_write_bytes(path, (json.dumps(payload, sort_keys=True) + '\n').encode('utf-8'))


def read_source_failures(cache_root):
    path = Path(cache_root) / REPORT_NAME
    if path.is_symlink():
        raise ValueError('Unsafe source failure report path')
    try:
        with path.open(encoding='utf-8') as stream:
            report = json.load(stream)
    except FileNotFoundError:
        return None
    if not isinstance(report, dict) or report.get('schemaVersion') != 1:
        raise ValueError('Unsupported source failure report')
    return report
