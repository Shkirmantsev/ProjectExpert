"""Best-effort local affinity and cgroup CPU entitlement collection."""
import os
from pathlib import Path
from pi_platform.core.orchestration.resource_budget import effective_cpu_capacity, cpu_worker_budget


def _read(root, name):
    try:
        return (Path(root) / name).read_text().strip()
    except OSError:
        return ""


def _cpuset_count(value):
    cpus = set()
    for part in value.split(","):
        if not part:
            continue
        first, _, last = part.partition("-")
        start, end = int(first), int(last or first)
        if start < 0 or end < start or end - start > 100000:
            raise ValueError("invalid cpuset range")
        cpus.update(range(start, end + 1))
    return len(cpus) or None


def probe_cpu_capacity(cgroup_root="/sys/fs/cgroup", *, engine_limit=None):
    limits = [os.cpu_count(), engine_limit]
    try:
        limits.append(len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    roots = _cgroup_roots(cgroup_root)
    for root in roots:
        for name in ("cpuset.cpus.effective", "cpuset/cpuset.cpus", "cpuset.cpus"):
            try:
                limits.append(_cpuset_count(_read(root, name)))
            except ValueError:
                pass
        try:
            values = _read(root, "cpu.max").split()
            if len(values) == 2 and values[0] != "max" and float(values[1]) > 0:
                limits.append(float(values[0]) / float(values[1]))
            for prefix in ("", "cpu/"):
                quota = float(_read(root, prefix + "cpu.cfs_quota_us") or -1)
                period = float(_read(root, prefix + "cpu.cfs_period_us") or 0)
                if quota > 0 and period > 0:
                    limits.append(quota / period)
        except ValueError:
            pass
    return effective_cpu_capacity(*limits)


def parse_worker_budget(requested=None):
    target = int(os.environ.get("PI_CPU_TARGET_PERCENT", "80"))
    if requested is None:
        requested = os.environ.get("PI_PARSE_WORKERS", os.environ.get("PI_INDEX_WORKERS", "auto"))
    return cpu_worker_budget(probe_cpu_capacity(), target_percent=target,
                             requested=None if requested == "auto" else requested)


def _cgroup_roots(cgroup_root):
    """Collect the process cgroup and parents, including namespace mount root."""
    roots = [Path(cgroup_root)]
    if str(cgroup_root) == "/sys/fs/cgroup":
        try:
            for row in Path("/proc/self/cgroup").read_text().splitlines():
                _, controllers, path = row.split(":", 2)
                # v1 controller mount names commonly include cpu,cpuacct.
                bases = [Path(cgroup_root)] if not controllers else [
                    Path(cgroup_root) / controllers,
                    *[Path(cgroup_root) / name for name in controllers.split(",")]]
                for base in bases:
                    current = (base / path.lstrip("/")).resolve()
                    if not current.is_relative_to(base):
                        continue
                    while current != base:
                        roots.append(current)
                        current = current.parent
                    roots.append(base)
        except (OSError, ValueError):
            pass
    return tuple(dict.fromkeys(roots))


def probe_available_memory(cgroup_root="/sys/fs/cgroup", *, meminfo_path="/proc/meminfo"):
    """Available allocation headroom, capped by every known cgroup remainder.

    None means unknown, while zero means a known exhausted limit. This is a
    live admission observation, not a reservation against unrelated processes.
    """
    limits = []
    try:
        for row in Path(meminfo_path).read_text().splitlines():
            if row.startswith("MemAvailable:"):
                limits.append(max(0, int(row.split()[1]) * 1024))
                break
    except (OSError, ValueError, IndexError):
        pass
    if not limits:
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes
                class MemoryStatus(ctypes.Structure):
                    _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD),
                                *[(name, ctypes.c_ulonglong) for name in (
                                    "total_phys", "avail_phys", "total_page", "avail_page",
                                    "total_virtual", "avail_virtual", "avail_extended")]]
                status = MemoryStatus()
                status.length = ctypes.sizeof(status)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    limits.append(status.avail_phys)
            except (AttributeError, OSError):
                pass
        else:
            try:
                available_pages = os.sysconf("SC_AVPHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                if available_pages >= 0 and page_size > 0:
                    limits.append(available_pages * page_size)
            except (AttributeError, OSError, ValueError):
                pass
    for root in _cgroup_roots(cgroup_root):
        for limit_name, usage_name in (("memory.max", "memory.current"),
                                      ("memory.limit_in_bytes", "memory.usage_in_bytes"),
                                      ("memory/memory.limit_in_bytes", "memory/memory.usage_in_bytes")):
            try:
                limit, usage = _read(root, limit_name), _read(root, usage_name)
                if limit and limit != "max" and usage:
                    maximum, used = int(limit), int(usage)
                    if maximum > 0 and used >= 0:
                        limits.append(max(0, maximum - used))
            except ValueError:
                pass
    return min(limits) if limits else None


def estimate_source_worker_peak(source):
    """Conservative admission estimates for bounded text parser families.

    These are explicit heuristics, not measured RSS guarantees. Archive expansion,
    Docling models and unrecognized families require serial admission until a
    caller supplies a measured estimator. Source-buffer serialization is included
    in the amplification allowance.
    """
    estimates = {
        "java_source": (96, 64 * 1024 * 1024),
        "python_source": (64, 32 * 1024 * 1024),
        "markdown": (32, 16 * 1024 * 1024),
        "plain_text": (32, 16 * 1024 * 1024),
        "html": (64, 32 * 1024 * 1024),
        "maven_pom": (64, 32 * 1024 * 1024),
        "gradle_build": (32, 16 * 1024 * 1024),
        "python_manifest": (32, 16 * 1024 * 1024),
        "node_manifest": (32, 16 * 1024 * 1024),
        "python_lock": (64, 32 * 1024 * 1024),
        "node_lock": (64, 32 * 1024 * 1024),
        "openspec": (32, 16 * 1024 * 1024),
    }
    amplification, overhead = estimates.get(source.family, (None, None))
    if amplification is None:
        return None
    try:
        size = Path(source.uri).stat().st_size
    except (AttributeError, OSError, ValueError):
        return None
    return overhead + size * amplification
