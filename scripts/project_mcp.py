#!/usr/bin/env python3
"""Own a connectable loopback MCP process; never signal a PID from a state file."""
from __future__ import annotations

import argparse
from collections import deque
from typing import Callable
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import threading
import traceback
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

from common import ROOT, atomic_write_text, parse_env, project_root, validate_project_root
from file_lock import file_lock


def settings(env: dict[str, str]) -> tuple[str, int]:
    transport = env.get('PROJECT_CONTEXT_MCP_TRANSPORT', 'stdio').strip().lower()
    if transport not in {'stdio', 'http'}:
        raise ValueError('PROJECT_CONTEXT_MCP_TRANSPORT must be stdio or http')
    try:
        port = int(env.get('PROJECT_CONTEXT_MCP_PORT', '18883'))
    except ValueError:
        raise ValueError('PROJECT_CONTEXT_MCP_PORT must be an integer') from None
    if not 1024 <= port <= 65535:
        raise ValueError('PROJECT_CONTEXT_MCP_PORT must be between 1024 and 65535')
    return transport, port


def installed_python() -> Path:
    return ROOT / 'tmp/local/project-context/venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def server_command(python: Path, root: str, port: int) -> list[str]:
    arguments = ['--root', root, '--transport', 'streamable-http', '--port', str(port)]
    if os.name != 'nt':
        return [str(python), '-m', 'project_context_mcp.server', *arguments]
    # Windows venv python.exe is a redirector: its Popen PID/handle can belong
    # to the launcher instead of the server. Run the matching base interpreter
    # directly, loading this venv's packages and editable-install .pth files.
    venv = python.parent.parent
    config = {}
    for line in (venv / 'pyvenv.cfg').read_text(encoding='utf-8').splitlines():
        key, separator, value = line.partition('=')
        if separator:
            config[key.strip()] = value.strip()
    base = Path(config.get('executable', str(Path(config['home']) / 'python.exe')))
    code = ("import sys,site,runpy; p=sys.argv.pop(1); sys.path.insert(0,p); "
            "site.addsitedir(p); runpy.run_module('project_context_mcp.server',run_name='__main__')")
    return [str(base), '-c', code, str(venv / 'Lib/site-packages'), *arguments]


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) on Windows can terminate a process. Query its handle instead.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied: treat as live, never kill.
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


