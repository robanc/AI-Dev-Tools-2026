"""Record a verified development deployment or resolve it for manual promotion.

Resolution performs read-only GitHub API calls via gh (available on hosted runners).
It never builds an image or calls AWS. Only metadata from a successful main CI
run's latest attempt is accepted; artifact contents are data, never executed.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

REPOSITORY = 'robanc/AI-Dev-Tools-2026'
WORKFLOW = '.github/workflows/cicd.yaml'
IMAGE_PATTERN = r'ghcr\.io/robanc/ai-dev-tools-2026@sha256:[a-f0-9]{64}'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def positive_id(value):
    require(re.fullmatch(r'[1-9][0-9]*', str(value)) is not None, 'Invalid run ID or attempt')
    return int(value)


def check_image(image):
    require(isinstance(image, str) and re.fullmatch(IMAGE_PATTERN, image) is not None,
            'Expected this repository\'s immutable GHCR digest')
    return image


def record(environ):
    require(environ['GITHUB_REPOSITORY'] == REPOSITORY, 'Wrong repository')
    require(environ['GITHUB_REF'] == 'refs/heads/main', 'Development must use main')
    require(environ['GITHUB_EVENT_NAME'] in {'push', 'workflow_dispatch'}, 'Wrong event')
    sha = environ['GITHUB_SHA']
    require(re.fullmatch(r'[a-f0-9]{40}', sha) is not None, 'Invalid commit SHA')
    return dict(schema_version=1, repository=REPOSITORY, environment='development',
                workflow=WORKFLOW, run_id=positive_id(environ['GITHUB_RUN_ID']),
                run_attempt=positive_id(environ['GITHUB_RUN_ATTEMPT']), commit_sha=sha,
                image=check_image(environ['DEPLOY_IMAGE']))


def validate_run(run, run_id):
    require(run['id'] == run_id, 'Wrong source run')
    require(run['repository']['full_name'] == REPOSITORY and
            run['head_repository']['full_name'] == REPOSITORY, 'Wrong source repository')
    require(run['path'] == WORKFLOW, 'Wrong source workflow')
    require(run['head_branch'] == 'main', 'Source run must use main')
    require(run['event'] in {'push', 'workflow_dispatch'}, 'Untrusted source event')
    require(run['status'] == 'completed' and run['conclusion'] == 'success',
            'Source run must have completed successfully')
    positive_id(run['run_attempt'])


def validate_metadata(metadata, run):
    require(isinstance(metadata, dict), 'Promotion metadata must be an object')
    expected = dict(schema_version=1, repository=REPOSITORY, environment='development',
                    workflow=WORKFLOW, run_id=run['id'], run_attempt=run['run_attempt'],
                    commit_sha=run['head_sha'])
    for key, value in expected.items():
        require(type(metadata.get(key)) is type(value) and metadata[key] == value,
                f'Promotion metadata mismatch: {key}')
    require(re.fullmatch(r'[a-f0-9]{40}', metadata['commit_sha']) is not None, 'Invalid SHA')
    return check_image(metadata.get('image'))


def api(path, paginate=False):
    args = ['gh', 'api', f'repos/{REPOSITORY}/{path}']
    if paginate:
        args += ['--paginate', '--slurp']
    return subprocess.run(args, check=True, capture_output=True, timeout=60).stdout


def pages(path, key):
    return [item for page in json.loads(api(path, paginate=True)) for item in page[key]]


def read_record(archive, digest):
    require(isinstance(digest, str) and
            re.fullmatch(r'sha256:[a-f0-9]{64}', digest) is not None,
            'Artifact has no valid integrity digest')
    require('sha256:' + hashlib.sha256(archive).hexdigest() == digest,
            'Artifact integrity check failed')
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        require(bundle.namelist() == ['promotion.json'], 'Unexpected artifact contents')
        require(bundle.getinfo('promotion.json').file_size <= 16384, 'Oversized metadata')
        return json.loads(bundle.read('promotion.json'))


def resolve(run_id):
    run_id = positive_id(run_id)
    path = f'actions/runs/{run_id}'
    run = json.loads(api(path))
    validate_run(run, run_id)
    attempt = run['run_attempt']
    jobs = pages(f'{path}/attempts/{attempt}/jobs?per_page=100', 'jobs')
    deploy_jobs = [job for job in jobs if job['name'] == 'deploy']
    require(len(deploy_jobs) == 1 and deploy_jobs[0]['conclusion'] == 'success',
            'Development deployment job must succeed in this attempt')
    artifacts = pages(f'{path}/artifacts?per_page=100', 'artifacts')
    matches = [a for a in artifacts if a['name'] == f'development-promotion-{attempt}']
    require(len(matches) == 1 and matches[0]['expired'] is False,
            'Missing, duplicate, or expired promotion artifact')
    artifact = matches[0]
    artifact_id = positive_id(artifact['id'])
    require(artifact['size_in_bytes'] <= 65536, 'Oversized promotion artifact')
    metadata = read_record(api(f'actions/artifacts/{artifact_id}/zip'), artifact.get('digest'))
    image = validate_metadata(metadata, run)
    # Fail if a rerun began while we were reading its previous attempt's record.
    latest = json.loads(api(path))
    validate_run(latest, run_id)
    require(latest['run_attempt'] == attempt and latest['head_sha'] == run['head_sha'],
            'Source run changed during validation')
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    writer = commands.add_parser('record')
    writer.add_argument('--output', required=True)
    reader = commands.add_parser('resolve')
    reader.add_argument('--run-id', required=True)
    reader.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'record':
        Path(args.output).write_text(json.dumps(record(os.environ)) + '\n', encoding='utf-8')
    else:
        require(os.environ['GITHUB_REPOSITORY'] == REPOSITORY and
                os.environ['GITHUB_REF'] == 'refs/heads/main' and
                os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch',
                'Production promotion must be manually dispatched from main')
        image = resolve(args.run_id)
        with open(args.output, 'a', encoding='utf-8') as output:
            output.write(f'DEPLOY_IMAGE={image}\n')
        print(f'Validated development run {args.run_id}: {image}')


if __name__ == '__main__':
    main()
