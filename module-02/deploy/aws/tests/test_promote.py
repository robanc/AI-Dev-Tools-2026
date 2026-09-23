import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('promote', Path(__file__).parents[1] / 'promote.py')
promote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promote)
IMAGE = 'ghcr.io/robanc/ai-dev-tools-2026@sha256:' + 'a' * 64


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(GITHUB_REPOSITORY=promote.REPOSITORY, GITHUB_REF='refs/heads/main',
                        GITHUB_EVENT_NAME='push', GITHUB_SHA='b' * 40,
                        GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='2', DEPLOY_IMAGE=IMAGE)
        self.record = promote.record(self.env)
        self.run = dict(id=123, repository={'full_name': promote.REPOSITORY},
                        head_repository={'full_name': promote.REPOSITORY},
                        path=promote.WORKFLOW, head_branch='main', event='push',
                        status='completed', conclusion='success', run_attempt=2,
                        head_sha='b' * 40)
        self.archive = self.zip_record(self.record)
        self.artifact = dict(id=456, name='development-promotion-2', expired=False,
                             size_in_bytes=len(self.archive),
                             digest='sha256:' + hashlib.sha256(self.archive).hexdigest())
        self.jobs = [{'name': 'deploy', 'conclusion': 'success'}]

    @staticmethod
    def zip_record(record, name='promotion.json'):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as bundle:
            bundle.writestr(name, json.dumps(record))
        return output.getvalue()

    def responses(self):
        return [json.dumps(self.run).encode(), json.dumps([{'jobs': self.jobs}]).encode(),
                json.dumps([{'artifacts': [self.artifact]}]).encode(), self.archive,
                json.dumps(self.run).encode()]

    def test_resolve_exact_digest_and_attempt_specific_job(self):
        with patch.object(promote, 'api', side_effect=self.responses()) as api:
            self.assertEqual(promote.resolve('123'), IMAGE)
        self.assertIn('attempts/2/jobs', api.call_args_list[1].args[0])

    def test_accepts_manual_development_run(self):
        self.run['event'] = 'workflow_dispatch'
        with patch.object(promote, 'api', side_effect=self.responses()):
            self.assertEqual(promote.resolve('123'), IMAGE)

    def test_rejects_invalid_run_ids_before_api(self):
        for value in ['0', '-1', '12/../34', '123\n', '1; reboot', '', '1.0', True]:
            with self.subTest(value=value), patch.object(promote, 'api') as api:
                with self.assertRaises(ValueError):
                    promote.resolve(value)
                api.assert_not_called()

    def test_source_run_rejections(self):
        changes = {'id': 999, 'repository': {'full_name': 'other/repo'},
                   'head_repository': {'full_name': 'fork/repo'}, 'path': 'other.yaml',
                   'head_branch': 'feature', 'event': 'pull_request',
                   'status': 'in_progress', 'conclusion': 'failure', 'run_attempt': 0}
        for key, value in changes.items():
            with self.subTest(key=key):
                run = {**self.run, key: value}
                with self.assertRaises(ValueError):
                    promote.validate_run(run, 123)
        for conclusion in ['cancelled', 'skipped', 'timed_out', None]:
            with self.subTest(conclusion=conclusion), self.assertRaises(ValueError):
                promote.validate_run({**self.run, 'conclusion': conclusion}, 123)

    def test_requires_successful_deployment_job(self):
        for jobs in [[], [{'name': 'deploy', 'conclusion': 'skipped'}],
                     [{'name': 'deploy', 'conclusion': 'failure'}],
                     [{'name': 'other', 'conclusion': 'success'}], self.jobs * 2]:
            self.jobs = jobs
            with self.subTest(jobs=jobs), patch.object(promote, 'api', side_effect=self.responses()):
                with self.assertRaises(ValueError):
                    promote.resolve('123')

    def test_artifact_rejections(self):
        for change in [dict(expired=True), dict(name='development-promotion-1'),
                       dict(size_in_bytes=65537), dict(digest=None), dict(digest='sha256:' + '0' * 64)]:
            with self.subTest(change=change):
                responses = self.responses()
                responses[2] = json.dumps([{'artifacts': [{**self.artifact, **change}]}]).encode()
                with patch.object(promote, 'api', side_effect=responses), self.assertRaises(ValueError):
                    promote.resolve('123')
        for artifacts in [[], [self.artifact, self.artifact]]:
            responses = self.responses()
            responses[2] = json.dumps([{'artifacts': artifacts}]).encode()
            with patch.object(promote, 'api', side_effect=responses), self.assertRaises(ValueError):
                promote.resolve('123')

    def test_metadata_must_match_run(self):
        for key, value in dict(schema_version=2, repository='other/repo', environment='production',
                               workflow='other.yaml', run_id=999, run_attempt=1,
                               commit_sha='c' * 40).items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                promote.validate_metadata({**self.record, key: value}, self.run)
        for key in self.record:
            record = self.record.copy()
            del record[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                promote.validate_metadata(record, self.run)
        with self.assertRaises(ValueError):
            promote.validate_metadata({**self.record, 'schema_version': True}, self.run)

    def test_rejects_tags_other_images_and_injection(self):
        for image in ['ghcr.io/robanc/ai-dev-tools-2026:latest',
                      IMAGE.replace('robanc', 'attacker'), IMAGE + '\nAWS_REGION=evil',
                      IMAGE + '; reboot', IMAGE[:-1], None, 42]:
            with self.subTest(image=image), self.assertRaises(ValueError):
                promote.validate_metadata({**self.record, 'image': image}, self.run)

    def test_record_rejects_wrong_context(self):
        for key, value in dict(GITHUB_REPOSITORY='other/repo', GITHUB_REF='refs/heads/feature',
                               GITHUB_EVENT_NAME='pull_request', GITHUB_SHA='bad',
                               GITHUB_RUN_ID='0', GITHUB_RUN_ATTEMPT='0', DEPLOY_IMAGE='latest').items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                promote.record({**self.env, key: value})

    def test_rerun_race_fails_closed(self):
        for change in [dict(run_attempt=3), dict(status='in_progress'), dict(head_sha='c' * 40)]:
            responses = self.responses()
            responses[-1] = json.dumps({**self.run, **change}).encode()
            with self.subTest(change=change), patch.object(promote, 'api', side_effect=responses):
                with self.assertRaises(ValueError):
                    promote.resolve('123')

    def test_archive_is_never_extracted_and_rejects_unexpected_files(self):
        for name in ['../promotion.json', '/promotion.json', 'other.json']:
            archive = self.zip_record(self.record, name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                promote.read_record(archive, 'sha256:' + hashlib.sha256(archive).hexdigest())
        archive = self.zip_record({'padding': 'x' * 20000})
        with self.assertRaises(ValueError):
            promote.read_record(archive, 'sha256:' + hashlib.sha256(archive).hexdigest())

    def test_api_failures_propagate(self):
        with patch.object(promote, 'api', side_effect=subprocess.CalledProcessError(1, 'gh')):
            with self.assertRaises(subprocess.CalledProcessError):
                promote.resolve('123')

    def test_api_uses_read_only_calls_and_preserves_binary_archive(self):
        with patch.object(promote.subprocess, 'run') as run:
            run.return_value.stdout = self.archive
            self.assertEqual(promote.api('actions/artifacts/456/zip'), self.archive)
            run.assert_called_once_with(
                ['gh', 'api', 'repos/robanc/AI-Dev-Tools-2026/actions/artifacts/456/zip'],
                check=True, capture_output=True, timeout=60)

    def test_corrupt_archive_or_json_is_rejected(self):
        for archive in [b'not a zip', self.zip_record(None), self.zip_record([])]:
            responses = self.responses()
            artifact = {**self.artifact, 'digest': 'sha256:' + hashlib.sha256(archive).hexdigest()}
            responses[2] = json.dumps([{'artifacts': [artifact]}]).encode()
            responses[3] = archive
            with self.subTest(archive=archive[:20]), patch.object(promote, 'api', side_effect=responses):
                with self.assertRaises((ValueError, zipfile.BadZipFile)):
                    promote.resolve('123')

    def test_pagination_includes_all_pages(self):
        with patch.object(promote, 'api', return_value=b'[{"jobs":[1]},{"jobs":[2]}]'):
            self.assertEqual(promote.pages('path', 'jobs'), [1, 2])

    def test_failed_resolution_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'env'
            env = {**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch'}
            with patch.dict(os.environ, env), patch('sys.argv', ['promote', 'resolve',
                            '--run-id', '123', '--output', str(output)]):
                with patch.object(promote, 'resolve', side_effect=ValueError('failed')):
                    with self.assertRaises(ValueError):
                        promote.main()
            self.assertFalse(output.exists())

    def test_cli_records_and_writes_only_validated_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'record'
            with patch.dict(os.environ, self.env), patch('sys.argv', ['promote', 'record',
                            '--output', str(output)]):
                promote.main()
            self.assertEqual(json.loads(output.read_text()), self.record)
            output = Path(directory) / 'env'
            env = {**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch'}
            with patch.dict(os.environ, env), patch('sys.argv', ['promote', 'resolve',
                            '--run-id', '123', '--output', str(output)]):
                with patch.object(promote, 'api', side_effect=self.responses()):
                    promote.main()
            self.assertEqual(output.read_text(), f'DEPLOY_IMAGE={IMAGE}\n')

    def test_promotion_requires_manual_main_context(self):
        for change in [dict(GITHUB_REF='refs/heads/feature'), dict(GITHUB_EVENT_NAME='push'),
                       dict(GITHUB_REPOSITORY='other/repo')]:
            env = {**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch', **change}
            with patch.dict(os.environ, env), patch('sys.argv', ['promote', 'resolve',
                            '--run-id', '123', '--output', 'unused']):
                with patch.object(promote, 'resolve') as resolve, self.assertRaises(ValueError):
                    promote.main()
                resolve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
