import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createRealInterviewService } from './realInterviewService.js';

const snapshot = (revision = 0, problem = '', code = '') => ({ id: 'room', revision, problem, code });
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
class Socket {
  static instances = [];
  constructor(url) { this.url = url; this.sent = []; Socket.instances.push(this); }
  send(value) { this.sent.push(JSON.parse(value)); }
  close() { this.closed = true; }
  open() { this.onopen?.(); }
  event(message) { this.onmessage?.({ data: JSON.stringify(message) }); }
  drop() { this.onclose?.({ code: 1006 }); }
}
let fetchImpl, service, connection, state, onChange, onError;
const tick = () => vi.advanceTimersByTimeAsync(0);
beforeEach(() => {
  vi.useFakeTimers(); Socket.instances = [];
  fetchImpl = vi.fn().mockResolvedValue(response({ role: 'interviewer', candidateLink: '#/session/room/candidate', session: snapshot() }));
  service = createRealInterviewService({ baseUrl: 'https://api.example', fetchImpl, WebSocketImpl: Socket });
  onError = vi.fn(); onChange = vi.fn(value => { state = value; });
});
afterEach(() => { connection?.close(); connection = null; vi.useRealTimers(); });
async function join(role = 'interviewer') {
  fetchImpl.mockResolvedValueOnce(response({ role, candidateLink: role === 'interviewer' ? '#/session/room/candidate' : null, session: snapshot() }));
  connection = service.joinSession('room', 'secret', onChange, onError);
  await tick();
  const socket = Socket.instances.at(-1); socket.open();
  return socket;
}
async function connected(role) {
  const socket = await join(role);
  socket.event({ type: 'snapshot', session: snapshot(), otherConnected: false });
  return socket;
}

it('creates through POST without a body or credential and reports HTTP failures', async () => {
  fetchImpl.mockResolvedValueOnce(response({ interviewerLink: '#/session/room/secret' }, 201));
  await expect(service.createSession()).resolves.toEqual({ interviewerLink: '#/session/room/secret' });
  expect(fetchImpl).toHaveBeenCalledWith('https://api.example/sessions', expect.objectContaining({ method: 'POST', headers: {} }));
  expect(fetchImpl.mock.calls[0][1]).not.toHaveProperty('body');
  fetchImpl.mockResolvedValueOnce(response({}, 500));
  await expect(service.createSession()).rejects.toThrow('server could not complete');
  fetchImpl.mockRejectedValueOnce(new TypeError('network'));
  await expect(service.createSession()).rejects.toThrow('Could not reach the server');
});

it('uses bearer access and WebSocket authentication, waiting for a fresh snapshot before editing', async () => {
  const socket = await join();
  expect(fetchImpl).toHaveBeenCalledWith('https://api.example/sessions/room', expect.objectContaining({
    method: 'GET', headers: { Authorization: 'Bearer secret' }, credentials: 'omit', cache: 'no-store',
  }));
  expect(socket.url).toBe('wss://api.example/sessions/room/ws');
  expect(socket.sent).toEqual([{ type: 'authenticate', token: 'secret' }]);
  expect(state.connected).toBe(false);
  expect(() => connection.updateCode('early')).toThrow('Reconnect');
  socket.event({ type: 'snapshot', session: snapshot(2, 'Problem', 'code'), otherConnected: true });
  expect(state).toMatchObject({ role: 'interviewer', connected: true, otherConnected: true, problem: 'Problem', code: 'code' });
  socket.event({ type: 'presence.updated', otherConnected: false });
  expect(state.otherConnected).toBe(false);
  socket.event({ type: 'session.updated', session: snapshot(3, 'New problem', 'new code') });
  socket.event({ type: 'session.updated', session: snapshot(1, 'old', 'old') });
  expect(state).toMatchObject({ problem: 'New problem', code: 'new code' });
});

it('saves independent fields and waits for HTTP acknowledgements even when broadcasts arrive first', async () => {
  const socket = await connected();
  const problem = deferred(), code = deferred();
  fetchImpl.mockReturnValueOnce(problem.promise).mockReturnValueOnce(code.promise);
  connection.updateProblem('Question'); connection.updateCode('answer');
  await vi.advanceTimersByTimeAsync(150);
  for (const [field, value] of [['problem', 'Question'], ['code', 'answer']]) {
    expect(fetchImpl).toHaveBeenCalledWith(`https://api.example/sessions/room/${field}`, expect.objectContaining({
      method: 'PUT', headers: { Authorization: 'Bearer secret', 'Content-Type': 'application/json' }, body: JSON.stringify({ [field]: value }),
    }));
  }
  socket.event({ type: 'session.updated', session: snapshot(2, 'Question', 'answer') });
  expect(state.saveState).toBe('saving');
  code.resolve(response(snapshot(2, 'Question', 'answer'))); await tick();
  expect(state.saveState).toBe('saving');
  problem.resolve(response(snapshot(1, 'Question', ''))); await tick();
  expect(state).toMatchObject({ problem: 'Question', code: 'answer', saveState: 'saved' });
});

