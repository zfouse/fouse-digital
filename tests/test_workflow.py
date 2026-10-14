"""Exercise ledger loading with a fake Git transport; no remote writes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class LedgerLoadingTests(unittest.TestCase):
    def test_transport_failure_cannot_initialize_empty_ledger(self):
        workflow = (Path(__file__).parents[1] / '.github/workflows/prospecting.yml').read_text()
        block = workflow.split('      - name: Load durable ledger\n        run: |\n', 1)[1].split('      - name:', 1)[0]
        script = '\n'.join(line[10:] for line in block.splitlines())
        with tempfile.TemporaryDirectory() as root:
            fake_git = Path(root) / 'git'
            fake_git.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit 128\n')
            fake_git.chmod(0o755)
            log = Path(root) / 'calls'
            env = dict(os.environ, PATH=root + ':' + os.environ['PATH'], RUNNER_TEMP=root, CALL_LOG=str(log))
            result = subprocess.run(['bash', '-e', '-c', script], env=env, cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 128)
            self.assertEqual(log.read_text().splitlines(), ['ls-remote --heads origin prospect-ledger'])
