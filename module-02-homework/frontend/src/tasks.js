export const STATUSES = [
  { value: 'todo', label: 'To Do' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'done', label: 'Done' },
];

export function validateTask({ title, description }) {
  const errors = {};
  if (typeof title !== 'string' || !title.trim()) errors.title = 'Enter a task title.';
  else if (title.trim().length > 200) errors.title = 'Use 200 characters or fewer for the title.';
  if (typeof description !== 'string' || description.length > 2000) errors.description = 'Use 2,000 characters or fewer for the description.';
  return errors;
}
