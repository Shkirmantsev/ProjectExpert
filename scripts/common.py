from __future__ import annotations
import json, os, re, secrets, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"

def parse_env(path: Path = ENV) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists(): return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1); data[k.strip()] = v.strip()
    return data

def update_env(updates: dict[str, str], path: Path = ENV) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, value in updates.items():
        pat = re.compile(rf"(?m)^{re.escape(key)}=.*$")
        repl = f"{key}={value}"
        text = pat.sub(lambda _m, r=repl: r, text) if pat.search(text) else text.rstrip() + f"\n{repl}\n"
    atomic_write_text(path, text, mode=0o600)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    mode: int | None = None,
    encoding: str = "utf-8",
) -> None:
    """Publish complete text atomically; apply private mode before content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        if mode is not None and hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding=encoding) as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if mode is not None:
            os.chmod(path, mode)
        if os.name != "nt":
            parent_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)

def random_token(prefix: str = "") -> str:
    return prefix + secrets.token_hex(32)

def bool_env(env: dict[str,str], key: str, default: bool=False) -> bool:
    raw = env.get(key, "true" if default else "false").strip().lower()
    return raw in {"1","true","yes","on"}

def tailscale_identity() -> tuple[str, str]:
    ip = subprocess.check_output(["tailscale", "ip", "-4"], text=True, stderr=subprocess.DEVNULL).strip().splitlines()[0]
    raw = subprocess.check_output(["tailscale", "status", "--json"], text=True, stderr=subprocess.DEVNULL)
    data = json.loads(raw); self_obj = data.get("Self") or {}
    dns = (self_obj.get("DNSName") or "").rstrip(".")
    if not dns: raise RuntimeError("Tailscale DNSName not found")
    return dns, ip

def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return value or "default"

def project_root(env: dict[str,str]) -> Path:
    raw = env.get("PROJECT_ROOT", ".").strip() or "."
    p = Path(raw).expanduser()
    if not p.is_absolute(): p = (ROOT / p)
    return p.resolve()

def validate_project_root(path: Path) -> None:
    forbidden = {Path("/"), Path("/home"), Path("/root"), Path("/etc"), Path("/usr"), Path("/var"), Path("/srv"), Path("/opt")}
    if path in forbidden: raise RuntimeError(f"PROJECT_ROOT is too broad: {path}")
    if not path.exists() or not path.is_dir(): raise RuntimeError(f"PROJECT_ROOT is not a directory: {path}")
    # Reject an entire user's home directory while allowing a repo below it.
    if path.parent == Path("/home") or path == Path.home().resolve():
        raise RuntimeError(f"PROJECT_ROOT may not be an entire home directory: {path}")
