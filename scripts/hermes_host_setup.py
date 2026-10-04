#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, shlex, shutil, subprocess
from pathlib import Path
from common import parse_env, project_root, validate_project_root, bool_env

def run(cmd, check=True):
    print("+", shlex.join(str(x) for x in cmd))
    return subprocess.run(cmd, check=check)

def sudo(*args, check=True):
    return run(["sudo", *map(str, args)], check=check)

def parent_chain(root: Path):
    out = []
    p = root.parent
    while p != p.parent and p != Path("/home"):
        out.append(p)
        p = p.parent
    return reversed(out)

def deny_paths(root: Path, raw: str):
    found = set()
    for pattern in [x.strip() for x in raw.split(",") if x.strip()]:
        for p in root.glob(pattern):
            try:
                p.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            found.add(p)
    return sorted(found)

def main():
    if os.name == "nt":
        raise SystemExit("Hermes host ACL setup requires a POSIX host with ACL tools")
    import pwd
    ap = argparse.ArgumentParser()
    ap.add_argument("--revoke", action="store_true")
    ap.add_argument("--yes-enable-tailscale-ssh", action="store_true")
    args = ap.parse_args()
    env = parse_env()
    root = project_root(env)
    validate_project_root(root)
    user = env.get("HERMES_PROJECT_USER", "hermes-worker")

    if args.revoke:
        for p in parent_chain(root):
            sudo("setfacl", "-x", f"u:{user}", p, check=False)
        sudo("setfacl", "-R", "-x", f"u:{user}", root, check=False)
        subprocess.run(["sudo", "find", str(root), "-type", "d", "-exec", "setfacl", "-x", f"d:u:{user}", "{}", "+"], check=False)
        print("Project ACL revoked; dedicated account was kept. No workspace symlink is used by this layout.")
        return

    if not shutil.which("setfacl"):
        raise SystemExit("Install ACL tools first: sudo apt install acl")
    try:
        pwd.getpwnam(user)
        print(f"User {user} already exists")
    except KeyError:
        sudo("useradd", "--create-home", "--shell", "/bin/bash", user)
        sudo("passwd", "-l", user)

    # Remove common privilege-bearing supplemental groups. Never add this
    # account to docker/sudo/adm/lxd.
    for group in ("sudo", "docker", "adm", "lxd"):
        subprocess.run(["sudo", "gpasswd", "-d", user, group], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Parent directories are traverse-only; the selected repository is rwX.
    for parent in parent_chain(root):
        sudo("setfacl", "-m", f"u:{user}:--x", parent)
    sudo("setfacl", "-R", "-m", f"u:{user}:rwX", root)
    subprocess.run(["sudo", "find", str(root), "-type", "d", "-exec", "setfacl", "-m", f"d:u:{user}:rwX", "{}", "+"], check=True)

    # Deny currently-present harness credentials / generated secret material.
    deny_raw = env.get("HERMES_PROJECT_DENY_GLOBS", ".env,.env.*,secrets,.generated")
    denied = deny_paths(root, deny_raw)
    for path in denied:
        sudo("setfacl", "-R", "-m", f"u:{user}:---", path)
        if path.is_dir():
            subprocess.run(["sudo", "find", str(path), "-type", "d", "-exec", "setfacl", "-m", f"d:u:{user}:---", "{}", "+"], check=False)

    inbox = root / ".harness" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    sudo("setfacl", "-m", f"u:{user}:rwx", root / ".harness")
    sudo("setfacl", "-m", f"u:{user}:rwx", inbox)
    sudo("setfacl", "-m", f"d:u:{user}:rwx", inbox)

    if bool_env(env, "HERMES_USE_TAILSCALE_SSH"):
        if args.yes_enable_tailscale_ssh:
            sudo("tailscale", "set", "--ssh")
        else:
            print("NOTE: Tailscale SSH was not changed. Enable once with: sudo tailscale set --ssh")

    # Local permissions smoke test using the same OS identity Hermes will use.
    smoke = root / ".harness" / "hermes-host-setup-smoke.txt"
    run(["sudo", "-u", user, "bash", "-lc", f"cd {shlex.quote(str(root))} && printf 'ok\\n' > {shlex.quote(str(smoke))} && cat {shlex.quote(str(smoke))} && rm {shlex.quote(str(smoke))}"])
    run(["sudo", "-u", user, "test", "-r", str(root)])

    print(f"PASS: {user} has project ACL access to {root}")
    if denied:
        print("Explicitly denied current sensitive paths:", ", ".join(str(p.relative_to(root)) for p in denied))
    print("IMPORTANT: rerun `make hermes-host-setup` after adding a new sensitive path matching HERMES_PROJECT_DENY_GLOBS.")
    print("No /workspace symlink and no SSH keypair are created. Each delegated request carries the absolute PROJECT_ROOT.")
    print("For unattended Hermes SSH, configure a narrow Tailscale SSH policy that does not require interactive re-authentication.")

def _test_parent_chain():
    return list(parent_chain(Path("/home/alice/projects/repo")))

if __name__ == "__main__":
    main()
