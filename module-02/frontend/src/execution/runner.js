export const EXECUTION_TIMEOUT = 5000;
export const STARTUP_TIMEOUT = 30000;
export const OUTPUT_LIMIT = 20000;

// No collaboration service, session ID, credential, or backend URL enters this layer.
export function runCode({ language, code, onStatus = () => {} }, createWorker = () =>
  new Worker(new URL('./execution.worker.js', import.meta.url), { type: 'module' })) {
  let worker, timer, settled = false, started = false, resolve;
  const result = new Promise(done => { resolve = done; });
  function finish(value) {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    if (worker) {
      worker.onmessage = worker.onerror = worker.onmessageerror = null;
      worker.terminate();
    }
    resolve(value);
  }
  function deadline(ms, error) {
    clearTimeout(timer);
    timer = setTimeout(() => finish({ output: '', error }), ms);
  }
  try {
    if (!['javascript', 'python'].includes(language)) throw new Error('Unsupported language.');
    worker = createWorker();
    deadline(STARTUP_TIMEOUT, 'Runtime startup timed out after 30 seconds. Try again.');
    worker.onmessage = ({ data }) => {
      if (settled || !data || typeof data !== 'object') return;
      if (data.type === 'ready' && !started) {
        started = true;
        deadline(EXECUTION_TIMEOUT, 'Execution timed out after 5 seconds.');
        onStatus('running');
        worker.postMessage({ type: 'run', code });
      } else if (data.type === 'result') {
        finish({ output: typeof data.output === 'string' ? data.output.slice(0, OUTPUT_LIMIT + 40) : '',
          error: typeof data.error === 'string' ? data.error.slice(0, OUTPUT_LIMIT) : '' });
      }
    };
    worker.onerror = event => {
      event.preventDefault();
      finish({ output: '', error: 'Execution worker failed. Try again.' });
    };
    worker.onmessageerror = () => finish({ output: '', error: 'Could not read execution output.' });
    const runtimeUrl = new URL(`${import.meta.env.BASE_URL}pyodide/`, window.location.origin).href;
    worker.postMessage({ type: 'initialize', language, runtimeUrl });
  } catch (error) {
    finish({ output: '', error: error.message || 'Could not start execution.' });
  }
  return { result, cancel: () => finish({ output: '', error: 'Execution stopped.' }) };
}
