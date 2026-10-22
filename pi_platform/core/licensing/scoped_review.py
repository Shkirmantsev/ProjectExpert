"""Validate explicit release review against exact dependency and evidence bytes."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .policy import LicensePolicy


def load_scoped_review(path: Path, *, inventory: Path, lock: Path,
                       evidence: Path) -> dict[tuple[str, str, str], str]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('status') != 'approved':
        raise ValueError('Production license review is not approved by the operator')
    if not payload.get('accepted_by') or not payload.get('accepted_at'):
        raise ValueError('Production license review requires acceptance attribution and date')
    for field, source in (('lock_sha256', lock), ('inventory_sha256', inventory),
                          ('evidence_sha256', evidence)):
        if payload.get(field) != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError(f'Production license review is stale: {field}')
    dependencies = json.loads(inventory.read_text(encoding='utf-8'))['dependencies']
    recorded = {(d['name'], d['version'], d['spdx']) for d in dependencies}
    approved = {}
    for entry in payload.get('coordinates', []):
        key = (entry['name'], entry['version'], entry['license_expression'])
        if key not in recorded or key in approved:
            raise ValueError(f'Unknown or duplicate reviewed coordinate: {key}')
        if entry.get('decision') != 'accepted' or not entry.get('obligations'):
            raise ValueError(f'Coordinate lacks acceptance or obligations: {key}')
        # The record never authorizes the globally restricted patterns.
        policy = LicensePolicy()
        if any(policy._matches_deny(token) for token in re.findall(r'[A-Za-z0-9][A-Za-z0-9.+:-]*', key[2])):
            raise ValueError(f'Restricted dependency cannot use scoped review: {key}')
        approved[key] = entry['obligations']
    return approved


class ScopedReviewPolicy(LicensePolicy):
    def __init__(self, accepted: dict[tuple[str, str, str], str]):
        super().__init__()
        self.accepted = accepted

    def evaluate(self, dependency):
        key = (dependency.name, dependency.version, dependency.spdx)
        if key in self.accepted:
            return 'allow', 'Exact coordinate accepted in hash-bound production review'
        return super().evaluate(dependency)
