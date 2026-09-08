import { test, expect } from '@playwright/test';

test('production workers run JavaScript/Python, handle errors/timeouts, and keep output local', async ({ page, context }, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByRole('button', { name: /Create session/ }).click();
  const editor = page.getByRole('textbox', { name: 'Shared code' });
  await expect(editor).toBeVisible();
  const candidate = await context.newPage();
  await candidate.goto(await page.getByLabel('Candidate invitation', { exact: true }).inputValue());
  const output = page.getByRole('region', { name: 'Execution output' });
  async function run(code, language = 'javascript') {
    await page.getByRole('combobox', { name: 'Language' }).selectOption(language);
    await editor.fill(code);
    await page.getByRole('button', { name: 'Run', exact: true }).click();
  }
  await run('console.log("sum", 2 + 3); console.log(typeof document);');
  await expect(output).toContainText('sum 5');
  await expect(output).toContainText('undefined');
  await expect(candidate.getByRole('region', { name: 'Execution output' })).not.toContainText('sum 5');
  await run('console.log("before"); throw new Error("boom")');
  await expect(output).toContainText('before');
  await expect(output.getByRole('alert')).toContainText('Error: boom');
  await run('while (true) {}');
  await expect(page.getByRole('button', { name: 'Running…' })).toBeDisabled();
  // A real UI interaction succeeds while the worker is stuck.
  await page.getByLabel('Problem statement', { exact: true }).fill('UI is responsive');
  await expect(output).toContainText('Execution timed out after 5 seconds.', { timeout: 8000 });
  await run('while (true) {}');
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(output).toContainText('Execution stopped.');
  await run('print("Python sum", 2 + 3)\nimport sys\nsys.stderr.write("stderr\\n")', 'python');
  await expect(output).toContainText('Python sum 5', { timeout: 30000 });
  await expect(output).toContainText('stderr');
  await run('print("before error")\nraise ValueError("bad")', 'python');
  await expect(output.getByRole('alert')).toContainText('ValueError: bad', { timeout: 30000 });
  await expect(output).toContainText('before error');
  await run('while True:\n    pass', 'python');
  await expect(page.getByRole('button', { name: 'Running…' })).toBeDisabled({ timeout: 30000 });
  await expect(output).toContainText('Execution timed out after 5 seconds.', { timeout: 8000 });
  await run('print("Fresh run", 42, end="")', 'python');
  await expect(output).toContainText('Fresh run 42', { timeout: 30000 });
  await expect(candidate.getByRole('combobox', { name: 'Language' })).toHaveValue('javascript');
  await page.screenshot({ path: testInfo.outputPath('local-output.png'), fullPage: true });
  expect(errors).toEqual([]);
  await candidate.close();
});
