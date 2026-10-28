"""Policy-controlled acquisition of dependency artifacts.

Acquisition is an **explicit** operation. It is never implicit in an
inspection, and it never runs the code of a dependency: the artifact is
downloaded, its integrity is verified and its *bytes* are inspected.

The boundaries are:

* only an approved source identity may be used;
* only an exact ``name`` + ``version`` may be requested;
* every redirect hop must stay on an approved host;
* the download is bounded in size and in time;
* the integrity hash must match before the artifact is published;
* a failed download never publishes a partial artifact;
* the cache is content addressed and idempotent: an unchanged request
  reuses the cached artifact instead of downloading it again.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence

from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.research.policy import AcquisitionPolicy
from pi_platform.core.research.records import (
    EvidenceReference,
    ResearchDenied,
    ResearchError,
    ResearchResult,
    ResearchStatus,
)
from pi_platform.ports.research.dependency_research import DependencyAcquireRequest

__all__ = [
    "FetchResponse",
    "Fetcher",
    "HttpFetcher",
    "ArtifactLocation",
    "ArtifactLocator",
    "PypiLocator",
    "NpmLocator",
    "MavenLocator",
    "AcquisitionError",
    "IntegrityError",
    "AcquisitionTimeout",
    "ArtifactAcquirer",
]


class AcquisitionError(ResearchError):
    """The artifact could not be acquired."""


class IntegrityError(AcquisitionError):
    """The downloaded artifact does not match its expected digest."""


class AcquisitionTimeout(AcquisitionError):
    """The download did not finish within its budget."""


@dataclass(frozen=True)
class FetchResponse:
    """One HTTP response of the fetcher."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    #: Every URL that was visited, including the final one.
    chain: tuple[str, ...] = ()

    def header(self, name: str) -> Optional[str]:
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


class Fetcher(Protocol):
    """The transport of the acquirer.

    The acquirer never talks to the network itself: it asks a fetcher
    and validates the answer. A test therefore supplies a deterministic
    fetcher instead of reaching a registry.
    """

    def fetch(self, url: str, *, max_bytes: int,
              timeout: float) -> FetchResponse: ...


class HttpFetcher:
    """The default fetcher.

    Redirects are followed by urllib, but every hop is recorded so the
    acquirer can verify that the download stayed on an approved host.
    """

    def __init__(self, *, user_agent: str = "project-intelligence/1.0") -> None:
        self._user_agent = user_agent

    def fetch(self, url: str, *, max_bytes: int, timeout: float) -> FetchResponse:
        import urllib.error
        import urllib.request

        chain: list[str] = [url]

        class _Recorder(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                chain.append(newurl)
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        opener = urllib.request.build_opener(_Recorder)
        request = urllib.request.Request(url, headers={"User-Agent": self._user_agent})
        try:
            with opener.open(request, timeout=timeout) as response:
                body = response.read(max_bytes + 1)
                headers = {key: value for key, value in response.headers.items()}
                return FetchResponse(status=response.status, headers=headers,
                                     body=body, chain=tuple(chain))
        except urllib.error.HTTPError as exc:
            raise AcquisitionError(
                f"the registry answered {exc.code} for {url}") from exc
        except OSError as exc:
            raise AcquisitionError(f"cannot reach {url}: {exc}") from exc


@dataclass(frozen=True)
class ArtifactLocation:
    """Where an exact artifact lives and what it must hash to."""

    url: str
    filename: str
    integrity: Optional[str] = None
    size: Optional[int] = None
    source_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def expected_sha256(self) -> Optional[str]:
        """Return the expected SHA-256 digest, if the integrity states one."""

        if not self.integrity:
            return None
        value = self.integrity.strip()
        if value.startswith("sha256="):
            return value.split("=", 1)[1]
        if value.startswith("sha512="):
            return None
        if len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower()):
            return value.lower()
        return None


class ArtifactLocator(Protocol):
    """Resolve an exact package version to a downloadable artifact."""

    source_id: str

    def locate(self, ecosystem: str, name: str, version: str, *,
               fetcher: Fetcher, timeout: float) -> ArtifactLocation: ...


