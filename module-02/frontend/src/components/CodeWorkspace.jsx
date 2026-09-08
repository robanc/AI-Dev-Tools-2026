import { useEffect, useRef, useState } from 'react';
import { runCode } from '../execution/runner.js';
import CodeEditor from './CodeEditor.jsx';

export default function CodeWorkspace({ code, connected, onChange }) {
  const [language, setLanguage] = useState('javascript');
  const [status, setStatus] = useState('idle');
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');
  const [runLanguage, setRunLanguage] = useState('');
  const active = useRef(null);
  useEffect(() => () => { const job = active.current; active.current = null; job?.cancel(); }, []);
  const busy = status === 'loading' || status === 'running';
  async function run() {
    if (active.current) return;
    setOutput(''); setError(''); setRunLanguage(language); setStatus('loading');
    const job = runCode({ language, code, onStatus: setStatus });
    active.current = job;
    const result = await job.result;
    if (active.current !== job) return;
    active.current = null;
    setOutput(result.output); setError(result.error); setStatus('finished');
  }
  return <section className="panel">
    <div className="panel-heading"><h2>Shared code</h2>
      <label className="language-selector">Language <select value={language} onChange={event => setLanguage(event.target.value)}>
        <option value="javascript">JavaScript</option><option value="python">Python</option>
      </select></label>
      <button className="run-button" onClick={run} disabled={busy}>{status === 'loading' ? 'Loading…' : busy ? 'Running…' : 'Run'}</button>
      {busy && <button className="secondary" onClick={() => active.current?.cancel()}>Stop</button>}
    </div>
    <CodeEditor value={code} language={language} editable={connected} onChange={onChange} />
    <div className="panel-footer">Both roles edit · Tab to indent · Escape, then Tab to leave the editor</div>
    <section className="execution-output" aria-label="Execution output">
      <div className="output-heading"><h3>Output</h3><span>Only in this browser{runLanguage && ` · ${runLanguage === 'python' ? 'Python' : 'JavaScript'}`}</span></div>
      <p role="status">{status === 'idle' ? 'Run to see output. Execution stops after 5 seconds.' : status === 'loading' ? 'Loading runtime…' : busy ? 'Running…' : error ? 'Run ended with an error.' : 'Run complete.'}</p>
      {output && <pre>{output}</pre>}
      {error && <pre className="execution-error" role="alert">{error}</pre>}
      {status === 'finished' && !output && !error && <pre>No output.</pre>}
    </section>
  </section>;
}
