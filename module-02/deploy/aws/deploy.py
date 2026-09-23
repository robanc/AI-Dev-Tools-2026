"""Update the existing EC2 Compose app via SSM, then check its public health."""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request


def aws(*args):
    result = subprocess.run(
        ['aws', *args, '--output', 'json'], check=True, capture_output=True, text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def deployment_commands(image):
    if not re.fullmatch(r'ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}', image):
        raise ValueError('Deployment requires an immutable GHCR image digest')
    # The override survives reboots; leave bootstrap Compose, .env and volumes intact.
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
        'docker compose up -d --no-deps --wait --wait-timeout 300 app',
        f'test "$(docker inspect --format \'{{{{.Config.Image}}}}\' '
        f'"$(docker compose ps -q app)")" = "{image}"',
    ]


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
    commands = deployment_commands(os.environ['DEPLOY_IMAGE'])
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
