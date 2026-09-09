import { act, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import App from './App.jsx';
import { createTaskService } from './services/taskService.js';
import { createMockFetch } from './test/mockTaskService.js';

async function setup() {
  const service = createTaskService({ fetchImpl: createMockFetch() });
  const user = userEvent.setup();
  render(<App service={service} />);
  await waitFor(() => expect(screen.queryByText('Loading your board…')).not.toBeInTheDocument());
  return { service, user };
}
async function add(user, title = 'Write the report', description = '') {
  await user.click(screen.getByRole('button', { name: '+ Add task' }));
  await user.type(screen.getByLabelText(/Title/), title);
  if (description) await user.type(screen.getByLabelText(/Description/), description);
  await user.click(screen.getByRole('button', { name: 'Save task' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
}

describe('TaskLane board', () => {
  it('shows loading followed by three empty columns', async () => {
    let resolve;
    const service = { listTasks: () => new Promise((done) => { resolve = done; }) };
    render(<App service={service} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading');
    expect(screen.getByRole('button', { name: '+ Add task' })).toBeDisabled();
    await act(async () => resolve([]));
    for (const name of ['To Do', 'In Progress', 'Done']) expect(screen.getByRole('region', { name })).toBeInTheDocument();
    expect(screen.getAllByText('No tasks here yet')).toHaveLength(3);
  });

  it('creates trimmed tasks, shows full details, and sorts newest first', async () => {
    const { user, service } = await setup();
    await add(user, '  First task  ', 'Full task description');
    await add(user, 'Second task');
    const cards = within(screen.getByRole('region', { name: 'To Do' })).getAllByRole('article');
    expect(cards[0]).toHaveAccessibleName('Second task');
    expect(cards[1]).toHaveAccessibleName('First task');
    await user.click(screen.getByRole('button', { name: 'First task', exact: true }));
    expect(screen.getByLabelText(/Description/)).toHaveValue('Full task description');
    expect((await service.listTasks())[0].title).toBe('First task');
  });

  it('validates whitespace titles and text limits without saving', async () => {
    const { user, service } = await setup();
    const create = vi.spyOn(service, 'createTask');
    await user.click(screen.getByRole('button', { name: '+ Add task' }));
    await user.type(screen.getByLabelText(/Title/), '   ');
    await user.click(screen.getByRole('button', { name: 'Save task' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a task title');
    await user.clear(screen.getByLabelText(/Title/));
    await user.click(screen.getByLabelText(/Title/));
    await user.paste('x'.repeat(201));
    await user.click(screen.getByLabelText(/Description/));
    await user.paste('x'.repeat(2001));
    await user.click(screen.getByRole('button', { name: 'Save task' }));
    expect(screen.getByText('Use 200 characters or fewer for the title.')).toBeInTheDocument();
    expect(screen.getByText('Use 2,000 characters or fewer for the description.')).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it('cancels edits, then saves changed title and description', async () => {
    const { user } = await setup();
    await add(user);
    await user.click(screen.getByRole('button', { name: 'Write the report', exact: true }));
    await user.clear(screen.getByLabelText(/Title/));
    await user.type(screen.getByLabelText(/Title/), 'Discarded');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Write the report', exact: true })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByLabelText(/Title/)).toHaveValue('Write the report');
    await user.clear(screen.getByLabelText(/Title/));
    await user.type(screen.getByLabelText(/Title/), 'Edited report');
    await user.type(screen.getByLabelText(/Description/), 'Updated details');
    await user.click(screen.getByRole('button', { name: 'Save task' }));
    expect(await screen.findByRole('article', { name: 'Edited report' })).toHaveTextContent('Updated details');
  });

  it('moves a task through every column without losing details', async () => {
    const { user, service } = await setup();
    await add(user, 'Move me', 'Keep this description');
    for (const [value, label] of [['in_progress', 'In Progress'], ['done', 'Done'], ['todo', 'To Do']]) {
      await user.selectOptions(screen.getByRole('combobox'), value);
      await waitFor(() => expect(within(screen.getByRole('region', { name: label })).getByRole('article', { name: 'Move me' })).toBeInTheDocument());
    }
    expect((await service.listTasks())[0].description).toBe('Keep this description');
  });

  it('requires confirmation for deletion and supports cancel', async () => {
    const { user, service } = await setup();
    await add(user);
    await user.click(screen.getByRole('button', { name: 'Delete Write the report' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('cannot be undone');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('article')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete Write the report' }));
    await user.click(screen.getByRole('button', { name: 'Delete task', exact: true }));
    await waitFor(() => expect(screen.queryByRole('article')).not.toBeInTheDocument());
    expect(await service.listTasks()).toEqual([]);
  });

  it('offers a retry after loading fails', async () => {
    const service = createTaskService({ fetchImpl: createMockFetch() });
    vi.spyOn(service, 'listTasks').mockRejectedValueOnce(new Error('Offline'));
    render(<App service={service} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load');
    await userEvent.click(screen.getByRole('button', { name: 'Retry loading' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(await screen.findAllByText('No tasks here yet')).toHaveLength(3);
  });

  it('preserves entered values after a failed save and permits retry', async () => {
    const { user, service } = await setup();
    vi.spyOn(service, 'createTask').mockRejectedValueOnce(new Error('Offline'));
    await user.click(screen.getByRole('button', { name: '+ Add task' }));
    await user.type(screen.getByLabelText(/Title/), 'Keep my work');
    await user.type(screen.getByLabelText(/Description/), 'Unsaved details');
    await user.click(screen.getByRole('button', { name: 'Save task' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save');
    expect(screen.getByLabelText(/Title/)).toHaveValue('Keep my work');
    expect(screen.getByLabelText(/Description/)).toHaveValue('Unsaved details');
    await user.click(screen.getByRole('button', { name: 'Save task' }));
    expect(await screen.findByRole('article', { name: 'Keep my work' })).toBeInTheDocument();
  });

  it('disables submission while saving to prevent duplicates', async () => {
    const { user, service } = await setup();
    let resolve;
    const create = vi.spyOn(service, 'createTask').mockImplementation(() => new Promise((done) => { resolve = done; }));
    await user.click(screen.getByRole('button', { name: '+ Add task' }));
    await user.type(screen.getByLabelText(/Title/), 'Only once');
    await user.dblClick(screen.getByRole('button', { name: 'Save task' }));
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(create).toHaveBeenCalledTimes(1);
    await act(async () => resolve({ id: 1, title: 'Only once', description: '', status: 'todo' }));
  });

  it('keeps tasks unchanged when moving or deleting fails', async () => {
    const { user, service } = await setup();
    await add(user);
    vi.spyOn(service, 'updateTask').mockRejectedValueOnce(new Error('Offline'));
    await user.selectOptions(screen.getByRole('combobox'), 'done');
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not move');
    expect(screen.getByRole('combobox')).toHaveValue('todo');
    vi.spyOn(service, 'deleteTask').mockRejectedValueOnce(new Error('Offline'));
    await user.click(screen.getByRole('button', { name: 'Delete Write the report' }));
    await user.click(screen.getByRole('button', { name: 'Delete task', exact: true }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Could not delete');
    expect(await service.listTasks()).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Delete task', exact: true }));
    await waitFor(() => expect(screen.queryByRole('article')).not.toBeInTheDocument());
  });
});
