import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import App from './App.jsx';

const { service, handle } = vi.hoisted(() => ({
  service: { createSession: vi.fn(), joinSession: vi.fn() },
  handle: { close: vi.fn(), updateCode: vi.fn(), updateProblem: vi.fn(), reconnect: vi.fn() },
}));
vi.mock('./services/index.js', () => ({ interviewService: service, serviceMode: 'real' }));
beforeEach(() => {
  window.location.hash = '#/';
  service.joinSession.mockReturnValue(handle);
});

it('shows an asynchronous creation error without browser-storage instructions', async () => {
  service.createSession.mockRejectedValueOnce(new Error('Could not reach the server.'));
  render(<App />);
  expect(screen.getByText(/Sessions remain available until the server restarts/)).toBeInTheDocument();
  expect(screen.queryByText(/Frontend preview/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Create session/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the server.');
  expect(screen.queryByText(/Allow browser storage/)).not.toBeInTheDocument();
});

it('passes hash credentials to the service and displays asynchronous join errors', async () => {
  window.location.hash = '#/session/room/private-token';
  render(<App />);
  expect(screen.getByRole('status')).toHaveTextContent('Opening session');
  expect(service.joinSession).toHaveBeenCalledWith('room', 'private-token', expect.any(Function), expect.any(Function));
  await act(async () => service.joinSession.mock.lastCall[3](new Error('Session not found or link invalid')));
  expect(screen.getByRole('heading', { name: 'Session not found or link invalid' })).toBeInTheDocument();
});

it('shows server save state, pauses editing, and keeps language selection local', async () => {
  window.location.hash = '#/session/room/private-token';
  const { unmount } = render(<App />);
  const emit = service.joinSession.mock.lastCall[2];
  const state = { role: 'candidate', problem: 'Read me', code: '', connected: false,
    otherConnected: false, saveState: 'saved', warning: '', candidateLink: null };
  await act(async () => emit(state));
  expect(screen.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'true');
  expect(screen.getByLabelText('Problem statement')).toHaveAttribute('readonly');
  expect(screen.getByText('Saved on server')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Reconnect' }));
  expect(handle.reconnect).toHaveBeenCalledOnce();
  await act(async () => emit({ ...state, connected: true }));
  expect(screen.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'false');
  fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), { target: { value: 'python' } });
  expect(handle.updateCode).not.toHaveBeenCalled();
  expect(screen.queryByText('Prototype connection controls')).not.toBeInTheDocument();
  unmount(); expect(handle.close).toHaveBeenCalledOnce();
  await act(async () => emit({ ...state, code: 'late' }));
});
