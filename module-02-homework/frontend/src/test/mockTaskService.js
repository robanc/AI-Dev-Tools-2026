import { STATUSES, validateTask } from '../tasks.js';

// Test-only fixture; never imported by production code.
export function createTaskService({ delay = 250 } = {}) {
  let tasks = [];
  let nextId = 1;
  const wait = () => new Promise((resolve) => setTimeout(resolve, delay));
  const check = (task) => {
    const errors = validateTask(task);
    if (Object.keys(errors).length) throw new Error(Object.values(errors)[0]);
    if (!STATUSES.some(({ value }) => value === task.status)) throw new Error('Choose a valid status.');
  };
  return {
    async listTasks() { await wait(); return tasks.map((task) => ({ ...task })); },
    async createTask({ title, description = '' }) {
      await wait();
      const task = { id: nextId, title, description, status: 'todo' };
      check(task);
      task.title = task.title.trim();
      nextId += 1;
      tasks.push(task);
      return { ...task };
    },
    async updateTask(id, changes) {
      await wait();
      const index = tasks.findIndex((task) => task.id === id);
      if (index === -1) throw new Error('This task could not be found.');
      const task = { ...tasks[index] };
      for (const field of ['title', 'description', 'status']) {
        if (Object.hasOwn(changes, field)) task[field] = changes[field];
      }
      check(task);
      task.title = task.title.trim();
      tasks[index] = task;
      return { ...task };
    },
    async deleteTask(id) {
      await wait();
      if (!tasks.some((task) => task.id === id)) throw new Error('This task could not be found.');
      tasks = tasks.filter((task) => task.id !== id);
    },
  };
}

export function createMockFetch() {
  const store = createTaskService({ delay: 0 });
  return async (url, options) => {
    const id = Number(new URL(url).pathname.split('/')[3]);
    const body = options.body ? JSON.parse(options.body) : undefined;
    let data;
    if (options.method === 'GET') data = await store.listTasks();
    else if (options.method === 'POST') data = await store.createTask(body);
    else if (options.method === 'PATCH') data = await store.updateTask(id, body);
    else if (options.method === 'DELETE') {
      await store.deleteTask(id);
      return new Response(null, { status: 204 });
    }
    return Response.json(data, { status: options.method === 'POST' ? 201 : 200 });
  };
}
