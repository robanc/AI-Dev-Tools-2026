import { copyFile, mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const destination = new URL('../public/pyodide/', import.meta.url);
await mkdir(destination, { recursive: true });
for (const name of ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
  await copyFile(require.resolve(`pyodide/${name}`), new URL(name, destination));
}
