import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { mockInterviewService as service } from './mockInterviewService.js';
let connections;
const parse = link => link.split('/').slice(2);
beforeEach(() => { localStorage.clear(); connections = []; vi.useFakeTimers(); });
afterEach(() => { connections.forEach(connection => connection.close()); vi.useRealTimers(); });
function join(link) {
  const result = { state: null };
  result.connection = service.joinSession(...parse(link), state => { result.state = state; });
  connections.push(result.connection);
  return result;
}
async function pair() {
  const { interviewerLink } = await service.createSession();
  const interviewer = join(interviewerLink);
  const candidate = join(interviewer.state.candidateLink);
  return { interviewer, candidate, interviewerLink };
}
describe('mock interview service', () => {
  it('creates empty sessions with distinct private role links and validates access', async () => {
    const { interviewer, candidate, interviewerLink } = await pair();
    expect(interviewer.state).toMatchObject({ problem: '', code: '', role: 'interviewer' });
    expect(candidate.state.role).toBe('candidate');
    expect(candidate.state.candidateLink).toBeNull();
    expect(interviewer.state.candidateLink).not.toBe(interviewerLink);
    expect(() => service.joinSession(...parse(interviewerLink + 'wrong'), () => {})).toThrow('Session not found or link invalid');
  });
  it('enforces both roles at the service boundary', async () => {
    const { interviewer, candidate } = await pair();
    expect(() => interviewer.connection.updateCode('interviewer code')).not.toThrow();
    expect(() => candidate.connection.updateCode('candidate code')).not.toThrow();
    expect(() => candidate.connection.updateProblem('bad')).toThrow('This role cannot edit');
  });
  it('confirms saves and synchronizes independent problem and code edits within one second', async () => {
    const { interviewer, candidate, interviewerLink } = await pair();
    interviewer.connection.updateProblem('Return the sum.');
    candidate.connection.updateCode('function sum(a, b) {\n  return a + b;\n}');
    expect(candidate.state.saveState).toBe('saving');
    vi.advanceTimersByTime(400);
    expect(candidate.state.problem).toBe('Return the sum.');
    expect(interviewer.state.code).toContain('return a + b;');
    expect(candidate.state.saveState).toBe('saved');
    interviewer.connection.close();
    const restored = join(interviewerLink);
    expect(restored.state.problem).toBe('Return the sum.');
    expect(restored.state.code).toBe(candidate.state.code);
  });
  it('tracks presence, pauses offline edits, warns about pending loss, and reloads on reconnect', async () => {
    const { interviewer, candidate } = await pair();
    vi.advanceTimersByTime(200);
    expect(interviewer.state.otherConnected).toBe(true);
    candidate.connection.updateCode('pending');
    candidate.connection.disconnect();
    vi.advanceTimersByTime(200);
    expect(interviewer.state.otherConnected).toBe(false);
    expect(candidate.state.warning).toContain('may not have been saved');
    expect(() => candidate.connection.updateCode('offline')).toThrow('Reconnect');
    interviewer.connection.updateProblem('Latest saved problem');
    vi.advanceTimersByTime(200);
    candidate.connection.reconnect();
    expect(candidate.state).toMatchObject({ connected: true, code: '', problem: 'Latest saved problem' });
  });
  it('reacts to browser offline and online events', async () => {
    const { candidate } = await pair();
    window.dispatchEvent(new Event('offline'));
    expect(candidate.state.connected).toBe(false);
    window.dispatchEvent(new Event('online'));
    expect(candidate.state.connected).toBe(true);
  });
});

it('saves both interviewer fields without losing pending edits and shares code in both directions', async () => {
  const { interviewer, candidate, interviewerLink } = await pair();
  interviewer.connection.updateProblem('Write a greeting');
  interviewer.connection.updateCode('print("hello")');
  expect(interviewer.state).toMatchObject({ problem: 'Write a greeting', code: 'print("hello")', saveState: 'saving' });
  vi.advanceTimersByTime(400);
  expect(candidate.state).toMatchObject({ problem: 'Write a greeting', code: 'print("hello")' });
  expect(interviewer.state.saveState).toBe('saved');
  expect(join(interviewerLink).state).toMatchObject({ problem: 'Write a greeting', code: 'print("hello")' });
  candidate.connection.updateCode('print("world")');
  vi.advanceTimersByTime(400);
  expect(interviewer.state.code).toBe('print("world")');
  interviewer.connection.disconnect();
  expect(() => interviewer.connection.updateCode('offline')).toThrow('Reconnect');
  expect(() => interviewer.connection.updateProblem('offline')).toThrow('Reconnect');
});