it('serializes same-field writes, preserves newer typing, and flushes continuous typing within 150ms', async () => {
  await connected();
  const first = deferred(), second = deferred();
  fetchImpl.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  connection.updateCode('a'); await vi.advanceTimersByTimeAsync(100);
  connection.updateCode('ab'); await vi.advanceTimersByTimeAsync(50);
  expect(fetchImpl.mock.calls[1][1].body).toBe('{"code":"ab"}');
  connection.updateCode('abc'); await vi.advanceTimersByTimeAsync(200);
  expect(fetchImpl).toHaveBeenCalledTimes(2);
  first.resolve(response(snapshot(1, '', 'ab'))); await tick();
  expect(state).toMatchObject({ code: 'abc', saveState: 'saving' });
  expect(fetchImpl.mock.calls[2][1].body).toBe('{"code":"abc"}');
  second.resolve(response(snapshot(2, '', 'abc'))); await tick();
  expect(state.saveState).toBe('saved');
});

it('allows candidate code but rejects candidate problem updates locally', async () => {
  await connected('candidate');
  expect(state.candidateLink).toBeNull();
  expect(() => connection.updateProblem('bad')).toThrow('This role cannot edit');
  fetchImpl.mockResolvedValueOnce(response(snapshot(1, '', 'candidate code')));
  connection.updateCode('candidate code'); await vi.advanceTimersByTimeAsync(150);
  expect(state).toMatchObject({ code: 'candidate code', saveState: 'saved' });
});

it('discards unconfirmed edits, ignores late callbacks, and reloads on reconnect without replay', async () => {
  const socket = await connected(); const write = deferred();
  fetchImpl.mockReturnValueOnce(write.promise);
  connection.updateCode('uncertain'); await vi.advanceTimersByTimeAsync(150);
  socket.drop();
  expect(state).toMatchObject({ connected: false, saveState: 'unsaved', code: '' });
  expect(state.warning).toContain('may not have been saved');
  await vi.advanceTimersByTimeAsync(1000);
  const next = Socket.instances.at(-1); next.open();
  expect(state.connected).toBe(false);
  next.event({ type: 'snapshot', session: snapshot(3, 'Latest', 'remote'), otherConnected: true });
  write.resolve(response(snapshot(1, '', 'uncertain'))); await tick();
  expect(state).toMatchObject({ connected: true, code: 'remote', problem: 'Latest', saveState: 'unsaved' });
  expect(fetchImpl.mock.calls.filter(([, options]) => options.method === 'PUT')).toHaveLength(1);
});

it.each([401, 404])('reports async access failure %s and stops retrying', async status => {
  fetchImpl.mockResolvedValueOnce(response({}, status));
  connection = service.joinSession('room', 'bad', onChange, onError);
  await vi.advanceTimersByTimeAsync(30000);
  expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Session not found or link invalid' }));
  expect(fetchImpl).toHaveBeenCalledTimes(1); expect(Socket.instances).toHaveLength(0);
});

it('reports WebSocket invalid links without retrying', async () => {
  const socket = await join();
  socket.event({ type: 'error', code: 'invalid_link', message: 'Session not found or link invalid' });
  await vi.advanceTimersByTimeAsync(30000);
  expect(onError).toHaveBeenCalledOnce(); expect(Socket.instances).toHaveLength(1);
});

it('pauses after rejected writes and does not automatically retry validation or permission failures', async () => {
  await connected(); fetchImpl.mockResolvedValueOnce(response({}, 403));
  connection.updateProblem('rejected'); await vi.advanceTimersByTimeAsync(150);
  expect(state).toMatchObject({ connected: false, saveState: 'unsaved' });
  await vi.advanceTimersByTimeAsync(30000);
  expect(fetchImpl).toHaveBeenCalledTimes(2);
});

it('uses ping/pong and pauses on a missed heartbeat', async () => {
  const socket = await connected();
  await vi.advanceTimersByTimeAsync(10000);
  expect(socket.sent.at(-1)).toEqual({ type: 'ping' });
  socket.event({ type: 'pong' }); await vi.advanceTimersByTimeAsync(5000);
  expect(state.connected).toBe(true);
  await vi.advanceTimersByTimeAsync(10000);
  expect(state.connected).toBe(false); expect(socket.closed).toBe(true);
});

it('retries initial network failures with capped backoff and supports manual stop/cleanup', async () => {
  fetchImpl.mockRejectedValue(new TypeError('offline'));
  connection = service.joinSession('room', 'secret', onChange, onError);
  await tick(); expect(state.warning).toContain('Could not reach');
  for (const delay of [1000, 2000, 4000, 5000]) await vi.advanceTimersByTimeAsync(delay);
  expect(fetchImpl).toHaveBeenCalledTimes(5);
  connection.disconnect(); window.dispatchEvent(new Event('online'));
  await vi.advanceTimersByTimeAsync(10000); expect(fetchImpl).toHaveBeenCalledTimes(5);
  connection.reconnect(); await tick(); expect(fetchImpl).toHaveBeenCalledTimes(6);
  connection.close(); const calls = onChange.mock.calls.length;
  window.dispatchEvent(new Event('online')); await vi.advanceTimersByTimeAsync(30000);
  expect(fetchImpl).toHaveBeenCalledTimes(6); expect(onChange).toHaveBeenCalledTimes(calls);
});

it('cancels a pending join on close and suppresses its asynchronous result', async () => {
  const get = deferred(); fetchImpl.mockReturnValueOnce(get.promise);
  connection = service.joinSession('room', 'secret', onChange, onError);
  connection.close(); const calls = onChange.mock.calls.length;
  get.resolve(response({ role: 'interviewer', session: snapshot() })); await tick();
  expect(Socket.instances).toHaveLength(0); expect(onChange).toHaveBeenCalledTimes(calls);
});
