// This module is only loaded as a worker, never imported into React.
const send = self.postMessage.bind(self);
const LIMIT = 20000;
let language, pyodide, output = '', truncated = false;
function append(text) {
  const remaining = LIMIT - output.length;
  output += text.slice(0, remaining);
  if (text.length > remaining) truncated = true;
}
function format(value) {
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value) ?? String(value); }
  catch { return String(value); }
}
function result(error = '') {
  send({ type: 'result', output: output + (truncated ? '\n[Output truncated]' : ''), error: String(error).slice(0, LIMIT) });
}

self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'initialize') {
      language = data.language;
      if (language === 'python') {
        const { loadPyodide } = await import(/* @vite-ignore */ `${data.runtimeUrl}pyodide.mjs`);
        // Pyodide resolves its WASM/stdlib beside the imported runtime module.
        pyodide = await loadPyodide({ stdin: () => null });
        const stream = () => {
          const decoder = new TextDecoder();
          return { write: bytes => { append(decoder.decode(bytes, { stream: true })); return bytes.length; } };
        };
        pyodide.setStdout(stream());
        pyodide.setStderr(stream());
      }
      send({ type: 'ready' });
    } else if (data.type === 'run') {
      // One run per worker. The page terminates it on completion or timeout.
      self.onmessage = null;
      if (language === 'python') {
        try {
          const value = await pyodide.runPythonAsync(data.code);
          value?.destroy?.();
        } finally {
          // Include writes without a trailing newline, including before exceptions.
          try { pyodide.runPython('import sys\nsys.stdout.flush()\nsys.stderr.flush()'); }
          catch { /* User code may close/replace a stream; preserve its original result. */ }
        }
      } else {
        const log = (...args) => { if (!truncated) append(args.map(format).join(' ') + '\n'); };
        self.console = { ...self.console, log, info: log, warn: log, error: log, debug: log };
        // Dynamic compilation is confined to this disposable worker.
        const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
        await new AsyncFunction(data.code)();
      }
      result();
    }
  } catch (error) {
    result(error instanceof Error ? `${error.name}: ${error.message}` : error);
  }
};