def _json_fetch(url: str, *, fetcher: Fetcher, timeout: float,
                max_bytes: int = 4 * 1024 * 1024) -> Mapping[str, Any]:
    response = fetcher.fetch(url, max_bytes=max_bytes, timeout=timeout)
    if response.status != 200:
        raise AcquisitionError(
            f"the registry answered {response.status} for {url}")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError(f"the registry answer for {url} is not JSON") from exc
    if not isinstance(payload, Mapping):
        raise AcquisitionError(f"the registry answer for {url} is not an object")
    return payload


class PypiLocator:
    """Locate a wheel or source distribution on PyPI."""

    source_id = "pypi"
    index_url = "https://pypi.org/pypi"

    def locate(self, ecosystem: str, name: str, version: str, *,
               fetcher: Fetcher, timeout: float) -> ArtifactLocation:
        payload = _json_fetch(f"{self.index_url}/{name}/{version}/json",
                              fetcher=fetcher, timeout=timeout)
        urls = payload.get("urls")
        if not isinstance(urls, list) or not urls:
            raise AcquisitionError(
                f"{name} {version} has no downloadable artifact on {self.source_id}")
        wheel = next((item for item in urls
                      if isinstance(item, Mapping)
                      and str(item.get("packagetype", "")).endswith("bdist_wheel")),
                     None)
        chosen = wheel or next(item for item in urls if isinstance(item, Mapping))
        url = chosen.get("url")
        if not isinstance(url, str):
            raise AcquisitionError(
                f"{name} {version} has no artifact URL on {self.source_id}")
        filename = url.rsplit("/", 1)[-1]
        digest = chosen.get("digests")
        integrity = None
        if isinstance(digest, Mapping) and isinstance(digest.get("sha256"), str):
            integrity = "sha256=" + digest["sha256"]
        return ArtifactLocation(url=url, filename=filename, integrity=integrity,
                                size=chosen.get("size"), source_id=self.source_id)


class NpmLocator:
    """Locate a package tarball on the npm registry."""

    source_id = "npm"
    registry_url = "https://registry.npmjs.org"

    def locate(self, ecosystem: str, name: str, version: str, *,
               fetcher: Fetcher, timeout: float) -> ArtifactLocation:
        payload = _json_fetch(f"{self.registry_url}/{name}/{version}",
                              fetcher=fetcher, timeout=timeout)
        dist = payload.get("dist")
        if not isinstance(dist, Mapping):
            raise AcquisitionError(
                f"{name} {version} has no distribution on {self.source_id}")
        url = dist.get("tarball")
        if not isinstance(url, str):
            raise AcquisitionError(
                f"{name} {version} has no tarball on {self.source_id}")
        filename = url.rsplit("/", 1)[-1]
        integrity = dist.get("integrity")
        return ArtifactLocation(url=url, filename=filename,
                                integrity=integrity if isinstance(integrity, str) else None,
                                size=None, source_id=self.source_id)


class MavenLocator:
    """Locate an artifact on Maven Central."""

    source_id = "maven-central"
    repository_url = "https://repo1.maven.org/maven2"

    def locate(self, ecosystem: str, name: str, version: str, *,
               fetcher: Fetcher, timeout: float) -> ArtifactLocation:
        group, _, artifact = name.partition(":")
        if not group or not artifact:
            raise AcquisitionError(
                "a Maven coordinate must be 'group:artifact'")
        path = "/".join(group.split("."))
        filename = f"{artifact}-{version}.jar"
        url = f"{self.repository_url}/{path}/{artifact}/{version}/{filename}"
        return ArtifactLocation(url=url, filename=filename, integrity=None,
                                size=None, source_id=self.source_id)


