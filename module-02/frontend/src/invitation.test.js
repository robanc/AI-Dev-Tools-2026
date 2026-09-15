import { expect, it } from 'vitest';
import { candidateInvitationUrl } from './invitation.js';

it.each(['http://203.0.113.10', 'http://localhost:5173', 'https://example.com'])(
  'constructs an origin-only invitation for %s', origin => {
    const location = new URL(`${origin}/unrelated?utm_source=chatgpt.com#unrelated`);
    expect(candidateInvitationUrl('#/session/session-id/candidate-token', location.origin))
      .toBe(`${origin}/#/session/session-id/candidate-token`);
  },
);
