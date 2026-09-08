// @vitest-environment node
import { Worker } from 'node:worker_threads';
import { createRequire } from 'node:module';
import { dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const runtimeUrl = pathToFileURL(dirname(require.resolve('pyodide/package.json')) + '/').href;
function execute(language, code) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('../test/worker-bridge.mjs', import.meta.url));
    const timer = setTimeout(() => { worker.terminate(); reject(new Error('Worker test timed out')); }, 30000);
    function finish(value, error) {
      clearTimeout(timer); worker.terminate();
      if (error) reject(error); else resolve(value);
    }
    worker.on('error', error => finish(null, error));
    worker.on('message', message => {
      if (message.type === 'ready') worker.postMessage({ type: 'run', code });
      else if (message.type === 'result') finish(message);
    });
    worker.postMessage({ type: 'initialize', language, runtimeUrl });
  });
}
it('executes real JavaScript console output and awaits promises in a worker', async () => {
  const result = await execute('javascript', 'console.log("sum", 2 + 3); await Promise.resolve(); console.error("stderr");');
  expect(result).toMatchObject({ output: 'sum 5\nstderr\n', error: '' });
});
it('reports JavaScript syntax/runtime errors and retains preceding output', async () => {
  expect(await execute('javascript', 'console.log("before"); throw new Error("bad");'))
    .toMatchObject({ output: 'before\n', error: 'Error: bad' });
  expect((await execute('javascript', 'const =')).error).toContain('SyntaxError');
});
it('bounds noisy console output', async () => {
  const result = await execute('javascript', 'for(let i=0;i<100000;i++) console.log("hello");');
  expect(result.output.length).toBeLessThan(20040);
  expect(result.output).toContain('[Output truncated]');
});
it('executes actual Pyodide WASM with stdout, stderr and exceptions', async () => {
  const result = await execute('python', 'import sys\nprint("sum", 2 + 3)\nsys.stderr.write("stderr\\n")\nraise ValueError("bad")');
  expect(result.output).toBe('sum 5\nstderr\n');
  expect(result.error).toContain('ValueError: bad');
}, 30000);

it('captures Python Unicode and output without a trailing newline', async () => {
  expect(await execute('python', 'print("Hello λ 🌍", end="")'))
    .toMatchObject({ output: 'Hello λ 🌍', error: '' });
}, 30000);
