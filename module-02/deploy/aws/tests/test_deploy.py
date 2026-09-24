import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
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
        self.assertIn('docker compose up -d --no-deps --wait --wait-timeout 300 app', '\n'.join(commands))

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


class BootstrapLifecycleTests(unittest.TestCase):
    """Execute actual shell fragments with fake Docker/systemd, in a temporary host directory."""

    def setUp(self):
        self.bash = ('C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash'))
        if not self.bash or not Path(self.bash).exists():
            self.fail('Bash is required for bootstrap lifecycle validation')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.template = (Path(__file__).parents[1] / 'cloudformation.yaml').read_text()
        self.script = textwrap.dedent(self.template.split('Fn::Base64: !Sub |\n', 1)[1].split('\nOutputs:', 1)[0])
        self.image = 'ghcr.io/org/app@sha256:' + 'a' * 64
        self.stubs = '''
set -eu
export PATH=/usr/bin:/bin:$PATH
systemctl() { printf 'systemctl %s\\n' "$*" >> calls; }
docker() {
  printf 'docker %s\\n' "$*" >> calls
  case "$1" in
    inspect) printf '%s\\n' "IMAGE" ;;
    compose) if [ "$2" = ps ]; then printf 'app-id\\n'; fi ;;
  esac
}
flock() { :; }
'''.replace('IMAGE', self.image)

    def run_shell(self, script, success=True):
        result = subprocess.run([self.bash, '-c', self.stubs + script], cwd=self.folder,
                                capture_output=True, text=True, timeout=15)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return (self.folder / 'calls').read_text() if (self.folder / 'calls').exists() else ''

    def bootstrap(self, mode):
        # Execute the actual final startup decision, with paths confined to the fixture.
        script = self.script[self.script.index('systemctl daemon-reload'):]
        return self.run_shell(script.replace('${StartPairRoomOnBootstrap}', mode)
                             .replace('/opt/pairroom/', './'))

    def deployment(self):
        return '\n'.join(deploy.deployment_commands(self.image)).replace('/opt/pairroom', '.')

    def test_default_still_starts_service(self):
        parameter = self.template.split('  StartPairRoomOnBootstrap:\n', 1)[1].split('  InstanceProfileName:', 1)[0]
        self.assertIn("Default: 'true'", parameter)
        calls = self.bootstrap('true')
        self.assertIn('systemctl enable --now pairroom.service', calls)
        self.assertTrue((self.folder / 'bootstrap-complete').exists())
        self.assertFalse((self.folder / 'initial-deployment-pending').exists())

    def test_full_user_data_shell_syntax_in_both_modes(self):
        for mode in ['true', 'false']:
            script = (self.script.replace('${StartPairRoomOnBootstrap}', mode)
                      .replace('${AppImage}', self.image).replace('${!', '${'))
            result = subprocess.run([self.bash, '-n'], input=script, capture_output=True,
                                    text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_idle_bootstrap_does_not_enable_or_start_pairroom(self):
        calls = self.bootstrap('false')
        self.assertEqual(calls.strip(), 'systemctl daemon-reload')
        self.assertTrue((self.folder / 'initial-deployment-pending').exists())
        self.assertTrue((self.folder / 'bootstrap-complete').exists())
        self.assertIn('systemctl enable --now amazon-ssm-agent', self.script)

    def test_first_promotion_starts_service_after_digest_override(self):
        self.bootstrap('false')
        # The service must see the approved digest, never the bootstrap image.
        script = '''
systemctl() {
  test -f compose.override.yaml
  grep -q 'sha256:' compose.override.yaml
  printf 'systemctl %s\\n' "$*" >> calls
}
''' + self.deployment()
        calls = self.run_shell(script)
        self.assertIn('systemctl enable --now pairroom.service', calls)
        self.assertNotIn('docker compose up', calls)
        self.assertIn(self.image, (self.folder / 'compose.override.yaml').read_text())
        self.assertFalse((self.folder / 'initial-deployment-pending').exists())

    def test_failed_initial_start_keeps_marker_for_retry(self):
        self.bootstrap('false')
        self.run_shell('systemctl() { return 1; }\n' + self.deployment(), success=False)
        self.assertTrue((self.folder / 'initial-deployment-pending').exists())
        self.run_shell(self.deployment())
        self.assertFalse((self.folder / 'initial-deployment-pending').exists())

    def test_existing_host_updates_only_app_and_preserves_data(self):
        (self.folder / 'bootstrap-complete').touch()
        (self.folder / '.env').write_text('unchanged-fixture')
        (self.folder / 'database-fixture').write_text('unchanged-data')
        calls = self.run_shell(self.deployment())
        self.assertIn('docker compose up -d --no-deps --wait --wait-timeout 300 app', calls)
        self.assertNotIn('systemctl', calls)
        self.assertEqual((self.folder / '.env').read_text(), 'unchanged-fixture')
        self.assertEqual((self.folder / 'database-fixture').read_text(), 'unchanged-data')

    def test_start_service_sets_origin_and_starts_dependencies(self):
        script = self.script.split("<<'START'\n", 1)[1].split('\nSTART', 1)[0]
        script = script.replace('/opt/pairroom', '.')
        (self.folder / '.env').write_text('POSTGRES_PASSWORD=fixture\n')
        calls = self.run_shell('curl() { printf "203.0.113.10\\n"; }\n' + script)
        self.assertIn('FRONTEND_ORIGINS=http://203.0.113.10', (self.folder / '.env').read_text())
        self.assertIn('docker compose up -d --wait --wait-timeout 300', calls)


if __name__ == '__main__':
    unittest.main()
