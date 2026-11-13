"""A denied-egress smoke must send HTTP from inside its isolated network."""
import json
import subprocess
import unittest
from unittest.mock import patch

from scripts.smoke_production_container import ContainerEndpoint, request, request_bytes


class OfflineSmokeTransportTests(unittest.TestCase):
    def test_internal_client_preserves_request_and_response_without_host_socket(self):
        payload = {'text': 'fixture billing'}
        result = subprocess.CompletedProcess([], 0, b'{"ready":true}', b'')
        with patch('scripts.smoke_production_container.subprocess.run', return_value=result) as execute, patch(
            'scripts.smoke_production_container.urllib.request.urlopen', side_effect=AssertionError('host network used')):
            self.assertEqual(request(ContainerEndpoint('fixture-app'), '/health/ready', payload), {'ready': True})
        command = execute.call_args.args[0]
        self.assertEqual(command[:4], ['docker', 'exec', 'fixture-app', 'python'])
        self.assertEqual(command[-2], '/health/ready')
        self.assertEqual(json.loads(command[-1]), payload)

    def test_raw_ui_bytes_use_the_same_internal_transport(self):
        result = subprocess.CompletedProcess([], 0, b'<html>fixture</html>', b'')
        with patch('scripts.smoke_production_container.subprocess.run', return_value=result):
            self.assertEqual(request_bytes(ContainerEndpoint('fixture-app'), '/'), b'<html>fixture</html>')

    def test_failed_internal_request_does_not_fall_back_to_host_network(self):
        result = subprocess.CompletedProcess([], 1, b'', b'HTTP 503 fixture unavailable')
        with patch('scripts.smoke_production_container.subprocess.run', return_value=result), patch(
            'scripts.smoke_production_container.urllib.request.urlopen', side_effect=AssertionError('host fallback')):
            with self.assertRaisesRegex(RuntimeError, '503 fixture unavailable'):
                request(ContainerEndpoint('fixture-app'), '/health/ready')


if __name__ == '__main__':
    unittest.main()
