const PREFIX = 'pairroom:v1:';
const invalid = () => new Error('Session not found or link invalid');
const key = (id, field) => `${PREFIX}${id}:${field}`;
const read = (id, field) => JSON.parse(localStorage.getItem(key(id, field)) || 'null');
const write = (id, field, value) => localStorage.setItem(key(id, field), JSON.stringify(value));
const route = (id, token) => `#/session/${id}/${token}`;

function authorize(id, token) {
  const access = read(id, 'access');
  const role = access && ['interviewer', 'candidate'].find(role => access[role] === token);
  if (!role) throw invalid();
  return { role, access };
}

export const mockInterviewService = {
  async createSession() {
    const id = crypto.randomUUID();
    const access = { interviewer: crypto.randomUUID(), candidate: crypto.randomUUID() };
    write(id, 'problem', '');
    write(id, 'code', '');
    write(id, 'access', access);
    return { interviewerLink: route(id, access.interviewer) };
  },

  joinSession(id, token, onChange) {
    const { role, access } = authorize(id, token);
    const other = role === 'interviewer' ? 'candidate' : 'interviewer';
    let connected = navigator.onLine;
    let closed = false;
    let warning = '';
    let pending = {};
    let timer;
    let previous = '';
    const heartbeat = () => write(id, `presence:${role}`, connected ? Date.now() : 0);
    function emit() {
      if (closed) return;
      const state = {
        role, problem: read(id, 'problem') ?? '', code: read(id, 'code') ?? '',
        connected, otherConnected: connected && Date.now() - (read(id, `presence:${other}`) || 0) < 3000,
        saveState: Object.keys(pending).length === 0 ? (warning ? 'unsaved' : 'saved') : 'saving', warning,
        candidateLink: role === 'interviewer' ? route(id, access.candidate) : null,
      };
      Object.assign(state, pending);
      const serialized = JSON.stringify(state);
      if (serialized !== previous) { previous = serialized; onChange(state); }
    }
    function disconnect() {
      connected = false;
      clearTimeout(timer);
      if (Object.keys(pending).length > 0) warning = 'Your pending edit may not have been saved. Reconnecting restores the last saved version.';
      pending = {};
      heartbeat();
      emit();
    }
    function reconnect() {
      if (closed) return;
      // Reload persisted state before publishing an editable, connected snapshot.
      authorize(id, token);
      connected = navigator.onLine;
      heartbeat();
      emit();
    }
    function update(target, value) {
      if (closed || !connected) throw new Error('Reconnect before editing.');
      if (target === 'problem' && role !== 'interviewer') throw new Error('This role cannot edit that field.');
      authorize(id, token);
      pending[target] = value;
      warning = '';
      clearTimeout(timer);
      emit();
      timer = setTimeout(() => {
        try {
          for (const [field, value] of Object.entries(pending)) write(id, field, value);
          pending = {};
        } catch {
          warning = 'This edit could not be saved. Check browser storage and try again.';
          pending = {};
        }
        emit();
      }, 150);
    }
    heartbeat();
    emit();
    const poll = setInterval(emit, 200);
    const pulse = setInterval(heartbeat, 1000);
    window.addEventListener('offline', disconnect);
    window.addEventListener('online', reconnect);
    window.addEventListener('pagehide', disconnect);
    return {
      updateProblem: value => update('problem', value),
      updateCode: value => update('code', value),
      disconnect, reconnect,
      close() {
        disconnect();
        closed = true;
        clearInterval(poll);
        clearInterval(pulse);
        window.removeEventListener('offline', disconnect);
        window.removeEventListener('online', reconnect);
        window.removeEventListener('pagehide', disconnect);
      },
    };
  },
};
