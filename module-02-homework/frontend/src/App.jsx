import { useEffect, useRef, useState } from 'react';
import { taskService } from './services/taskService.js';
import { STATUSES, validateTask } from './tasks.js';

function Modal({ title, busy, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog.showModal();
    return () => { dialog.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} aria-labelledby="dialog-title" onCancel={(event) => {
    event.preventDefault();
    if (!busy) onClose();
  }}>
    <h2 id="dialog-title">{title}</h2>
    {children}
  </dialog>;
}

function TaskForm({ task, onSave, onClose }) {
  const [title, setTitle] = useState(task?.title ?? '');
  const [description, setDescription] = useState(task?.description ?? '');
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const validation = validateTask({ title, description });
    setErrors(validation);
    if (Object.keys(validation).length) return;
    setBusy(true); setError('');
    try { await onSave({ title: title.trim(), description }); }
    catch { setError('Could not save this task. Your changes are still here. Please try again.'); }
    finally { setBusy(false); }
  }
  return <Modal title={task ? 'Task details' : 'Add a task'} busy={busy} onClose={onClose}>
    <form onSubmit={submit} noValidate>
      <fieldset disabled={busy}>
        <label htmlFor="task-title">Title <span className="hint">(required)</span></label>
        <input id="task-title" value={title} onChange={(e) => setTitle(e.target.value)} aria-invalid={!!errors.title} aria-describedby={errors.title ? 'title-error' : undefined} />
        {errors.title && <p className="field-error" id="title-error" role="alert">{errors.title}</p>}
        <label htmlFor="task-description">Description <span className="hint">(optional)</span></label>
        <textarea id="task-description" rows="6" value={description} onChange={(e) => setDescription(e.target.value)} aria-invalid={!!errors.description} aria-describedby={errors.description ? 'description-error' : undefined} />
        {errors.description && <p className="field-error" id="description-error" role="alert">{errors.description}</p>}
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="dialog-actions"><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save task'}</button></div>
    </form>
  </Modal>;
}

function DeleteDialog({ task, onDelete, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function confirm() {
    if (busy) return;
    setBusy(true); setError('');
    try { await onDelete(task.id); }
    catch { setError('Could not delete this task. Please try again.'); }
    finally { setBusy(false); }
  }
  return <Modal title="Delete task?" busy={busy} onClose={onClose}>
    <p>“{task.title}” will be permanently deleted. This cannot be undone.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="dialog-actions"><button disabled={busy} onClick={onClose}>Cancel</button><button className="danger" disabled={busy} onClick={confirm}>{busy ? 'Deleting…' : 'Delete task'}</button></div>
  </Modal>;
}

export default function App({ service = taskService }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState('');
  const [moving, setMoving] = useState(null);
  const [modal, setModal] = useState(null);
  useEffect(() => {
    let active = true;
    setLoading(true); setLoadError(false);
    service.listTasks().then((data) => { if (active) setTasks(data); })
      .catch(() => { if (active) setLoadError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [service, attempt]);
  const replaceTask = (updated) => setTasks((current) => current.map((task) => task.id === updated.id ? updated : task));
  async function save(values) {
    if (modal.task) replaceTask(await service.updateTask(modal.task.id, values));
    else { const created = await service.createTask(values); setTasks((current) => [...current, created]); }
    setModal(null);
  }
  async function move(task, status) {
    setMoving(task.id); setError('');
    try { replaceTask(await service.updateTask(task.id, { status })); }
    catch { setError(`Could not move “${task.title}”. Please try selecting the status again.`); }
    finally { setMoving(null); }
  }
  return <main>
    <header><div className="brand"><span className="brand-icon" aria-hidden="true">▥</span><span>TaskLane</span></div><span className="prototype">Frontend prototype</span></header>
    <section className="board-heading"><div><p className="eyebrow">A LITTLE FOCUS, EVERY DAY</p><h1>Your task board</h1><p>Make a plan. Take the next step. See your progress.</p></div><button className="primary" disabled={loading || loadError || moving !== null} onClick={() => setModal({ type: 'form' })}>+ Add task</button></section>
    <p className="notice">Tasks are saved automatically and stay available after a refresh or restart.</p>
    {loading && <p role="status">Loading your board…</p>}
    {loadError && <div className="error" role="alert">Could not load your board. <button onClick={() => setAttempt((value) => value + 1)}>Retry loading</button></div>}
    {error && <p className="error" role="alert">{error}</p>}
    {moving !== null && <p role="status">Moving task…</p>}
    <div className="board" aria-busy={loading}>
      {STATUSES.map(({ value, label }) => {
        const columnTasks = tasks.filter((task) => task.status === value).sort((a, b) => b.id - a.id);
        return <section className={`column ${value}`} key={value} aria-labelledby={`column-${value}`}>
          <div className="column-heading"><h2 id={`column-${value}`}><span className="dot" />{label}</h2><span className="count" aria-label={`${columnTasks.length} tasks`}>{columnTasks.length}</span></div>
          {!loading && !loadError && columnTasks.length === 0 && <div className="empty"><span aria-hidden="true">—</span><p>No tasks here yet</p><small>{value === 'todo' ? 'Add a task to get started.' : value === 'in_progress' ? 'Move a task here when you start.' : 'Finished tasks belong here.'}</small></div>}
          {columnTasks.map((task) => <article className="task" key={task.id} aria-label={task.title}>
            <button className="task-title" disabled={moving !== null} onClick={() => setModal({ type: 'form', task })}>{task.title}</button>
            {task.description && <p className="description">{task.description}</p>}
            <div className="task-actions"><label className="sr-only" htmlFor={`status-${task.id}`}>Status for {task.title}</label><select id={`status-${task.id}`} value={task.status} disabled={moving !== null} onChange={(e) => move(task, e.target.value)}>{STATUSES.map((status) => <option key={status.value} value={status.value}>{status.label}</option>)}</select><button className="delete-button" disabled={moving !== null} aria-label={`Delete ${task.title}`} onClick={() => setModal({ type: 'delete', task })}>Delete</button></div>
          </article>)}
        </section>;
      })}
    </div>
    <footer>One board. A little less on your mind.</footer>
    {modal?.type === 'form' && <TaskForm task={modal.task} onSave={save} onClose={() => setModal(null)} />}
    {modal?.type === 'delete' && <DeleteDialog task={modal.task} onClose={() => setModal(null)} onDelete={async (id) => { await service.deleteTask(id); setTasks((current) => current.filter((task) => task.id !== id)); setModal(null); }} />}
  </main>;
}
