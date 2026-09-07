import { useEffect, useState } from 'react';
import { interviewService, serviceMode } from './services/index.js';
import Session from './components/Session.jsx';

export default function App() {
  const [hash, setHash] = useState(window.location.hash);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const navigate = () => setHash(window.location.hash);
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  async function create() {
    setBusy(true); setError('');
    try { const result = await interviewService.createSession(); window.location.hash = result.interviewerLink; }
    catch (err) { setError(serviceMode === 'real' ? err.message : 'Could not create a session. Allow browser storage and try again.'); }
    finally { setBusy(false); }
  }
  const match = hash.match(/^#\/session\/([^/]+)\/([^/]+)$/);
  const home = !hash || hash === '#/' || hash === '#';
  return <><header><a className="brand" href="#/"><span aria-hidden="true">⌘</span> pairroom<span className="brand-dot">.</span></a><span className="header-note">A little space for big ideas <span className="prototype-badge">{serviceMode === 'mock' ? 'Prototype' : 'Live session'}</span></span></header>
    {home ? <main className="home"><span className="eyebrow">One problem. Two perspectives.</span><h1>Good interviews<br />start with a <em>shared space.</em></h1><p className="intro">A focused room for your next coding conversation. Share a problem, watch a solution take shape, and think it through together.</p><button disabled={busy} onClick={create}>{busy ? 'Creating…' : 'Create session'} <span aria-hidden="true">↗</span></button><p className="hint">No accounts. Just a private invitation link.</p>{error && <p role="alert" className="notice">{error}</p>}<div className="steps"><div><span>01 / CREATE</span><h2>Make room.</h2><p>Start a session and write your problem.</p></div><div><span>02 / INVITE</span><h2>Bring someone in.</h2><p>Share the candidate link with your candidate.</p></div><div><span>03 / COLLABORATE</span><h2>Think together.</h2><p>Follow edits as they happen. Talk on your own call.</p></div></div><p className="mock-note">{serviceMode === 'mock' ? 'Frontend preview - Sessions stay in this browser. Open both links on the same site in the same browser profile.' : 'Sessions remain available until the server restarts. Keep your private link to return.'}</p></main>
    : match ? <Session key={hash} id={match[1]} token={match[2]} /> : <main className="error-view"><span className="eyebrow">Unable to open session</span><h1>Session not found or link invalid</h1><p>Check the full invitation link and try again.</p><a className="button" href="#/">Back to home</a></main>}
    <footer><span>PAIRROOM / A collaborative coding interview</span><span>Space to think, together.</span></footer>
  </>;
}
