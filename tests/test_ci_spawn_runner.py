"""Run the actual Actions Python wrapper against a real spawn-only fixture."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CIProcessRunnerTests(unittest.TestCase):
    def test_actions_runner_does_not_reenter_tests_in_spawned_children(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/verify.yml').read_text())
        step = next(step for step in workflow['jobs']['unit']['steps'] if step.get('shell') == 'python')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / 'tests'
            tests.mkdir()
            (tests / '__init__.py').write_text('')
            (tests / 'test_spawn_fixture.py').write_text('''import multiprocessing, os, unittest

def child(queue):
    queue.put(os.getpid())

class SpawnFixture(unittest.TestCase):
    def test_spawn(self):
        ctx = multiprocessing.get_context('spawn')
        queue = ctx.Queue()
        process = ctx.Process(target=child, args=(queue,))
        try:
            process.start()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertNotEqual(queue.get(timeout=2), os.getpid())
        finally:
            if process.is_alive():
                process.terminate()
                process.join(5)
            process.close()
            queue.close()
            queue.join_thread()
''')
            runner = root / 'actions-runner.py'
            runner.write_text(step['run'])
            result = subprocess.run([sys.executable, str(runner)], cwd=root,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr.count('Ran 1 test'), 1, result.stderr)


if __name__ == '__main__':
    unittest.main()
