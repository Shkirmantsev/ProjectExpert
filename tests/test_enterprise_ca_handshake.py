"""A real local TLS handshake proves imported roots retain strict verification."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest

from pi_platform.deployment.trust import merge_ca_bundles


@unittest.skipUnless(shutil.which('openssl'), 'OpenSSL required to generate isolated test certificate')
class EnterpriseCAHandshakeTests(unittest.TestCase):
    def test_enterprise_root_trusted_and_unknown_root_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificate, key = root / 'root.pem', root / 'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(str(certificate), str(key))
            server.socket = server_context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                merged = root / 'merged.pem'
                public_roots = root / 'public-roots.pem'
                public_roots.write_text(''.join(ssl.DER_cert_to_PEM_cert(value) for value in ssl.create_default_context().get_ca_certs(binary_form=True)))
                merge_ca_bundles(public_roots, [certificate], merged)
                connection = http.client.HTTPSConnection('localhost', server.server_port, context=ssl.create_default_context(cafile=str(merged)), timeout=4)
                try:
                    connection.request('GET', '/')
                    self.assertEqual(connection.getresponse().status, 200)
                finally:
                    connection.close()
                unknown = http.client.HTTPSConnection('localhost', server.server_port, context=ssl.create_default_context(), timeout=4)
                try:
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        unknown.request('GET', '/')
                finally:
                    unknown.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
