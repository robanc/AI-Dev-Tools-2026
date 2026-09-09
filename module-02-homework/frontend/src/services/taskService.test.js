import { describe, expect, it, vi } from 'vitest';
import { API_BASE_URL, createTaskService } from './taskService.js';

describe('HTTP task service', () => {
  it('uses the configured Vite URL', async () => {
    expect(API_BASE_URL).toBe('http://127.0.0.1:8000');
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:9000');
    vi.resetModules();
    try { expect((await import('./taskService.js')).API_BASE_URL).toBe('http://localhost:9000'); }
    finally { vi.unstubAllEnvs(); vi.resetModules(); }
  });
  it('maps every operation to the API contract and handles 204', async () => {
    const task = { id: 7, title: 'Task', description: '', status: 'todo' };
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(Response.json([task]))
      .mockResolvedValueOnce(Response.json(task, { status: 201 }))
      .mockResolvedValueOnce(Response.json({ ...task, title: 'Edited' }))
      .mockResolvedValueOnce(Response.json({ ...task, status: 'done' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const service = createTaskService({ baseUrl: 'http://localhost:9000/', fetchImpl });
    expect(await service.listTasks()).toEqual([task]);
    expect(await service.createTask({ title: 'Task' })).toEqual(task);
    expect(await service.updateTask(7, { title: 'Edited' })).toMatchObject({ title: 'Edited' });
    expect(await service.updateTask(7, { status: 'done' })).toMatchObject({ status: 'done' });
    await expect(service.deleteTask(7)).resolves.toBeUndefined();
    expect(fetchImpl.mock.calls.map(([url, options]) => [url, options.method, options.body && JSON.parse(options.body)])).toEqual([
      ['http://localhost:9000/api/tasks', 'GET', undefined],
      ['http://localhost:9000/api/tasks', 'POST', { title: 'Task', description: '' }],
      ['http://localhost:9000/api/tasks/7', 'PATCH', { title: 'Edited' }],
      ['http://localhost:9000/api/tasks/7', 'PATCH', { status: 'done' }],
      ['http://localhost:9000/api/tasks/7', 'DELETE', undefined],
    ]);
    expect(fetchImpl.mock.calls[1][1].headers).toEqual({ 'Content-Type': 'application/json' });
  });
  it.each([
    [404, { detail: 'Task not found.' }, 'Task not found.'],
    [422, { detail: [{ msg: 'Title is required' }] }, 'Title is required'],
  ])('rejects HTTP %s errors', async (status, data, message) => {
    const service = createTaskService({ fetchImpl: vi.fn().mockResolvedValue(Response.json(data, { status })) });
    await expect(service.updateTask(1, {})).rejects.toThrow(message);
  });
  it('handles non-JSON failures', async () => {
    const service = createTaskService({ fetchImpl: vi.fn().mockResolvedValue(new Response('Unavailable', { status: 503 })) });
    await expect(service.listTasks()).rejects.toThrow('503');
  });
  it('handles connection failures', async () => {
    const service = createTaskService({ fetchImpl: vi.fn().mockRejectedValue(new TypeError('Failed to fetch')) });
    await expect(service.createTask({ title: 'Task' })).rejects.toThrow('backend is running');
  });
});
