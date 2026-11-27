"""Project-local operator workflow over the existing indexer and signed writer."""
import os
from pathlib import Path
import re
import secrets

from pi_platform.adapters.sync.portable_format import confined, decode, encode, read_bounded
from pi_platform.core.canonical.durable_write import atomic_write_bytes
from pi_platform.core.sync.materialise import MaterialiseService
from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
from pi_platform.ports import ApprovalRequest

DEFAULTS = {'share_enabled': False, 'post_reindex_export': False, 'include_vectors': False}


class KnowledgeSyncCoordinator:
    def __init__(self, target, cache_root, *, index=None, authenticated_operator=False, local_operator=False):
        self.target = Path(target).resolve()
        self.cache = Path(cache_root).resolve()
        self.index = index
        self.authenticated_operator = authenticated_operator
        self.local_operator = local_operator
        self.operator_authorized = authenticated_operator or local_operator
        self.settings_path = self.cache / 'knowledge-settings.json'

    def settings(self):
        if not self.settings_path.exists():
            return dict(DEFAULTS)
        value = decode(read_bounded(confined(self.cache, self.settings_path.name), 4096))
        if not isinstance(value, dict) or any(type(value.get(k, v)) is not bool for k, v in DEFAULTS.items()):
            raise ValueError("Invalid private knowledge settings")
        return {k: value.get(k, v) for k, v in DEFAULTS.items()}

    def save_settings(self, patch):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer
        with exclusive_indexer(self.cache):
            return self._save_settings(patch)

    def _save_settings(self, patch):
        if set(patch) - DEFAULTS.keys() or any(type(v) is not bool for v in patch.values()):
            raise ValueError('Knowledge settings accept only the three boolean preferences')
        value = {**self.settings(), **patch}
        if value['post_reindex_export'] and not value['share_enabled']:
            raise ValueError('Enable safe sharing before automatic export')
        if value['post_reindex_export']:
            boundary = self._operator_boundary()
            # An explicit, expiring repository grant; stored only in private cache.
            grant = boundary.issue(ApprovalRequest(action='materialise', repo_root=str(self.target)), ttl_seconds=3600)
            self._private_write(self.cache / 'security-state' / 'auto-export-grant', grant.encode())
        self._private_write(self.settings_path, encode(value))
        return value

    def _private_write(self, path, raw):
        from pi_platform.adapters.fs.private_cache import ensure_private_cache
        ensure_private_cache(self.target, self.cache)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_bytes(path, raw)
        if os.name != 'nt':
            path.parent.chmod(0o700)
            path.chmod(0o600)

    def _operator_boundary(self):
        if not self.operator_authorized:
            raise ValueError('Authenticated administrator or trusted local owner required for publication authorization')
        from pi_platform.adapters.fs.private_cache import ensure_private_cache
        ensure_private_cache(self.target, self.cache)
        boundary = HmacTrustedApprovalBoundary()
        if boundary.has_key():
            return boundary
        path = self.cache / 'security-state' / 'operator-approval.key'
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        # O_EXCL handles simultaneous first approvals without replacing a key.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(secrets.token_bytes(32))
        return HmacTrustedApprovalBoundary(key=read_bounded(confined(path.parent, path.name), 4096))

    def export(self):
        settings = self.settings()
        if not settings['share_enabled']:
            raise ValueError('Enable safe knowledge sharing in project settings first')
        result = MaterialiseService().stage_active_index(self.target, cache_root=self.cache,
            include_vectors=settings['include_vectors'])
        return {k: v for k, v in result.items() if k in {
            'stagingId', 'snapshotId', 'sources', 'excludedSourceCount', 'excludedReasonCounts',
            'completeForExportableScope', 'completeForLocalIndex', 'totalBytes', 'fileCount',
            'vectors', 'changedPaths', 'state', 'cleanupRequired', 'message', 'safeContextCount'}}

    def review_source(self, path, classification):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer
        with exclusive_indexer(self.cache):
            return self._review_source(path, classification)

    def _review_source(self, path, classification):
        """Resolve unknown media sensitivity by an authenticated human review.

        A public review never overrides content/policy detectors. The approval
        binds exact bytes and is invalidated when the source changes.
        """
        if not self.operator_authorized:
            raise ValueError('Local owner access or authenticated administrator required for review')
        if classification not in {'public', 'confidential'}:
            raise ValueError('Unknown source classification')
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import _file_checksum
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        if path not in {e.path for e in RepositorySourceDiscovery().discover(self.target).entries}:
            raise ValueError('Source is not in the current project inventory')
        digest = _file_checksum(confined(self.target, path))
        storage = self.cache / 'security-state' / 'source-reviews.json'
        value = decode(read_bounded(storage)) if storage.exists() else {}
        value[path] = {'sourceHash': digest, 'classification': classification}
        self._private_write(storage, encode(value))
        return {'state': 'source-review-saved', 'classification': classification}

    def proposal(self, staging_id):
        if not isinstance(staging_id, str) or not re.fullmatch('[a-f0-9]{32}', staging_id):
            raise ValueError('Invalid proposal identifier')
        path = self.cache / 'portable-staging' / staging_id
        value = decode(read_bounded(confined(path, 'proposal.json')))
        # Deliberately whitelist operator-safe counts; no source inventory/version.
        result = {k: value[k] for k in ('stagingId', 'snapshotId', 'sources', 'excludedSourceCount',
            'excludedReasonCounts', 'completeForExportableScope', 'totalBytes', 'fileCount', 'vectors', 'safeContextCount') if k in value}
        from pi_platform.adapters.sync.portable_snapshot_reader import verified_snapshot
        from pi_platform.adapters.sync.portable_snapshot_exporter import changed_paths
        with verified_snapshot(path / 'knowledge', self.cache) as (_, report):
            result['changedPaths'] = changed_paths(path / 'knowledge', self.target / 'project-knowledge', report['paths'])
        return result

    def publish(self, staging_id):
        if not self.settings()['share_enabled']:
            raise ValueError('Safe knowledge sharing is disabled')
        proposal = self.proposal(staging_id)
        boundary = self._operator_boundary()
        token = boundary.issue(ApprovalRequest(action='materialise', repo_root=str(self.target),
            change_ids=(proposal['snapshotId'],)))
        published = MaterialiseService(boundary=boundary).publish_active_index(self.target, cache_root=self.cache,
            staging_id=staging_id, approval_token=token)
        return {**proposal, 'state': 'published', 'changedPaths': published['changedPaths']}

    def restore(self):
        from pi_platform.core.orchestration.repository_indexing import RestoreRequiresReindex
        if self.index is None:
            raise RuntimeError('Restore execution is unavailable')
        try:
            summary = self.index(restore_only=True)
        except RestoreRequiresReindex as exc:
            return {'state': 'requires-reindex', 'searchReady': False, 'requiresReindex': True,
                    'new_vectors': 0, 'source_parse_misses': 0, **exc.report}
        return {**summary, 'state': 'portable-restored', 'searchReady': True, 'requiresReindex': False}

    def status(self):
        from pi_platform.core.sync.version_monitor import read_project_version
        from pi_platform.core.sync.version_snapshot import RuntimeSnapshotService, RuntimeSnapshotError
        from pi_platform.adapters.sync.portable_format import ROOT
        version = read_project_version(self.target)
        ready = False
        try:
            snapshot = RuntimeSnapshotService(cache_root=self.cache).read_snapshot()
            if snapshot:
                active = snapshot.active
                ready = (active.head == version.head and active.branch == version.branch and
                         active.working_tree_fingerprint == version.working_tree_fingerprint)
        except (OSError, ValueError, RuntimeSnapshotError):
            pass
        return {'branch': version.branch, 'localIndexReady': ready,
                'gitSnapshot': 'present-unverified' if (self.target / 'project-knowledge' / ROOT).exists() else 'absent',
                'settings': self.settings(), 'publicationRequiresAuthenticatedOperator': not self.local_operator}

    def save_job(self, job):
        self._private_write(self.cache / 'knowledge-jobs' / (job['job_id'] + '.json'), encode(job))

    def read_job(self, job_id):
        if not re.fullmatch('job-[a-f0-9]{16}', job_id):
            return None
        path = self.cache / 'knowledge-jobs' / (job_id + '.json')
        if not path.exists():
            return None
        value = decode(read_bounded(confined(path.parent, path.name)))
        if value['status'] in {'queued', 'running'}:
            value.update(status='interrupted', message='Server restarted; retry the operation')
        return value