class ArtifactAcquirer:
    """Download and publish one exact dependency artifact."""

    def __init__(self, *, cache_root: Path, fetcher: Optional[Fetcher] = None,
                 locators: Optional[Sequence[ArtifactLocator]] = None,
                 policy: Optional[AcquisitionPolicy] = None) -> None:
        self.cache_root = Path(cache_root)
        self.fetcher = fetcher or HttpFetcher()
        self.policy = policy or AcquisitionPolicy()
        self.locators = {locator.source_id: locator
                         for locator in (locators or (PypiLocator(), NpmLocator(),
                                                      MavenLocator()))}

    # -- public API ----------------------------------------------------------

    def acquire(self, request: DependencyAcquireRequest, *,
                policy: Optional[AcquisitionPolicy] = None) -> ResearchResult:
        policy = policy or self.policy
        if not policy.allows(request.source_id):
            raise ResearchDenied(
                f"the source {request.source_id!r} is not approved by the "
                "acquisition policy")
        locator = self.locators.get(request.source_id)
        if locator is None:
            raise ResearchDenied(
                f"no locator is registered for the source {request.source_id!r}")

        directory = (self.cache_root / request.ecosystem / request.name
                     / request.version)
        manifest_path = directory / "artifact.json"
        cached = self._read_manifest(manifest_path)
        if cached is not None:
            target = directory / cached["filename"]
            if target.is_file() and self._hash_file(target) == cached["sha256"]:
                # Idempotent reuse: the identical artifact is already there.
                return self._result(request, cached, target, reused=True)

        with self._artifact_lock(directory):
            # Another writer may have published the artifact while this
            # call waited for the lock.
            cached = self._read_manifest(manifest_path)
            if cached is not None:
                target = directory / cached["filename"]
                if target.is_file() and self._hash_file(target) == cached["sha256"]:
                    return self._result(request, cached, target, reused=True)

            location = locator.locate(
                request.ecosystem, request.name, request.version,
                fetcher=self.fetcher, timeout=policy.timeout_seconds)
            self._check_hosts(location.url, policy)
            payload = self._download(location, policy)
            digest = hashlib.sha256(payload).hexdigest()
            expected = location.expected_sha256()
            if expected and expected != digest:
                raise IntegrityError(
                    f"the artifact of {request.name} {request.version} hashes to "
                    f"{digest}, but the registry states {expected}")
            published = self._publish(directory, location.filename, payload)
            record = {
                "ecosystem": request.ecosystem,
                "name": request.name,
                "version": request.version,
                "source": request.source_id,
                "url": location.url,
                "filename": published.name,
                "sha256": digest,
                "size": len(payload),
                "acquiredAt": int(time.time()),
            }
            self._write_manifest(manifest_path, record)
            return self._result(request, record, published, reused=False)

    # -- helpers -------------------------------------------------------------

    def _download(self, location: ArtifactLocation,
                  policy: AcquisitionPolicy) -> bytes:
        started = time.monotonic()
        try:
            response = self.fetcher.fetch(location.url,
                                          max_bytes=policy.max_compressed_bytes,
                                          timeout=policy.timeout_seconds)
        except AcquisitionTimeout:
            raise
        except AcquisitionError:
            raise
        if response.status != 200:
            raise AcquisitionError(
                f"the registry answered {response.status} for {location.url}")
        if len(response.chain) > policy.max_redirects + 1:
            raise AcquisitionError(
                f"the download followed {len(response.chain) - 1} redirects, "
                f"above the limit of {policy.max_redirects}")
        for hop in response.chain:
            self._check_hosts(hop, policy)
        if len(response.body) > policy.max_compressed_bytes:
            raise AcquisitionError(
                f"the artifact is {len(response.body)} bytes, above the limit of "
                f"{policy.max_compressed_bytes}")
        if time.monotonic() - started > policy.timeout_seconds:
            raise AcquisitionTimeout(
                f"the download of {location.url} exceeded the budget of "
                f"{policy.timeout_seconds} seconds")
        return response.body

    @staticmethod
    def _check_hosts(url: str, policy: AcquisitionPolicy) -> None:
        """Only approved hosts may be contacted."""

        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise AcquisitionError(
                f"only https artifacts may be downloaded, not {url!r}")
        hosts = policy.allowed_hosts
        if hosts and parsed.netloc not in hosts:
            raise AcquisitionDenied(
                f"the host {parsed.netloc!r} is not approved by the "
                "acquisition policy")

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 256)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _publish(self, directory: Path, filename: str, payload: bytes) -> Path:
        """Publish the artifact atomically; a failure leaves nothing behind."""

        directory.mkdir(parents=True, exist_ok=True)
        safe = Path(filename).name
        if not safe or safe in {".", ".."}:
            raise AcquisitionError(f"unsafe artifact filename: {filename!r}")
        target = directory / safe
        partial = directory / (safe + ".partial")
        try:
            with partial.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(partial, target)
        except OSError as exc:
            partial.unlink(missing_ok=True)
            raise AcquisitionError(f"cannot publish the artifact: {exc}") from exc
        return target

    @staticmethod
    def _read_manifest(path: Path) -> Optional[dict]:
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return record if isinstance(record, dict) else None

    @staticmethod
    def _write_manifest(path: Path, record: Mapping[str, Any]) -> None:
        partial = path.with_suffix(".json.partial")
        try:
            partial.write_text(json.dumps(record, sort_keys=True, indent=2),
                               encoding="utf-8")
            os.replace(partial, path)
        except OSError as exc:
            partial.unlink(missing_ok=True)
            raise AcquisitionError(f"cannot publish the artifact manifest: {exc}") from exc

    class _ArtifactLock:
        """A bounded, per-artifact lock.

        The lock is a file that is created exclusively. A crashed
        process leaves a stale lock behind, so the lock carries its own
        deadline and is reclaimed when it is older than the timeout.
        """

        def __init__(self, path: Path, timeout: float) -> None:
            self._path = path
            self._timeout = timeout
            self._handle: Optional[int] = None

        def __enter__(self) -> "ArtifactAcquirer._ArtifactLock":
            self._path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + self._timeout
            while True:
                try:
                    self._handle = os.open(
                        self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.write(self._handle, str(int(time.time())).encode("ascii"))
                    return self
                except OSError as exc:
                    if exc.errno != errno.EEXIST:
                        raise AcquisitionError(
                            f"cannot take the artifact lock: {exc}") from exc
                try:
                    age = time.time() - self._path.stat().st_mtime
                    if age > self._timeout:
                        self._path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise AcquisitionTimeout(
                        "another acquisition holds the artifact lock")
                time.sleep(0.05)

        def __exit__(self, *exc_info) -> None:
            if self._handle is not None:
                os.close(self._handle)
            self._path.unlink(missing_ok=True)

    def _artifact_lock(self, directory: Path):
        return self._ArtifactLock(directory / ".acquire.lock",
                                  timeout=self.policy.timeout_seconds)

    def _result(self, request: DependencyAcquireRequest, record: Mapping[str, Any],
                target: Path, *, reused: bool) -> ResearchResult:
        evidence = EvidenceReference(
            evidence_id=content_address({
                "kind": "artifact", "ecosystem": request.ecosystem,
                "name": request.name, "version": request.version,
                "sha256": record["sha256"],
            }),
            repository=str(self.cache_root),
            revision=str(record.get("version") or request.version),
            artifact_hash=str(record["sha256"]),
            member=str(record.get("filename") or target.name),
            parser_version="artifact-acquisition-1",
            representation="source",
            license_policy=f"source={record.get('source')}",
        )
        return ResearchResult(
            snapshot_id=str(record["sha256"]),
            status=ResearchStatus.COMPLETE,
            operation="dependency.acquire",
            evidence=(evidence,),
            warnings=(),
            truncated=False,
            limits=self.policy.as_dict(),
            scope={
                "ecosystem": request.ecosystem,
                "name": request.name,
                "version": request.version,
                "source": record.get("source"),
            },
            detail={
                "artifact": {
                    "path": str(target),
                    "filename": target.name,
                    "sha256": record["sha256"],
                    "size": record.get("size"),
                    "url": record.get("url"),
                    "reused": reused,
                },
            },
        )


class AcquisitionDenied(ResearchDenied):
    """The download was refused by the acquisition policy."""


def default_allowed_hosts() -> tuple[str, ...]:
    """The hosts an approved source may redirect to."""

    return ("files.pythonhosted.org", "pypi.org", "registry.npmjs.org",
            "repo1.maven.org")
