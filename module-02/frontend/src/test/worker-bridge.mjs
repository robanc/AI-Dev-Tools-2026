// Node test adapter: run the actual browser worker module off the test/UI thread.
import { parentPort } from 'node:worker_threads';
globalThis.self = globalThis;
self.postMessage = value => parentPort.postMessage(value);
await import('../execution/execution.worker.js');
parentPort.on('message', data => self.onmessage?.({ data }));
