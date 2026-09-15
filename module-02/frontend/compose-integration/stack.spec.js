import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

const root = fileURLToPath(new URL('../../', import.meta.url));
function compose(...args) {
  return execFileSync('docker', ['compose', '-f', 'docker-compose.yaml', ...args], {
    cwd: root, encoding: 'utf8', timeout: 30000,
  });
}

test.beforeEach(async ({ request }) => {
  await expect.poll(async () => {
    try { return (await request.get('/openapi.json', { timeout: 2000 })).status(); }
    catch { return 0; }
  }, { timeout: 30000 }).toBe(200);
});

test('production frontend serves its compiled JavaScript and CSS', async ({ request }) => {
  const response = await request.get('/');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('text/html');
  const html = await response.text();
  expect(html).toContain('<div id="root">');
  expect(html).not.toMatch(/@vite\/client|\/src\/main/);
  const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^" ]+\.(?:js|css))"/g)].map(match => match[1]);
  expect(assets.some(asset => asset.endsWith('.js'))).toBe(true);
  expect(assets.some(asset => asset.endsWith('.css'))).toBe(true);
  for (const asset of assets) {
    const built = await request.get(asset);
    expect(built.status()).toBe(200);
    expect(built.headers()['content-type']).toMatch(asset.endsWith('.js') ? /javascript/ : /text\/css/);
    expect((await built.body()).length).toBeGreaterThan(0);
  }
});

test('backend exposes the session API', async ({ request }) => {
  const response = await request.get('/openapi.json');
  expect(response.status()).toBe(200);
  expect((await response.json()).paths['/sessions'].post).toBeTruthy();
  expect((await request.get('/docs')).status()).toBe(200);
});

test('API writes reach PostgreSQL and survive an app restart', async ({ request }) => {
  const created = await request.post('/sessions');
  expect(created.status()).toBe(201);
  const [, , id, token] = (await created.json()).interviewerLink.split('/');
  expect(id).toMatch(/^[0-9a-f-]{36}$/);
  const path = `/sessions/${id}`;
  const headers = { Authorization: `Bearer ${token}` };
  const problem = 'Compose persistence check';
  const code = 'const persisted = true;';
  expect((await request.put(`${path}/problem`, { headers, data: { problem } })).status()).toBe(200);
  const updated = await request.put(`${path}/code`, { headers, data: { code } });
  expect(updated.status()).toBe(200);
  const saved = await updated.json();
  // Query the actual Compose PostgreSQL service through a separate connection.
  // The validated UUID is the only interpolated SQL value.
  const row = JSON.parse(compose('exec', '-T', 'postgres', 'psql', '-U', 'pairroom', '-d', 'pairroom',
    '-tA', '-v', 'ON_ERROR_STOP=1', '-c',
    `SELECT row_to_json(s) FROM (SELECT problem, code, revision FROM interview_sessions WHERE id = '${id}') s;`).trim());
  expect(row).toEqual({ problem, code, revision: saved.revision });
  compose('restart', 'app');
  await expect.poll(async () => {
    try {
      const response = await request.get(path, { headers, timeout: 2000 });
      return response.ok() ? (await response.json()).session : null;
    } catch { return null; }
  }, { timeout: 30000 }).toEqual(saved);
});
