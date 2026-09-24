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

    def test_production_and_unspecified_deployments_remain_image_only(self):
        image = 'ghcr.io/org/app@sha256:' + 'a' * 64
        for environment in (None, 'production'):
            with self.subTest(environment=environment):
                commands = deploy.deployment_commands(image, environment=environment)
                combined = '\n'.join(commands)
                self.assertIn(f'docker pull {image}', combined)
                self.assertIn('docker compose up -d --no-deps --wait --wait-timeout 300 app', combined)
                self.assertNotIn('pairroom-observability', combined)
                self.assertNotIn('PAIRROOM_TELEMETRY_ENABLED', combined)
                self.assertNotIn('OTEL_', combined)

    def test_normal_ci_uses_image_only_deployment_without_telemetry(self):
        repository = Path(__file__).resolve().parents[4]
        development = (repository / '.github/workflows/cicd.yaml').read_text(encoding='utf-8')
        production = (repository / '.github/workflows/promote-production.yaml').read_text(encoding='utf-8')
        deploy_step = development.split('      - name: Deploy and verify public health endpoint', 1)[1]
        deploy_step = deploy_step.split('      - name: Record verified development version', 1)[0]
        self.assertNotIn('PAIRROOM_DEPLOY_ENVIRONMENT', deploy_step)
        self.assertNotIn('PAIRROOM_DEPLOY_ENVIRONMENT', production)

        image = 'ghcr.io/org/app@sha256:' + 'a' * 64
        commands = deploy.deployment_commands(image)
        combined = '\n'.join(commands)
        self.assertIn(f'docker pull {image}', combined)
        self.assertIn('docker compose up -d --no-deps --wait --wait-timeout 300 app', combined)
        self.assertNotIn('pairroom-observability', combined)
        self.assertNotIn('PAIRROOM_TELEMETRY_ENABLED', combined)
        self.assertNotIn('OTEL_', combined)

    def test_rejects_unknown_deployment_environment(self):
        with self.assertRaises(ValueError):
            deploy.deployment_commands('ghcr.io/org/app@sha256:' + 'a' * 64,
                                       environment='staging')

    def test_development_config_uses_digest_and_private_docker_network(self):
        image = 'ghcr.io/org/app@sha256:' + 'a' * 64
        override = deploy._development_override(image)
        self.assertIn(f'service.version=sha256:{"a" * 64}', override)
        self.assertIn('deployment.environment.name=development', override)
        self.assertIn('OTEL_SERVICE_NAME: "pairroom-backend"', override)
        self.assertIn('OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4318"', override)
        self.assertIn('      - telemetry\n', override)
        self.assertIn('name: pairroom-telemetry', override)
        self.assertNotIn('ports:', override)

    def test_development_starts_only_committed_observability_config_before_app(self):
        image = 'ghcr.io/org/app@sha256:' + 'a' * 64
        commands = deploy.deployment_commands(image, environment='development')
        combined = '\n'.join(commands)
        obs_start = commands.index('docker compose up -d --wait --wait-timeout 180')
        app_update = next(index for index, command in enumerate(commands)
                          if 'docker compose up -d --no-deps --wait --wait-timeout 300 app' in command)
        self.assertLess(obs_start, app_update)
        self.assertIn('openssl rand -hex 32 > .secrets/grafana-admin-password.tmp', combined)
        self.assertIn('chmod 600 .secrets/grafana-admin-password.tmp', combined)
        self.assertNotIn('cat .secrets/grafana-admin-password', combined)
        self.assertIn('docker pull ' + image, combined)
        self.assertIn('host_memory_kib" -ge 3500000', combined)
        self.assertIn('Development observability requires a 4 GiB host', combined)
        guard = combined.index('test "$host_memory_kib" -ge 3500000')
        self.assertLess(guard, combined.index('docker pull ' + image))
        self.assertLess(guard, combined.index('docker compose up -d --wait --wait-timeout 180'))
        self.assertIn('docker compose ps -q app', combined)
        self.assertIn('docker compose up -d --no-deps --wait --wait-timeout 300 app', combined)
        self.assertIn('compose.override.yaml.previous', combined)
        self.assertIn('rollback_deployment EXIT', combined)
        self.assertNotIn('docker compose down', combined)
        self.assertNotIn('--volumes', combined)
        self.assertNotIn('postgres-data', combined)
        self.assertNotIn('docker compose up -d --no-deps --wait --wait-timeout 300 postgres', combined)
        self.assertLessEqual(max(map(len, commands)), 4096)

    def test_observability_startup_failure_stops_before_pairroom_update(self):
        bash = ('C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash'))
        self.assertTrue(bash and Path(bash).exists(), 'Bash is required for startup rollback validation')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'source'
            for relative in deploy.OBSERVABILITY_FILES:
                source = root / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('fixture: true\n', encoding='utf-8')
            host = './host'
            commands = deploy._observability_stack_commands(root)
            script = '\n'.join(commands).replace('/opt/pairroom-observability', host)
            stubs = r'''
set -eu
export PATH=/usr/bin:/bin:$PATH
install() {
  local target
  for target in "$@"; do :; done
  mkdir -p "$target"
}
openssl() { printf 'temporary-test-password'; }
docker() {
  printf 'docker %s\n' "$*" >> calls
  if [ "$1" = compose ] && [ "$2" = up ]; then return 1; fi
}
'''
            result = subprocess.run([bash, '-c', stubs + '\n' + script], cwd=temp,
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0, result.stderr)
            calls_path = Path(temp) / 'host' / 'calls'
            self.assertTrue(calls_path.exists(), result.stderr)
            calls = calls_path.read_text(encoding='utf-8')
            self.assertIn('docker compose config --quiet', calls)
            self.assertIn('docker compose up -d --wait --wait-timeout 180', calls)
            self.assertNotIn('app', calls)
            self.assertNotIn('postgres', calls)
            self.assertNotIn('down', calls)
            self.assertNotIn('temporary-test-password', result.stdout + result.stderr)

    def test_only_observability_allowlist_is_copied_and_no_local_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in deploy.OBSERVABILITY_FILES:
                source = root / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(f'fixture: {relative}\n', encoding='utf-8')
            commands = deploy._observability_stack_commands(root)
        combined = '\n'.join(commands)
        for relative in deploy.OBSERVABILITY_FILES:
            self.assertIn('/opt/pairroom-observability/' + relative, combined)
        for excluded in ('.env', '.validation', 'verify.py', 'compose.pairroom.yaml'):
            self.assertNotIn(excluded, combined)
        self.assertLessEqual(max(map(len, commands)), 4096)

    def test_failed_app_update_restores_previous_override_without_touching_database(self):
        image = 'ghcr.io/org/app@sha256:' + 'a' * 64
        commands = deploy._development_app_update_commands(image)
        bash = ('C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash'))
        self.assertTrue(bash and Path(bash).exists(), 'Bash is required for rollback validation')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'compose.override.yaml').write_text('old-image: preserved\n', encoding='utf-8')
            stubs = r'''
set -eu
export PATH=/usr/bin:/bin:$PATH
systemctl() { :; }
docker() {
  printf 'docker %s\n' "$*" >> calls
  if [ "$1" = compose ] && [ "$2" = ps ]; then echo app-id; return 0; fi
  if [ "$1" = compose ] && [ "$2" = up ]; then
    count=0
    [ ! -f up-count ] || count=$(cat up-count)
    count=$((count + 1))
    printf '%s' "$count" > up-count
    [ "$count" -ne 1 ]
    return
  fi
  if [ "$1" = inspect ]; then printf '%s\n' 'ghcr.io/org/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'; fi
}
'''
            result = subprocess.run([bash, '-c', stubs + '\n'.join(commands)],
                                    cwd=folder, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((folder / 'compose.override.yaml').read_text(encoding='utf-8'),
                             'old-image: preserved\n')
            calls = (folder / 'calls').read_text(encoding='utf-8')
            self.assertIn('docker compose up -d --no-deps --wait --wait-timeout 300 app', calls)
            self.assertNotIn('postgres', calls)
            self.assertFalse((folder / 'compose.override.yaml.previous').exists())

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
