import { createHttpClient } from './http.js';

const uncertain = 'Your pending edit may not have been saved. Reconnecting restores the last saved version.';
const validState = state => state && Number.isSafeInteger(state.revision) && state.revision >= 0
  && typeof state.problem === 'string' && typeof state.code === 'string';

export function createRealInterviewService({ baseUrl = 'http://127.0.0.1:8000',
  fetchImpl = (...args) => fetch(...args), WebSocketImpl = globalThis.WebSocket } = {}) {
  const base = new URL(baseUrl);
  if (!['http:', 'https:'].includes(base.protocol) || base.search || base.hash || base.username || base.password) {
    throw new Error('VITE_API_BASE_URL must be an HTTP(S) URL without credentials, query, or hash.');
  }
  const apiUrl = base.href.replace(/\/$/, '');
  const request = createHttpClient(apiUrl, fetchImpl);
  return {
    createSession: () => request('/sessions', { method: 'POST' }),
    joinSession(id, token, onChange, onError = () => {}) {
      const path = `/sessions/${encodeURIComponent(id)}`;
      let state = { role: null, candidateLink: null, problem: '', code: '', connected: false,
        otherConnected: false, saveState: 'saved', warning: '' };
      let saved = { problem: '', code: '', revision: -1 };
      let pending = {};
      const flights = new Set();
      const flushTimers = new Map();
      let socket, controller, retryTimer, heartbeat, pongTimeout, handshake;
      let closed = false, manual = false, generation = 0, attempts = 0;
      const active = current => !closed && current === generation;
      function emit() {
        if (closed) return;
        onChange({ ...state, problem: pending.problem?.value ?? saved.problem,
          code: pending.code?.value ?? saved.code,
          saveState: Object.keys(pending).length ? 'saving' : state.saveState });
      }
      function apply(snapshot) {
        if (!validState(snapshot)) throw new Error('Invalid session snapshot');
        if (snapshot.revision > saved.revision) saved = snapshot;
      }
      function retire() {
        generation++;
        controller?.abort();
        clearTimeout(retryTimer); clearTimeout(pongTimeout); clearTimeout(handshake); clearInterval(heartbeat);
        flushTimers.forEach(clearTimeout); flushTimers.clear(); flights.clear();
        if (socket) {
          socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
          socket.close(1000);
          socket = null;
        }
      }
      function lose(message = '', retry = true) {
        const hadPending = Object.keys(pending).length > 0;
        retire(); pending = {};
        state = { ...state, connected: false, otherConnected: false,
          saveState: hadPending ? 'unsaved' : state.saveState,
          warning: hadPending ? `${message ? `${message} ` : ''}${uncertain}` : (state.saveState === 'unsaved' ? state.warning : message) };
        emit();
        if (retry && !closed && !manual && navigator.onLine) {
          retryTimer = setTimeout(begin, Math.min(1000 * 2 ** Math.min(attempts++, 3), 5000));
        }
      }
      function fatal(error) {
        manual = true;
        lose(error.message, false);
        onError(error);
      }
      function failure(error, current) {
        if (!active(current)) return;
        if ([401, 404].includes(error.status)) fatal(error);
        else lose(error.message, ![400, 403, 415].includes(error.status));
      }
      async function flush(field) {
        flushTimers.delete(field);
        if (!state.connected || flights.has(field) || !pending[field]) return;
        const sent = pending[field], current = generation;
        flights.add(field);
        try {
          const snapshot = await request(`${path}/${field}`, {
            method: 'PUT', token, body: { [field]: sent.value }, signal: controller.signal,
          });
          if (!active(current)) return;
          apply(snapshot);
          if (pending[field] === sent) delete pending[field];
          flights.delete(field);
          if (!Object.keys(pending).length) state.saveState = 'saved';
          emit();
          // A newer local value waits for this acknowledgement; never send same-field writes in parallel.
          if (pending[field]) void flush(field);
        } catch (error) { failure(error, current); }
      }
      function update(field, value) {
        if (closed || !state.connected) throw new Error('Reconnect before editing.');
        if (field === 'problem' && state.role !== 'interviewer') throw new Error('This role cannot edit that field.');
        pending[field] = { value };
        state.warning = ''; state.saveState = 'saving';
        emit();
        // Do not reset this timer on every keystroke: continuous typing still flushes.
        if (!flights.has(field) && !flushTimers.has(field)) {
          flushTimers.set(field, setTimeout(() => void flush(field), 150));
        }
      }
      async function begin() {
        if (closed || manual || !navigator.onLine) return;
        retire();
        const current = generation;
        controller = new AbortController();
        try {
          const access = await request(path, { token, signal: controller.signal });
          if (!active(current)) return;
          if (!['interviewer', 'candidate'].includes(access.role)) throw new Error('Invalid session role');
          apply(access.session);
          state = { ...state, role: access.role, candidateLink: access.candidateLink };
          emit();
          const wsUrl = new URL(`${apiUrl}${path}/ws`);
          wsUrl.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
          socket = new WebSocketImpl(wsUrl.href);
          const ws = socket;
          handshake = setTimeout(() => { if (active(current)) lose('Could not establish a live connection. Retrying…'); }, 10000);
          ws.onopen = () => {
            if (active(current)) ws.send(JSON.stringify({ type: 'authenticate', token }));
          };
          ws.onerror = () => { if (active(current)) lose('Connection lost. Retrying…'); };
          ws.onclose = event => {
            if (!active(current)) return;
            if (event.code === 1008) fatal(new Error('The live connection was rejected. Close any duplicate role tab and reopen your link.'));
            else lose('Connection lost. Retrying…');
          };
          ws.onmessage = event => {
            if (!active(current)) return;
            try {
              const message = JSON.parse(event.data);
              if (message.type === 'error') {
                if (message.code === 'invalid_link') fatal(new Error('Session not found or link invalid'));
                else if (message.code === 'invalid_message') fatal(new Error('The live connection was rejected. Close any duplicate role tab and reopen your link.'));
                else lose('The live connection failed. Retrying…');
                return;
              }
              if (!state.connected && message.type !== 'snapshot') throw new Error('Expected snapshot');
              switch (message.type) {
                case 'snapshot':
                  if (state.connected || !validState(message.session) || typeof message.otherConnected !== 'boolean') throw new Error('Invalid snapshot');
                  // Fresh connection state replaces any pre-disconnect baseline before editing resumes.
                  saved = message.session;
                  clearTimeout(handshake); attempts = 0;
                  state.connected = true; state.otherConnected = message.otherConnected;
                  if (state.saveState !== 'unsaved') state.warning = '';
                  heartbeat = setInterval(() => {
                    try {
                      ws.send(JSON.stringify({ type: 'ping' }));
                      pongTimeout = setTimeout(() => lose('Connection lost. Retrying…'), 5000);
                    } catch { lose('Connection lost. Retrying…'); }
                  }, 10000);
                  break;
                case 'session.updated': apply(message.session); break;
                case 'presence.updated':
                  if (typeof message.otherConnected !== 'boolean') throw new Error('Invalid presence');
                  state.otherConnected = message.otherConnected; break;
                case 'pong': clearTimeout(pongTimeout); break;
                default: throw new Error('Unexpected event');
              }
              emit();
            } catch { fatal(new Error('The server sent an unexpected response. Reopen your session to try again.')); }
          };
        } catch (error) { failure(error, current); }
      }
      const offline = () => lose('Connection lost. Waiting for a network connection.', false);
      const online = () => { if (!manual && !closed && !state.connected) void begin(); };
      const pagehide = () => { manual = true; lose('', false); };
      const pageshow = event => { if (event.persisted && !closed) { manual = false; void begin(); } };
      window.addEventListener('offline', offline); window.addEventListener('online', online);
      window.addEventListener('pagehide', pagehide); window.addEventListener('pageshow', pageshow);
      emit();
      if (navigator.onLine) void begin(); else offline();
      return {
        updateProblem: value => update('problem', value), updateCode: value => update('code', value),
        disconnect() { manual = true; lose('', false); },
        reconnect() { if (!closed) { manual = false; lose('', false); void begin(); } },
        close() {
          closed = true; retire(); pending = {};
          window.removeEventListener('offline', offline); window.removeEventListener('online', online);
          window.removeEventListener('pagehide', pagehide); window.removeEventListener('pageshow', pageshow);
        },
      };
    },
  };
}
