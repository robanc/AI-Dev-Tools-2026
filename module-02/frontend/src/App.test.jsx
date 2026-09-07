import { beforeEach, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditorView } from '@codemirror/view';
import { javascriptLanguage } from '@codemirror/lang-javascript';
import { pythonLanguage } from '@codemirror/lang-python';
import App from './App.jsx';
import { interviewService } from './services/index.js';
vi.mock('./services/index.js', async () => ({
  interviewService: (await import('./services/mockInterviewService.js')).mockInterviewService,
  serviceMode: 'mock',
}));
beforeEach(() => { localStorage.clear(); window.location.hash = '#/'; });
it('creates an interviewer room with empty fields and a copyable candidate link', async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole('button', { name: /Create session/ }));
  const problem = await screen.findByRole('textbox', { name: 'Problem statement' });
  expect(problem).toHaveValue('');
  expect(problem).not.toHaveAttribute('readonly');
  expect(screen.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'false');
  await user.click(screen.getByRole('button', { name: /Copy candidate link/ }));
  expect(await screen.findByText('Link copied')).toBeInTheDocument();
  expect(await navigator.clipboard.readText()).toBe(screen.getByLabelText('Candidate invitation').value);
  fireEvent.change(problem, { target: { value: 'Add two numbers' } });
  expect(screen.getByText('Saving…')).toBeInTheDocument();
  await screen.findByText('Saved in this browser');
});
it('joins as candidate, shows saved problem, and pauses/resumes editor on disconnect', async () => {
  const created = await interviewService.createSession();
  let snapshot;
  const owner = interviewService.joinSession(...created.interviewerLink.split('/').slice(2), state => { snapshot = state; });
  owner.updateProblem('Find the answer');
  await waitFor(() => expect(snapshot.saveState).toBe('saved'));
  window.location.hash = snapshot.candidateLink;
  owner.close();
  const user = userEvent.setup();
  render(<App />);
  expect(await screen.findByRole('textbox', { name: 'Problem statement' })).toHaveValue('Find the answer');
  expect(screen.getByLabelText('Problem statement')).toHaveAttribute('readonly');
  expect(screen.queryByRole('button', { name: /Copy candidate/ })).not.toBeInTheDocument();
  const code = screen.getByRole('textbox', { name: 'Shared code' });
  expect(code).toHaveAttribute('contenteditable', 'true');
  await user.click(screen.getByText('Prototype connection controls'));
  await user.click(screen.getByRole('button', { name: 'Simulate disconnection' }));
  expect(code).toHaveAttribute('aria-readonly', 'true');
  expect(screen.getByRole('alert')).toHaveTextContent('Editing is paused');
  await user.click(screen.getByRole('button', { name: 'Reconnect' }));
  expect(code).toHaveAttribute('aria-readonly', 'false');
});
it.each(['#/session/missing/bad', '#/broken'])('shows a clear invalid-link view for %s', async hash => {
  window.location.hash = hash;
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Session not found or link invalid' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '#/');
});
it('reports storage failures during session creation', async () => {
  const failing = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage denied'); });
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: /Create session/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Allow browser storage');
  failing.mockRestore();
});

it.each(['interviewer', 'candidate'])('lets %s select either highlighting language and pauses code editing offline', async role => {
  const created = await interviewService.createSession();
  let snapshot;
  const owner = interviewService.joinSession(...created.interviewerLink.split('/').slice(2), state => { snapshot = state; });
  window.location.hash = role === 'interviewer' ? created.interviewerLink : snapshot.candidateLink;
  owner.close();
  const user = userEvent.setup();
  render(<App />);
  const code = await screen.findByRole('textbox', { name: 'Shared code' });
  expect(code).toHaveAttribute('contenteditable', 'true');
  const selector = screen.getByRole('combobox', { name: 'Language' });
  expect(selector).toHaveValue('javascript');
  expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['JavaScript', 'Python']);
  const view = EditorView.findFromDOM(code);
  expect(javascriptLanguage.isActiveAt(view.state, 0)).toBe(true);
  await user.selectOptions(selector, 'python');
  expect(selector).toHaveValue('python');
  expect(pythonLanguage.isActiveAt(view.state, 0)).toBe(true);
  await user.selectOptions(selector, 'javascript');
  expect(javascriptLanguage.isActiveAt(view.state, 0)).toBe(true);
  await user.click(screen.getByText('Prototype connection controls'));
  await user.click(screen.getByRole('button', { name: 'Simulate disconnection' }));
  expect(code).toHaveAttribute('contenteditable', 'false');
  expect(screen.getByLabelText('Problem statement')).toHaveAttribute('readonly');
  await user.click(screen.getByRole('button', { name: 'Reconnect' }));
  expect(code).toHaveAttribute('contenteditable', 'true');
});
