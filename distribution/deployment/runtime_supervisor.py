"""Bounded internal controller for the managed llama-server child (stdlib only).

No Docker socket, shell commands, model paths or arbitrary flags are accepted
over HTTP. The embedding API key authenticates this unexposed control port.
"""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

BINARY = '/app/llama-server'


def server_arguments(base, device, fit_target):
    if not re.fullmatch(r'none|Vulkan[0-9]+|CUDA[0-9]+', device):
        raise ValueError('Unsupported device')
    if not isinstance(fit_target, int) or isinstance(fit_target, bool) or not 192 <= fit_target <= 512:
        raise ValueError('fit_target must be between 192 and 512 MiB')
    args=[]
    iterator=iter(base)
    for arg in iterator:
        if arg in ('--device', '--fit', '--fit-target'):
            next(iterator, None)
        else:
            args.append(arg)
    args += ['--device', device]
    if device != 'none':
        args += ['--fit', 'on', '--fit-target', str(fit_target)]
    return args


class Supervisor:
    def __init__(self, base):
        self.base=base
        self.device='none'
        if '--device' in base:
            self.device=base[base.index('--device')+1]
        self.device=os.environ.get('PI_RUNTIME_INITIAL_DEVICE', self.device)
        self.fit_target=192
        if '--fit-target' in base:
            self.fit_target=int(base[base.index('--fit-target')+1])
        self.backend=os.environ.get('PI_RUNTIME_BACKEND', 'vulkan')
        self.generation=uuid.uuid4().hex
        self.process=None
        self.lock=threading.Lock()
        self.applying=False

    def probe(self):
        result=subprocess.run([BINARY, '--list-devices'], capture_output=True,
                              text=True, timeout=20, check=False)
        return (result.stdout+result.stderr)[-32768:] if result.returncode == 0 else ''

    def ready(self):
        if self.process is None or self.process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen('http://127.0.0.1:8769/health', timeout=2) as response:
                return response.status == 200
        except OSError:
            return False

    def status(self):
        return dict(generation=self.generation, backend=self.backend, device=self.device,
                    ready=self.ready(), applying=self.applying, devices=self.probe())

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)

    def start(self, device, fit_target):
        argv=server_arguments(self.base, device, fit_target)
        self.stop()
        self.process=subprocess.Popen([BINARY, *argv])
        deadline=time.monotonic()+180
        while time.monotonic() < deadline:
            if self.ready():
                self.device=device
                self.fit_target=fit_target
                self.generation=uuid.uuid4().hex
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.25)
        raise RuntimeError('Embedding process did not become healthy; inspect embeddings logs')

    def configure(self, body):
        if set(body) - {'device', 'fit_target'}:
            raise ValueError('Only device and fit_target may be configured')
        device=body.get('device', 'none')
        fit=body.get('fit_target', 192)
        server_arguments(self.base, device, fit)
        if device != 'none' and not re.search(r'(?m)^\s*'+re.escape(device)+r'\s*:', self.probe()):
            raise ValueError('GPU device is unavailable in this container; configure GPU passthrough first')
        if not self.lock.acquire(blocking=False):
            raise ValueError('Runtime change already in progress')
        previous=(self.device, self.fit_target)
        try:
            self.applying=True
            if previous != (device, fit) or not self.ready():
                try:
                    self.start(device, fit)
                except RuntimeError as error:
                    try:
                        self.start(*previous)
                    except RuntimeError:
                        raise RuntimeError('Runtime change and rollback failed; inspect embeddings logs') from None
                    raise RuntimeError(str(error)+'; previous device restored') from None
            return self.status()
        finally:
            self.applying=False
            self.lock.release()


def handler(controller, key):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            data=json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+key)

        def do_GET(self):
            if not self.authorized():
                self.reply(401, {'error':'Unauthorized'}); return
            if self.path != '/runtime':
                self.reply(404, {'error':'Not found'}); return
            self.reply(200, controller.status())

        def do_PUT(self):
            if not self.authorized():
                self.reply(401, {'error':'Unauthorized'}); return
            if self.path != '/runtime':
                self.reply(404, {'error':'Not found'}); return
            try:
                length=int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024:
                    raise ValueError('Expected bounded JSON body')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Expected JSON object')
                self.reply(200, controller.configure(body))
            except (ValueError, TypeError) as error:
                self.reply(400, {'error':str(error)})
            except RuntimeError as error:
                self.reply(503, {'error':str(error)})
    return Handler


def main():
    if '--list-devices' in sys.argv[1:]:
        os.execv(BINARY, [BINARY, '--list-devices'])
    key=Path('/models/llama-api-key').read_text().strip()
    if not key:
        raise RuntimeError('Managed runtime API key is required')
    controller=Supervisor(sys.argv[1:])
    controller.start(controller.device, controller.fit_target)
    def shutdown(*_):
        controller.stop()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        ThreadingHTTPServer(('0.0.0.0', 8770), handler(controller, key)).serve_forever()
    finally:
        controller.stop()


if __name__ == '__main__':
    main()
