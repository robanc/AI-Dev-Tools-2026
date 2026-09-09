import assert from 'node:assert/strict';
import { createTaskService } from '../src/services/taskService.js';

// Run against a started backend; only the task created here is removed.
const baseUrl = process.env.TASKLANE_API_URL || 'http://127.0.0.1:8000';
const origin = 'http://127.0.0.1:5173';
const service = createTaskService({ baseUrl });
const preflight = await fetch(`${baseUrl}/api/tasks/1`, {
  method: 'OPTIONS',
  headers: { Origin: origin, 'Access-Control-Request-Method': 'PATCH', 'Access-Control-Request-Headers': 'content-type' },
});
assert.equal(preflight.status, 200);
assert.equal(preflight.headers.get('access-control-allow-origin'), origin);
let task;
try {
  task = await service.createTask({ title: 'API communication check', description: 'Temporary verification task' });
  assert.equal(task.status, 'todo');
  assert.ok((await service.listTasks()).some(({ id }) => id === task.id));
  const edited = await service.updateTask(task.id, { title: 'Edited communication check', description: 'Updated details' });
  assert.equal(edited.title, 'Edited communication check');
  for (const status of ['in_progress', 'done', 'todo']) {
    const moved = await service.updateTask(task.id, { status });
    assert.equal(moved.status, status);
    assert.equal(moved.description, 'Updated details');
  }
  // A fresh service instance reloads the same server state.
  assert.ok((await createTaskService({ baseUrl }).listTasks()).some(({ id }) => id === task.id));
  await service.deleteTask(task.id);
  assert.ok(!(await service.listTasks()).some(({ id }) => id === task.id));
  task = undefined;
  console.log(`PASS: frontend HTTP service → ${baseUrl}/api/tasks; CRUD, reload, status changes, and CORS preflight.`);
} finally {
  if (task) await service.deleteTask(task.id);
}
