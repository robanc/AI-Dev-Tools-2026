"""Update the existing EC2 Compose app via SSM, then check its public health."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request


OBSERVABILITY_FILES = (
    'compose.yaml',
    'collector.yaml',
    'prometheus.yaml',
    'alerts.yaml',
    'alerts.test.yaml',
    'loki.yaml',
    'tempo.yaml',
    'grafana/provisioning/datasources/datasources.yaml',
)
OBSERVABILITY_DIRECTORY = Path(__file__).resolve().parents[2] / 'observability'
OBSERVABILITY_HOST_DIRECTORY = '/opt/pairroom-observability'
TELEMETRY_NETWORK = 'pairroom-telemetry'


def aws(*args):
    result = subprocess.run(
        ['aws', *args, '--output', 'json'], check=True, capture_output=True, text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def _standard_deployment_commands(image):
    """Keep production promotion and unspecified deployments image-only."""
    return [
        'set -eu',
        'test -f /opt/pairroom/bootstrap-complete',
        'cd /opt/pairroom',
        'exec 9>/opt/pairroom/deploy.lock',
        'flock -w 600 9',
        f'docker pull {image}',
        "printf '%s\\n' 'services:' '  app:' '    image: " + image
        + "' > compose.override.yaml.tmp",
        'mv compose.override.yaml.tmp compose.override.yaml',
        'if [ -f initial-deployment-pending ]; then\n'
        '  systemctl enable --now pairroom.service\n'
        '  rm initial-deployment-pending\n'
        'else\n'
        '  docker compose up -d --no-deps --wait --wait-timeout 300 app\n'
        'fi',
        f'test "$(docker inspect --format \'{{{{.Config.Image}}}}\' '
        f'"$(docker compose ps -q app)")" = "{image}"',
    ]


def _observability_stack_commands(source_directory=None):
    """Copy only committed, non-secret stack configuration through SSM."""
    source_directory = Path(source_directory or OBSERVABILITY_DIRECTORY)
    host_directory = OBSERVABILITY_HOST_DIRECTORY
    commands = [
        f'install -d -m 755 {host_directory}/grafana/provisioning/datasources',
        f'install -d -m 700 {host_directory}/.secrets',
    ]
    for relative_path in OBSERVABILITY_FILES:
        source = source_directory / relative_path
        destination = f'{host_directory}/{relative_path}'
        encoded = base64.b64encode(source.read_bytes()).decode('ascii')
        commands.append(
            f"printf '%s' '{encoded}' | base64 -d > '{destination}.tmp' "
            f"&& chmod 644 '{destination}.tmp' && mv '{destination}.tmp' '{destination}'"
        )
    commands.extend([
        # Create the password only on the host. Never emit it to SSM output/logs.
        'cd /opt/pairroom-observability',
        'if [ ! -s .secrets/grafana-admin-password ]; then\n'
        '  umask 077\n'
        '  openssl rand -hex 32 > .secrets/grafana-admin-password.tmp\n'
        '  chmod 600 .secrets/grafana-admin-password.tmp\n'
        '  mv .secrets/grafana-admin-password.tmp .secrets/grafana-admin-password\n'
        'fi',
        'docker compose config --quiet',
        'docker compose up -d --wait --wait-timeout 180',
        'cd /opt/pairroom',
    ])
    return commands


def _development_override(image):
    version = image.rsplit('@', 1)[1]
    return '\n'.join((
        'services:',
        '  app:',
        f'    image: "{image}"',
        '    environment:',
        '      PAIRROOM_TELEMETRY_ENABLED: "true"',
        '      OTEL_SERVICE_NAME: "pairroom-backend"',
        '      OTEL_RESOURCE_ATTRIBUTES: '
        f'"deployment.environment.name=development,service.version={version}"',
        '      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4318"',
        '    networks:',
        '      - default',
        '      - telemetry',
        'networks:',
        '  telemetry:',
        '    external: true',
        f'    name: {TELEMETRY_NETWORK}',
        '',
    ))


def _development_app_update_commands(image):
    override = _development_override(image)
    return [
        'had_previous_override=false',
        'if [ -f compose.override.yaml ]; then\n'
        '  cp -p compose.override.yaml compose.override.yaml.previous\n'
        '  had_previous_override=true\n'
        'fi',
        'app_was_running=false',
        'if [ -n "$(docker compose ps -q app)" ]; then app_was_running=true; fi',
        'rollback_deployment() {\n'
        '  status=$?\n'
        '  trap - EXIT\n'
        '  if [ "$status" -ne 0 ]; then\n'
        '    if [ "$had_previous_override" = true ]; then\n'
        '      mv -f compose.override.yaml.previous compose.override.yaml '
        '|| echo "Could not restore the previous app override." >&2\n'
        '    else\n'
        '      rm -f compose.override.yaml || echo "Could not remove the failed app override." >&2\n'
        '    fi\n'
        '    rm -f compose.override.yaml.tmp\n'
        '    if [ "$app_was_running" = true ]; then\n'
        '      docker compose up -d --no-deps --wait --wait-timeout 300 app '
        '|| echo "App rollback failed; inspect the PairRoom Compose project." >&2\n'
        '    fi\n'
        '  else\n'
        '    rm -f compose.override.yaml.previous compose.override.yaml.tmp\n'
        '  fi\n'
        '  exit "$status"\n'
        '}',
        'trap rollback_deployment EXIT',
        "cat > compose.override.yaml.tmp <<'PAIRROOM_OVERRIDE'\n"
        + override + 'PAIRROOM_OVERRIDE',
        'chmod 600 compose.override.yaml.tmp',
        'mv compose.override.yaml.tmp compose.override.yaml',
        'if [ -f initial-deployment-pending ]; then\n'
        '  systemctl enable --now pairroom.service\n'
        '  rm initial-deployment-pending\n'
        'else\n'
        '  docker compose up -d --no-deps --wait --wait-timeout 300 app\n'
        'fi',
        'app_id="$(docker compose ps -q app)"',
        'test -n "$app_id"',
        f'test "$(docker inspect --format \'{{{{.Config.Image}}}}\' "$app_id")" = "{image}"',
        "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"$app_id\" "
        "| grep -Fx 'PAIRROOM_TELEMETRY_ENABLED=true'",
        "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"$app_id\" "
        "| grep -Fx 'OTEL_SERVICE_NAME=pairroom-backend'",
        "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"$app_id\" "
        f"| grep -Fx 'OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=development,service.version={image.rsplit('@', 1)[1]}'",
        "docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"$app_id\" "
        "| grep -Fx 'OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318'",
        'trap - EXIT',
        'rm -f compose.override.yaml.previous',
    ]


def deployment_commands(image, environment=None, observability_directory=None):
    if not re.fullmatch(r'ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}', image):
        raise ValueError('Deployment requires an immutable GHCR image digest')
    if environment not in (None, 'development', 'production'):
        raise ValueError('Deployment environment must be development or production')
    if environment != 'development':
        return _standard_deployment_commands(image)

    commands = [
        'set -eu',
        'test -f /opt/pairroom/bootstrap-complete',
        'cd /opt/pairroom',
        'exec 9>/opt/pairroom/deploy.lock',
        'flock -w 600 9',
        'host_memory_kib="$(awk \'/^MemTotal:/ {print $2}\' /proc/meminfo)"',
        'test "$host_memory_kib" -ge 3500000 || { '
        'echo "Development observability requires a 4 GiB host; resize before deploying." >&2; exit 1; }',
        f'docker pull {image}',
    ]
    commands.extend(_observability_stack_commands(observability_directory))
    commands.extend(_development_app_update_commands(image))
    return commands


def wait_for_command(command_id, instance_id, timeout=720):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = aws('ssm', 'get-command-invocation', '--command-id', command_id,
                         '--instance-id', instance_id)
        except subprocess.CalledProcessError as error:
            if 'InvocationDoesNotExist' not in error.stderr:
                raise
        else:
            status = result['Status']
            if status == 'Success':
                return
            if status not in {'Pending', 'InProgress', 'Delayed'}:
                raise RuntimeError(f'SSM deployment failed: {status}; inspect command {command_id}')
        time.sleep(5)
    raise TimeoutError(f'SSM deployment timed out; inspect command {command_id}')


def wait_for_health(url, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status == 200 and json.load(response) == {'status': 'ok'}:
                    return
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            pass
        time.sleep(5)
    raise TimeoutError(f'Deployment health check failed: {url}')


def main():
    instance = os.environ['AWS_INSTANCE_ID']
    if not re.fullmatch(r'i-[a-f0-9]+', instance):
        raise ValueError('AWS_INSTANCE_ID must identify the existing PairRoom EC2 host')
    commands = deployment_commands(os.environ['DEPLOY_IMAGE'],
                                   os.environ.get('PAIRROOM_DEPLOY_ENVIRONMENT'))
    command = aws('ssm', 'send-command', '--instance-ids', instance,
                  '--document-name', 'AWS-RunShellScript', '--timeout-seconds', '60',
                  '--parameters', json.dumps({'commands': commands, 'executionTimeout': ['660']}))
    command_id = command['Command']['CommandId']
    print(f'Deployment command: {command_id}', flush=True)
    wait_for_command(command_id, instance)
    details = aws('ec2', 'describe-instances', '--instance-ids', instance)
    address = details['Reservations'][0]['Instances'][0]['PublicIpAddress']
    url = f'http://{address}/health'
    wait_for_health(url)
    print(f'Deployment verified: {url}')


if __name__ == '__main__':
    main()
