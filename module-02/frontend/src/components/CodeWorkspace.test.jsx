import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { runCode } from '../execution/runner.js';
import CodeWorkspace from './CodeWorkspace.jsx';

vi.mock('../execution/runner.js', () => ({ runCode: vi.fn() }));
let finish, cancel;
beforeEach(() => {
  cancel = vi.fn();
  runCode.mockImplementation(() => ({ result: new Promise(resolve => { finish = resolve; }), cancel }));
});
it('runs the editor snapshot, disables Run, renders stdout as text, and preserves local selection', async () => {
  const onChange = vi.fn();
  const { rerender, container } = render(<CodeWorkspace code={'console.log("hello")'} connected onChange={onChange} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  expect(runCode).toHaveBeenCalledWith(expect.objectContaining({ language: 'javascript', code: 'console.log("hello")' }));
  expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled();
  act(() => runCode.mock.lastCall[0].onStatus('running'));
  expect(screen.getByRole('button', { name: 'Running…' })).toBeDisabled();
  fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), { target: { value: 'python' } });
  rerender(<CodeWorkspace code="remote edit" connected onChange={onChange} />);
  await act(async () => finish({ output: '<b>hello</b>\n42', error: '' }));
  expect(screen.getByRole('region', { name: 'Execution output' })).toHaveTextContent('<b>hello</b>');
  expect(container.querySelector('b')).toBeNull();
  expect(screen.getByRole('button', { name: 'Run' })).toBeEnabled();
  expect(screen.getByRole('combobox')).toHaveValue('python');
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  expect(runCode).toHaveBeenLastCalledWith(expect.objectContaining({ language: 'python', code: 'remote edit' }));
});
it.each(['ValueError: bad', 'Execution timed out after 5 seconds.'])('renders %s and permits another run', async error => {
  render(<CodeWorkspace code="bad" connected onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  await act(async () => finish({ output: 'before error', error }));
  expect(screen.getByRole('alert')).toHaveTextContent(error);
  expect(screen.getByText('before error')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  await act(async () => finish({ output: '', error: '' }));
  expect(screen.getByText('No output.')).toBeInTheDocument();
});
it('stops execution and cancels on unmount without displaying a late result', async () => {
  const { unmount } = render(<CodeWorkspace code="while(true){}" connected onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run' }));
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
  expect(cancel).toHaveBeenCalledOnce();
  unmount();
  expect(cancel).toHaveBeenCalledTimes(2);
  await act(async () => finish({ output: 'late', error: '' }));
  await waitFor(() => expect(screen.queryByText('late')).not.toBeInTheDocument());
});
