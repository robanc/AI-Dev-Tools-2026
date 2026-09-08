import { afterEach, expect, it, vi } from 'vitest';
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); });

it('defaults to the preserved mock adapter', async () => {
  vi.stubEnv('VITE_INTERVIEW_SERVICE', ''); vi.resetModules();
  const entry = await import('./index.js');
  expect(entry.serviceMode).toBe('mock');
  expect(entry.interviewService).toBe((await import('./mockInterviewService.js')).mockInterviewService);
});

it('selects the real adapter by Vite environment', async () => {
  vi.stubEnv('VITE_INTERVIEW_SERVICE', 'real'); vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000'); vi.resetModules();
  const entry = await import('./index.js');
  expect(entry.serviceMode).toBe('real');
  expect(entry.interviewService).not.toBe((await import('./mockInterviewService.js')).mockInterviewService);
  expect(entry.interviewService.joinSession).toBeTypeOf('function');
});

it('uses the page origin for the single-container build', async () => {
  vi.stubEnv('VITE_INTERVIEW_SERVICE', 'real');
  vi.stubEnv('VITE_API_BASE_URL', 'same-origin');
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ interviewerLink: 'link' }) });
  vi.stubGlobal('fetch', fetch);
  const entry = await import('./index.js');
  await entry.interviewService.createSession();
  expect(fetch).toHaveBeenCalledWith(`${window.location.origin}/sessions`, expect.objectContaining({ method: 'POST' }));
});
