import { afterEach, expect, it, vi } from 'vitest';
import { runCode, EXECUTION_TIMEOUT, STARTUP_TIMEOUT } from './runner.js';

afterEach(() => vi.useRealTimers());
function worker() {
  return { postMessage: vi.fn(), terminate: vi.fn(), emit(data) { this.onmessage?.({ data }); } };
}
it.each(['javascript', 'python'])('sends only local %s execution data and cleans up after output', async language => {
  const socket = worker(), onStatus = vi.fn();
  const job = runCode({ language, code: 'example', onStatus }, () => socket);
  expect(socket.postMessage.mock.calls[0][0]).toEqual({ type: 'initialize', language, runtimeUrl: expect.stringContaining('/pyodide/') });
  socket.emit({ type: 'ready' });
  expect(onStatus).toHaveBeenCalledWith('running');
  expect(socket.postMessage).toHaveBeenLastCalledWith({ type: 'run', code: 'example' });
  socket.emit({ type: 'result', output: 'hello\n', error: '' });
  await expect(job.result).resolves.toEqual({ output: 'hello\n', error: '' });
  expect(socket.terminate).toHaveBeenCalledOnce();
  expect(socket.onmessage).toBeNull();
});
it('terminates an infinite loop and cannot extend its deadline with repeated ready messages', async () => {
  vi.useFakeTimers();
  const socket = worker();
  const job = runCode({ language: 'javascript', code: 'while(true){}' }, () => socket);
  socket.emit({ type: 'ready' });
  vi.advanceTimersByTime(EXECUTION_TIMEOUT - 1);
  socket.emit({ type: 'ready' });
  expect(socket.terminate).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  await expect(job.result).resolves.toMatchObject({ error: 'Execution timed out after 5 seconds.' });
  expect(socket.terminate).toHaveBeenCalledOnce();
});
it('times out stalled runtime initialization separately', async () => {
  vi.useFakeTimers();
  const socket = worker();
  const job = runCode({ language: 'python', code: '' }, () => socket);
  vi.advanceTimersByTime(STARTUP_TIMEOUT);
  await expect(job.result).resolves.toMatchObject({ error: expect.stringContaining('startup timed out') });
  expect(socket.terminate).toHaveBeenCalledOnce();
});
it('handles worker startup failure and runtime errors', async () => {
  await expect(runCode({ language: 'javascript', code: '' }, () => { throw new Error('Worker unavailable'); }).result)
    .resolves.toMatchObject({ error: 'Worker unavailable' });
  const socket = worker();
  const job = runCode({ language: 'python', code: '' }, () => socket);
  socket.emit({ type: 'result', output: 'before error', error: 'ValueError: bad' });
  await expect(job.result).resolves.toEqual({ output: 'before error', error: 'ValueError: bad' });
});
it('stops once and ignores late results', async () => {
  const socket = worker();
  const job = runCode({ language: 'javascript', code: '' }, () => socket);
  const late = socket.onmessage;
  job.cancel(); job.cancel();
  late({ data: { type: 'result', output: 'late' } });
  await expect(job.result).resolves.toMatchObject({ error: 'Execution stopped.' });
  expect(socket.terminate).toHaveBeenCalledOnce();
});
