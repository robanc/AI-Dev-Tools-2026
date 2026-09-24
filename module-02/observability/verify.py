"""Exercise only the isolated local test app and observability stack; never delete volumes.

Run: uv run --project module-02/backend python module-02/observability/verify.py
Requires both Compose projects running. Restarts only pairroom-observability.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parent
APP = 'http://127.0.0.1:' + os.getenv('PAIRROOM_OBSERVABILITY_PORT', '18100')
VERSION = os.getenv('PAIRROOM_OBSERVABILITY_VERSION', 'observability-local')
OBS = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml')]
TEST = ['docker', 'compose', '-p', 'pairroom-observability-test',
        '-f', str(ROOT.parent / 'docker-compose.yaml'), '-f', str(ROOT / 'compose.pairroom.yaml')]


def request(url, data=None, headers=None, method=None):
    headers = dict(headers or {})
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read()
        return json.loads(body) if 'json' in response.headers.get('Content-Type', '') else body.decode()


def wait(label, action, timeout=180):
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = action()
            assert result is not False
            print(label + ': PASS', flush=True)
            return result
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError(label + ' did not pass before timeout') from None
            time.sleep(3)


def main():
    # Require the dedicated project and its own database volume before generating data.
    config = json.loads(subprocess.check_output(TEST + ['config', '--format', 'json'], text=True))
    assert config['name'] == 'pairroom-observability-test'
    assert config['volumes']['postgres-data']['name'] == 'pairroom-observability-test_postgres-data'
    assert config['services']['app']['ports'][0]['published'] == APP.rsplit(':', 1)[1]
    password_file = Path(os.getenv('GRAFANA_ADMIN_PASSWORD_FILE', str(ROOT / '.secrets/grafana-admin-password')))
    auth = {'Authorization': 'Basic ' + base64.b64encode(
        ('admin:' + password_file.read_text().strip()).encode()).decode()}

    def grafana(path, data=None):
        return request('http://127.0.0.1:3000' + path, data=data, headers=auth)

    def proxy(uid, path):
        return grafana('/api/datasources/proxy/uid/' + uid + path)

    def readiness():
        wait('Grafana database readiness', lambda: grafana('/api/health')['database'] == 'ok')
        for uid, path in [('prometheus', '/-/ready'), ('loki', '/ready'), ('tempo', '/ready')]:
            wait(uid + ' readiness', lambda uid=uid, path=path: proxy(uid, path))
        def collector():
            code = "import urllib.request; assert urllib.request.urlopen('http://otel-collector:13133', timeout=5).status == 200"
            subprocess.run(TEST + ['exec', '-T', 'app', 'python', '-c', code],
                           check=True, capture_output=True, timeout=15)
        wait('Collector readiness', collector)
        for uid in ['prometheus', 'loki', 'tempo']:
            wait('Grafana datasource ' + uid,
                 lambda uid=uid: grafana('/api/datasources/uid/' + uid + '/health')['status'] == 'OK')

    readiness()
    assert request(APP + '/health') == {'status': 'ok'}
    assert 'Pair' in request(APP + '/') or '<html' in request(APP + '/')
    start = time.time_ns()
    marker = 'privacy-' + uuid.uuid4().hex
    link = request(APP + '/sessions', data={})['interviewerLink']
    session_id, token = link.split('/')[2:]
    path = '/sessions/' + session_id
    owner = {'Authorization': 'Bearer ' + token, 'Cookie': marker + '-cookie'}
    candidate_link = request(APP + path, headers=owner)['candidateLink']
    candidate = candidate_link.split('/')[-1]
    secrets = [session_id, token, candidate, marker]
    with connect(APP.replace('http:', 'ws:') + path + '/ws', origin=APP,
                 open_timeout=10) as first, connect(APP.replace('http:', 'ws:') + path + '/ws',
                                                 origin=APP, open_timeout=10) as second:
        first.send(json.dumps({'type': 'authenticate', 'token': token}))
        assert json.loads(first.recv(timeout=5))['type'] == 'snapshot'
        second.send(json.dumps({'type': 'authenticate', 'token': candidate}))
        assert json.loads(second.recv(timeout=5))['type'] == 'snapshot'
        assert json.loads(first.recv(timeout=5))['type'] == 'presence.updated'
        for access in [owner, {'Authorization': 'Bearer ' + candidate}]:
            saved = request(APP + path + '/code?private=' + marker,
                            data={'code': marker}, headers=access, method='PUT')
            for socket in [first, second]:
                event = json.loads(socket.recv(timeout=5))
                assert event['type'] == 'session.updated'
                assert event['session']['revision'] == saved['revision']
        first.send(json.dumps({'type': 'ping'}))
        assert json.loads(first.recv(timeout=5)) == {'type': 'pong'}
    request(APP + path + '/problem', data={'problem': marker}, headers=owner, method='PUT')
    assert request(APP + path, headers=owner)['session']['code'] == marker
    print('PairRoom health, frontend, two-client WebSocket updates, heartbeat, persistence: PASS', flush=True)

    selector = '{service_name="pairroom-backend",deployment_environment_name="local"}'
    metric_query = 'pairroom_sessions_created_total{service_name="pairroom-backend",deployment_environment_name="local",service_version="' + VERSION + '"}'

    def metrics(at=None):
        params = {'query': metric_query}
        if at:
            params['time'] = at
        result = proxy('prometheus', '/api/v1/query?' + urllib.parse.urlencode(params))
        assert result['data']['result']
        return result

    def logs(end=None):
        params = {'query': selector, 'start': str(start), 'end': str(end or time.time_ns()), 'limit': '1000'}
        result = proxy('loki', '/loki/api/v1/query_range?' + urllib.parse.urlencode(params))
        assert result['data']['result']
        return result

    metric_data = wait('Metrics and resource labels', metrics)
    log_data = wait('Structured logs', logs)
    trace_ids = set()
    def traces_from_logs():
        nonlocal log_data
        log_data = logs()
        for stream in log_data['data']['result']:
            assert stream['stream']['service_name'] == 'pairroom-backend'
            assert stream['stream']['deployment_environment_name'] == 'local'
            for value in stream['values']:
                metadata = {**stream['stream'], **(value[2] if len(value) > 2 else {})}
                assert metadata['service_version'] == VERSION
                trace_ids.add(metadata['trace_id'])
        assert trace_ids
    wait('Log version labels and trace correlation', traces_from_logs)
    traces = []
    for trace_id in sorted(trace_ids):
        data = wait('Trace retrieval', lambda trace_id=trace_id: proxy('tempo', '/api/traces/' + trace_id))
        serialized = json.dumps(data)
        assert 'pairroom-backend' in serialized and VERSION in serialized
        assert 'deployment.environment.name' in serialized and 'local' in serialized
        traces.append(data)
    # Scan all emitted PairRoom metrics, not just the session counter.
    all_metrics = proxy('prometheus', '/api/v1/query?' + urllib.parse.urlencode({'query': selector}))
    telemetry_text = json.dumps([all_metrics, log_data, traces])
    assert all(secret not in telemetry_text for secret in secrets), 'Sensitive fixture data exported'
    print('Sensitive-data scan across metrics, logs and correlated traces: PASS', flush=True)

    # Persist an actual user-created Grafana object, not merely reprovisioned datasources.
    folder_uid = 'validation-' + uuid.uuid4().hex[:12]
    grafana('/api/folders', {'uid': folder_uid, 'title': 'Local persistence verification ' + folder_uid})
    end = time.time_ns()
    sample_time = time.time()
    before = metrics(sample_time)
    before_logs = logs(end)
    print('Restarting only pairroom-observability; all volumes retained.', flush=True)
    subprocess.run(OBS + ['restart', '--timeout', '30'], check=True, timeout=180)
    readiness()
    after = wait('Historical metric persistence', lambda: metrics(sample_time))
    assert before['data']['result'] == after['data']['result']
    after_logs = wait('Historical log persistence', lambda: logs(end))
    def entries(data):
        return sorted((value[0], value[1]) for stream in data['data']['result'] for value in stream['values'])
    assert entries(before_logs) == entries(after_logs)
    for trace_id in sorted(trace_ids):
        wait('Trace persistence', lambda trace_id=trace_id: proxy('tempo', '/api/traces/' + trace_id))
    assert grafana('/api/folders/' + folder_uid)['uid'] == folder_uid
    assert request(APP + '/health') == {'status': 'ok'}
    print('Grafana saved state and post-restart PairRoom health: PASS', flush=True)
    evidence = {'result': 'PASS', 'version': VERSION, 'trace_count': len(trace_ids),
                'persistence': ['prometheus', 'loki', 'tempo', 'grafana'],
                'privacy': 'no fixture secrets found', 'completed_at': time.time()}
    (ROOT / '.validation').mkdir(exist_ok=True)
    (ROOT / '.validation/results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence), flush=True)


if __name__ == '__main__':
    main()
