export class ServiceError extends Error {
  constructor(message, status = 0) { super(message); this.status = status; }
}

export function createHttpClient(baseUrl, fetchImpl) {
  return async (path, { method = 'GET', token, body, signal } = {}) => {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) abort();
    signal?.addEventListener('abort', abort, { once: true });
    const timeout = setTimeout(abort, 10000);
    try {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        method, signal: controller.signal, cache: 'no-store', credentials: 'omit',
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) {
        // Fixed messages avoid displaying credentials or proxy/server internals.
        const messages = { 401: 'Session not found or link invalid', 404: 'Session not found or link invalid',
          403: 'This role cannot edit that field.', 400: 'The edit could not be accepted.',
          415: 'The edit could not be accepted.' };
        throw new ServiceError(messages[response.status] || 'The server could not complete the request. Please try again.', response.status);
      }
      return await response.json();
    } catch (error) {
      if (error instanceof ServiceError) throw error;
      throw new ServiceError('Could not reach the server. Check your connection and try again.');
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener('abort', abort);
    }
  };
}
