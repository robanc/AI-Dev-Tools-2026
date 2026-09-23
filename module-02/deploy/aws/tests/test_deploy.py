import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).parents[1] / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploymentTests(unittest.TestCase):
    def test_rejects_tags_and_shell_injection(self):
        for image in ['ghcr.io/org/app:latest', 'bad; echo injected', '',
                      'ghcr.io/org/app@sha256:' + 'a' * 64 + '\nreboot']:
            with self.subTest(image=image), self.assertRaises(ValueError):
                deploy.deployment_commands(image)

    def test_accepts_digest(self):
        commands = deploy.deployment_commands('ghcr.io/org/app@sha256:' + 'a' * 64)
        self.assertIn('docker compose up -d --no-deps --wait --wait-timeout 300 app', commands)

    @patch.object(deploy.time, 'sleep')
    def test_waits_for_ssm_eventual_consistency_and_completion(self, sleep):
        missing = subprocess.CalledProcessError(1, 'aws', stderr='InvocationDoesNotExist')
        with patch.object(deploy, 'aws', side_effect=[missing, {'Status': 'InProgress'},
                                                    {'Status': 'Success'}]):
            deploy.wait_for_command('command', 'instance')

    def test_remote_failure_fails_deploy(self):
        with patch.object(deploy, 'aws', return_value={'Status': 'Failed'}):
            with self.assertRaises(RuntimeError):
                deploy.wait_for_command('command', 'instance')

    @patch.object(deploy.time, 'sleep')
    def test_health_requires_ok_body(self, sleep):
        invalid = io.BytesIO(b'{"status":"error"}')
        invalid.status = 200
        valid = io.BytesIO(b'{"status":"ok"}')
        valid.status = 200
        with patch.object(deploy.urllib.request, 'urlopen', side_effect=[invalid, valid]) as get:
            deploy.wait_for_health('http://example/health')
            self.assertEqual(get.call_count, 2)

    def test_health_timeout_fails_deploy(self):
        with self.assertRaises(TimeoutError):
            deploy.wait_for_health('http://example/health', timeout=0)


if __name__ == '__main__':
    unittest.main()