class Lifecycle:
    def __init__(self, state_dir: Path | None = None):
        self.directory = state_dir or ROOT / 'tmp/local/mcp'
        self.state_file = self.directory / 'project-context.json'
        self.stop_file = self.directory / 'stop.json'
        self.log_file = self.directory / 'project-context.log'
        self.lock_file = self.directory / 'lifecycle.lock'

    def read(self) -> dict:
        try:
            value = json.loads(self.state_file.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def write(self, state: dict) -> None:
        atomic_write_text(self.state_file, json.dumps(state) + '\n', mode=0o600)

    def active(self, state: dict) -> bool:
        return state.get('phase') in {'starting', 'ready'} and process_alive(int(state.get('workerPid', 0)))

    def ready(self, state: dict) -> bool:
        if state.get('phase') != 'ready':
            return False
        try:
            # No system proxy: readiness is strictly a loopback request.
            url = f"http://127.0.0.1:{int(state['port'])}/health"
            with build_opener(ProxyHandler({})).open(url, timeout=0.5) as response:
                health = json.load(response)
            return health.get('instance') == state.get('instance') and health.get('pid') == state.get('serverPid')
        except (OSError, ValueError, KeyError):
            return False

    def start(self, root: Path, port: int, python: Path) -> int:
        with file_lock(self.lock_file):
            state = self.read()
            if self.active(state):
                if self.ready(state):
                    print(f"project-context MCP already running: http://127.0.0.1:{state['port']}/mcp")
                    return 0
                print('MCP worker is starting or unresponsive; use stop-mcp before restarting', file=sys.stderr)
                return 1
            if not python.is_file():
                print('MCP is not installed; run python harness.py mcp-install (or make init-mcp)', file=sys.stderr)
                return 2
            self.stop_file.unlink(missing_ok=True)
            state = {'instance': uuid4().hex, 'phase': 'starting', 'root': str(root),
                     'python': str(python), 'port': port, 'workerPid': 0}
            self.write(state)
            options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL,
                       'stderr': subprocess.DEVNULL, 'cwd': str(ROOT)}
            if os.name == 'nt':
                options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            else:
                options['start_new_session'] = True
            worker_python = getattr(sys, '_base_executable', sys.executable) if os.name == 'nt' else sys.executable
            worker = subprocess.Popen([worker_python, str(Path(__file__).resolve()), 'worker',
                                       '--state-dir', str(self.directory.resolve())], **options)
            state['workerPid'] = worker.pid
            self.write(state)
            threading.Thread(target=worker.wait, daemon=True).start()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                state = self.read()
                if self.ready(state):
                    print(f'project-context MCP started: http://127.0.0.1:{port}/mcp')
                    print(f'Log: {self.log_file}')
                    return 0
                if state.get('phase') == 'failed' or worker.poll() is not None:
                    break
                time.sleep(0.05)
            atomic_write_text(self.stop_file, json.dumps({'instance': state.get('instance')}) + '\n', mode=0o600)
            print(f'MCP failed to become ready; see {self.log_file}', file=sys.stderr)
            return 1

    def stop(self) -> int:
        with file_lock(self.lock_file):
            state = self.read()
            if not self.active(state):
                print('project-context MCP already stopped')
                return 0
            instance = state['instance']
            atomic_write_text(self.stop_file, json.dumps({'instance': instance}) + '\n', mode=0o600)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                current = self.read()
                if current.get('instance') != instance:
                    print('MCP ownership changed; refusing to stop another instance', file=sys.stderr)
                    return 1
                if not self.active(current):
                    print('project-context MCP stopped')
                    return 0
                time.sleep(0.05)
            print('MCP worker did not acknowledge stop; state retained, no unrelated PID signalled', file=sys.stderr)
            return 1

    def status(self) -> int:
        with file_lock(self.lock_file):
            state = self.read()
            if self.active(state) and self.ready(state):
                print(f"project-context MCP running: http://127.0.0.1:{state['port']}/mcp")
                return 0
            print('project-context MCP unresponsive' if self.active(state) else 'project-context MCP stopped')
            return 1

    def logs(self) -> int:
        if self.log_file.exists():
            with self.log_file.open(encoding='utf-8', errors='replace') as log:
                print(''.join(deque(log, maxlen=50)), end='')
        else:
            print('No project-context MCP log yet')
        return 0

    def clean(self, runtime_cleanup: Callable[[], None] | None = None) -> int:
        with file_lock(self.lock_file):
            if self.active(self.read()):
                print('Stop MCP before cleaning its state', file=sys.stderr)
                return 1
            for path in (self.state_file, self.stop_file, self.log_file):
                path.unlink(missing_ok=True)
            if runtime_cleanup is not None:
                runtime_cleanup()
            print('project-context MCP state and log cleaned')
            return 0

    def worker(self) -> int:
        deadline = time.monotonic() + 5
        state = self.read()
        while state.get('workerPid') != os.getpid() and time.monotonic() < deadline:
            time.sleep(0.02)
            state = self.read()
        if state.get('workerPid') != os.getpid():
            return 1
        child = None
        stopping = False

        def request_stop(*_):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        try:
            with self.log_file.open('ab', buffering=0) as log:
                env = os.environ.copy()
                env['PROJECT_CONTEXT_MCP_INSTANCE'] = state['instance']
                child = subprocess.Popen(server_command(Path(state['python']), state['root'], state['port']),
                    cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
                state['serverPid'] = child.pid
                state['phase'] = 'ready'  # Parent still waits for matching HTTP health.
                self.write(state)
                while child.poll() is None and not stopping:
                    try:
                        request = json.loads(self.stop_file.read_text(encoding='utf-8'))
                        stopping = request.get('instance') == state['instance']
                    except (FileNotFoundError, json.JSONDecodeError):
                        pass
                    time.sleep(0.05)
                if child.poll() is None:
                    child.terminate()  # Owned Popen handle, never a stale file PID.
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
                state['phase'] = 'stopped' if stopping else 'failed'
        except Exception:
            try:
                with self.log_file.open('a', encoding='utf-8') as log:
                    traceback.print_exc(file=log)
            finally:
                state['phase'] = 'failed'
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        finally:
            self.write(state)
        return 0 if state['phase'] == 'stopped' else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'logs', 'clean', 'worker'])
    parser.add_argument('--state-dir', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    lifecycle = Lifecycle(args.state_dir)
    if args.action == 'start':
        env = parse_env()
        _, port = settings(env)
        root = project_root(env)
        validate_project_root(root)
        return lifecycle.start(root, port, installed_python())
    return getattr(lifecycle, args.action)()


if __name__ == '__main__':
    raise SystemExit(main())
