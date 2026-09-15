import { test, expect } from '@playwright/test';

for (const mode of ['preferred', 'unavailable', 'rejected', 'blocked']) {
  test(`candidate invitation copy: ${mode}`, async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/?utm_source=chatgpt.com');
    await page.getByRole('button', { name: /Create session/ }).click();
    const field = page.getByLabel('Candidate invitation', { exact: true });
    await expect(field).toBeVisible();
    await page.evaluate(mode => {
      const clipboard = navigator.clipboard;
      window.readCopiedInvitation = () => clipboard.readText();
      if (mode === 'preferred') {
        document.execCommand = () => { throw new Error('Fallback must not run'); };
      } else if (mode === 'rejected') {
        Object.defineProperty(navigator, 'clipboard', { configurable: true,
          value: { writeText: async () => { throw new Error('Permission denied'); } } });
      } else {
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
      }
      if (mode === 'blocked') document.execCommand = () => false;
    }, mode);
    await page.getByRole('button', { name: /Copy candidate link/ }).click();
    if (mode === 'blocked') {
      await expect(page.getByText('Automatic copy failed. Select and copy the invitation link manually.')).toBeVisible();
      await expect(field).toBeFocused();
      expect(await field.evaluate(input => input.selectionStart === 0 && input.selectionEnd === input.value.length)).toBe(true);
    } else {
      await expect(page.getByText('Link copied', { exact: true })).toBeVisible();
      // Compare inside the browser so private links never appear in assertion output.
      expect(await page.evaluate(async () => await window.readCopiedInvitation() === document.getElementById('invitation').value)).toBe(true);
    }
  });
}
test('two browser windows share edits, enforce roles, refresh, and reconnect', async ({ browser, page: owner }, testInfo) => {
  const candidateContext = await browser.newContext();
  const candidate = await candidateContext.newPage();
  const errors = [];
  const ownerUpdates = [];
  owner.on('websocket', socket => {
    if (!new URL(socket.url()).pathname.endsWith('/ws')) return;
    socket.on('framereceived', ({ payload }) => {
      const message = JSON.parse(String(payload));
      if (message.type === 'session.updated') ownerUpdates.push(message.session.code);
    });
  });
  owner.on('pageerror', error => errors.push(error.message));
  candidate.on('pageerror', error => errors.push(error.message));
  try {
    await owner.goto('/?utm_source=chatgpt.com#/');
    await owner.getByRole('button', { name: /Create session/ }).click();
    await expect(owner.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'false');
    const invitation = await owner.getByLabel('Candidate invitation', { exact: true }).inputValue();
    expect(new URL(invitation).search).toBe('');
    expect(invitation.startsWith(`${new URL(owner.url()).origin}/#/session/`)).toBe(true);
    expect(new URL(invitation).hash === new URL(owner.url()).hash).toBe(false);
    await candidate.goto(invitation);
    await expect(candidate.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'false');
    await expect(owner.getByText('Candidate connected', { exact: true })).toBeVisible();
    await expect(candidate.getByText('Interviewer connected', { exact: true })).toBeVisible();
    await expect(candidate.getByLabel('Problem statement', { exact: true })).toHaveAttribute('readonly', '');
    await expect(candidate.getByRole('button', { name: /Copy candidate/ })).toHaveCount(0);
    const timings = [];
    let start = Date.now();
    await owner.getByLabel('Problem statement', { exact: true }).fill('Return the sum of two numbers.');
    await expect(candidate.getByLabel('Problem statement', { exact: true })).toHaveValue('Return the sum of two numbers.', { timeout: 1000 });
    timings.push(Date.now() - start);
    start = Date.now();
    await candidate.getByRole('textbox', { name: 'Shared code' }).fill('function sum(a, b) { return a + b; }');
    await expect(owner.getByRole('textbox', { name: 'Shared code' })).toHaveText('function sum(a, b) { return a + b; }', { timeout: 1000 });
    timings.push(Date.now() - start);
    expect(ownerUpdates).toContain('function sum(a, b) { return a + b; }');
    start = Date.now();
    await owner.getByRole('textbox', { name: 'Shared code' }).fill('const sum = (a, b) => a + b;');
    await expect(candidate.getByRole('textbox', { name: 'Shared code' })).toHaveText('const sum = (a, b) => a + b;', { timeout: 1000 });
    timings.push(Date.now() - start);
    expect(timings.every(ms => ms < 1000)).toBe(true);
    await candidate.getByRole('combobox', { name: 'Language' }).selectOption('python');
    await expect(owner.getByRole('combobox', { name: 'Language' })).toHaveValue('javascript');
    await expect(owner.getByText('Saved on server', { exact: true })).toBeVisible();
    await candidate.reload();
    await expect(candidate.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'false');
    await expect(candidate.getByRole('textbox', { name: 'Shared code' })).toHaveText('const sum = (a, b) => a + b;');
    await expect(candidate.getByRole('combobox', { name: 'Language' })).toHaveValue('javascript');
    await candidateContext.setOffline(true);
    await expect(candidate.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'true');
    await expect(owner.getByText('Candidate not connected', { exact: true })).toBeVisible();
    await owner.getByLabel('Problem statement', { exact: true }).fill('Updated while candidate was offline.');
    await expect(owner.getByText('Saved on server', { exact: true })).toBeVisible();
    await candidateContext.setOffline(false);
    await expect(candidate.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'false');
    await expect(candidate.getByLabel('Problem statement', { exact: true })).toHaveValue('Updated while candidate was offline.');
    await expect(owner.getByText('Candidate connected', { exact: true })).toBeVisible();
    await owner.reload();
    await expect(owner.getByRole('textbox', { name: 'Shared code' })).toHaveAttribute('aria-readonly', 'false');
    await expect(owner.getByLabel('Problem statement', { exact: true })).toHaveValue('Updated while candidate was offline.');
    await candidate.screenshot({ path: testInfo.outputPath('candidate.png'), fullPage: true });
    console.log(`Live edit propagation (problem, candidate code, interviewer code): ${timings.join(', ')} ms`);
    await candidate.goto(invitation + 'invalid');
    await expect(candidate.getByRole('heading', { name: 'Session not found or link invalid' })).toBeVisible();
    expect(errors).toEqual([]);
  } finally { await candidateContext.close(); }
});
