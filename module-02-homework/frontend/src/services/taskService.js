export const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000';

// All production backend communication is centralized here.
export function createTaskService({ baseUrl = API_BASE_URL, fetchImpl = (...args) => fetch(...args) } = {}) {
  const root = baseUrl.replace(/\/+$/, '');
  async function request(path, method = 'GET', body) {
    let response;
    try {
      response = await fetchImpl(`${root}${path}`, {
        method,
        ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
      });
    } catch {
      throw new Error('Cannot reach TaskLane. Check that the backend is running and try again.');
    }
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      const detail = data?.detail;
      const message = typeof detail === 'string' ? detail
        : Array.isArray(detail) ? detail.map((item) => item.msg).join(' ')
          : `TaskLane request failed (${response.status}). Please try again.`;
      throw new Error(message);
    }
    if (response.status === 204) return undefined;
    return response.json();
  }
  return {
    listTasks: () => request('/api/tasks'),
    createTask: ({ title, description = '' }) => request('/api/tasks', 'POST', { title, description }),
    updateTask: (id, changes) => request(`/api/tasks/${encodeURIComponent(id)}`, 'PATCH', changes),
    deleteTask: (id) => request(`/api/tasks/${encodeURIComponent(id)}`, 'DELETE'),
  };
}

export const taskService = createTaskService();
