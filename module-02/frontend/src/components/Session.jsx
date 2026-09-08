import { useEffect, useRef, useState } from 'react';
import { interviewService, serviceMode } from '../services/index.js';
import CodeWorkspace from './CodeWorkspace.jsx';

export default function Session({ id, token }) {
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const [copyStatus, setCopyStatus] = useState('');
  const connection = useRef(null);
  useEffect(() => {
    let active = true;
    try { connection.current = interviewService.joinSession(id, token,
      value => { if (active) setState(value); }, err => { if (active) setError(err.message); }); }
    catch (err) { setError(err.message); }
    return () => { active = false; connection.current?.close(); };
  }, [id, token]);
  if (error) return <main className="error-view"><span className="eyebrow">Unable to open session</span><h1>{error}</h1><p>Check the full invitation link with your interviewer.</p><a className="button" href="#/">Back to home</a></main>;
  if (!state?.role) return <main><p role="status">Opening session…</p>{state?.warning && <p role="alert" className="notice">{state.warning}</p>}{state && !state.connected && <button onClick={() => connection.current?.reconnect()}>Retry connection</button>}</main>;
  const interviewer = state.role === 'interviewer';
  const candidateUrl = state.candidateLink ? new URL(state.candidateLink, window.location.href).href : '';
  function edit(field, value) {
    try { connection.current[field](value); } catch (err) { setError(err.message); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(candidateUrl); setCopyStatus('Link copied'); }
    catch { setCopyStatus('Select and copy the invitation link below.'); }
  }
  return <main className="session">
    <div className="session-heading"><div><span className="eyebrow">Shared workspace</span><h1>Your interview room<span className="role-badge">{interviewer ? 'Interviewer' : 'Candidate'}</span></h1><p>{interviewer ? 'Set the problem. Work through the code together.' : 'Read the problem. Make your thinking visible.'}</p></div>
      {interviewer && <button onClick={copy}>Copy candidate link <span aria-hidden="true">↗</span></button>}
    </div>
    {interviewer && <div className="invitation"><label htmlFor="invitation">Candidate invitation</label><input id="invitation" readOnly value={candidateUrl} onFocus={event => event.target.select()} /><span role="status">{copyStatus}</span><small>Keep your own address to return as interviewer. Both links are private.</small></div>}
    <div className="status-bar" role="status"><span className={state.connected ? 'online' : 'offline'}>● {state.connected ? 'Connected' : 'Disconnected'}</span><span>{interviewer ? 'Candidate' : 'Interviewer'} {state.otherConnected ? 'connected' : 'not connected'}</span><span className="save-status">{state.saveState === 'saving' ? 'Saving…' : state.saveState === 'unsaved' ? 'Changes not confirmed' : serviceMode === 'real' ? 'Saved on server' : 'Saved in this browser'}</span></div>
    {!state.connected && <p className="notice" role="alert">Connection lost. Editing is paused until the latest saved content is restored.</p>}
    {state.warning && <p className="notice" role="alert">{state.warning}</p>}
    <div className="workspace">
      <section className="panel"><div className="panel-heading"><h2>Problem statement</h2><span>{interviewer ? 'You edit' : 'Read only'}</span></div><label className="sr-only" htmlFor="problem">Problem statement</label><textarea id="problem" value={state.problem} readOnly={!interviewer || !state.connected} placeholder={interviewer ? 'Describe the problem, inputs, and expected output…' : 'The interviewer hasn’t added a problem yet.'} onChange={event => edit('updateProblem', event.target.value)} /><div className="panel-footer">Plain text · {interviewer ? 'Shared with your candidate' : 'Updated by your interviewer'}</div></section>
      <CodeWorkspace code={state.code} connected={state.connected} onChange={value => edit('updateCode', value)} />
    </div>
    {serviceMode === 'mock' ? <details className="prototype"><summary>Prototype connection controls</summary><p>Sessions are shared between tabs in this browser on this site. Use an external call for conversation.</p><button className="secondary" onClick={() => state.connected ? connection.current.disconnect() : connection.current.reconnect()}>{state.connected ? 'Simulate disconnection' : 'Reconnect'}</button></details>
      : !state.connected && <button className="secondary" onClick={() => connection.current.reconnect()}>Reconnect</button>}
  </main>;
}
