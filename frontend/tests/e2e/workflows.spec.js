import { expect, test } from '@playwright/test';
import { NEW_PASSWORD, signIn, signOut } from './helpers';

test.describe.configure({ mode: 'serial' });

test('unauthenticated users are sent to sign-in and no token is stored in the page', async ({ page }) => {
  await page.goto('/cases');
  await expect(page).toHaveURL(/\/login$/);
  await signIn(page, 'admin');
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }));
  expect(stored).not.toMatch(/eyJ/); // no JWT anywhere in localStorage
  const cookies = await page.context().cookies('http://localhost:8000');
  const session = cookies.find((c) => c.name === 'acrms_session');
  expect(session?.httpOnly).toBe(true);
});

test('wrong password shows a generic error', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', { exact: true }).fill('definitely-wrong');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('Incorrect username or password');
});

test('officer registers a case and records victims, evidence, links and status', async ({ page }) => {
  await signIn(page, 'officer1');
  await page.getByRole('link', { name: /Cases & FIR Files/ }).click();
  await page.getByRole('button', { name: 'Register case' }).click();
  const dialog = page.getByRole('dialog', { name: 'Register case file' });
  await dialog.getByLabel('Case title *').fill('E2E warehouse burglary');
  await dialog.getByLabel('Crime category').selectOption('Burglary');
  await dialog.getByLabel('Priority *').selectOption('high');
  await dialog.getByLabel('Incident location').fill('Dock 7');
  await dialog.getByRole('button', { name: 'Create case' }).click();

  await expect(page.getByRole('heading', { name: 'E2E warehouse burglary' })).toBeVisible();

  await page.getByRole('tab', { name: /Victims/ }).click();
  await page.getByRole('button', { name: 'Add victim' }).click();
  const victim = page.getByRole('dialog', { name: 'Add victim' });
  await victim.getByLabel('First name *').fill('Asha');
  await victim.getByLabel('Last name *').fill('Verma');
  await victim.getByLabel('Condition *').selectOption('hospitalized');
  await victim.getByRole('button', { name: 'Save victim' }).click();
  await expect(page.getByRole('cell', { name: 'Asha Verma' })).toBeVisible();

  await page.getByRole('tab', { name: /Evidence/ }).click();
  await page.getByRole('button', { name: 'Log evidence' }).click();
  const evidence = page.getByRole('dialog', { name: 'Log evidence item' });
  await evidence.getByLabel('Description *').fill('Pry bar with paint transfer');
  await evidence.getByLabel('Type *').selectOption('physical');
  await evidence.getByLabel('Location found').fill('Loading bay');
  await evidence.getByRole('button', { name: 'Save evidence' }).click();
  await expect(page.getByRole('cell', { name: 'Pry bar with paint transfer' })).toBeVisible();

  await page.getByRole('tab', { name: /Linked persons/ }).click();
  await page.getByRole('button', { name: 'Link record' }).click();
  const link = page.getByRole('dialog', { name: 'Link a person to this case' });
  await link.getByLabel('Search offender records').fill('Vega');
  await link.getByRole('button', { name: /Marcus Vega/ }).click();
  await link.getByLabel('Role in case').selectOption('suspect');
  await link.getByRole('button', { name: 'Link record' }).click();
  await expect(page.getByRole('link', { name: 'Marcus Vega' })).toBeVisible();

  await page.getByRole('button', { name: 'Change status' }).click();
  const status = page.getByRole('dialog', { name: 'Change case status' });
  await status.getByLabel('New status').selectOption('closed');
  await expect(status.getByLabel(/Reason/)).toHaveAttribute('required', ''); // closing needs a reason
  await status.getByLabel(/Reason/).fill('Suspect charged; file transferred to prosecution');
  await status.getByRole('button', { name: 'Update status' }).click();
  await expect(page.getByText('Closed').first()).toBeVisible();
  await signOut(page);
});

test('record clerk cannot reach AI review or admin screens', async ({ page }) => {
  await signIn(page, 'clerk1');
  await expect(page.getByRole('link', { name: /AI Predictions/ })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'User Directory' })).toHaveCount(0);
  await page.goto('/ai-predictions');
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto('/admin/users');
  await expect(page).toHaveURL(/\/dashboard$/);
  await signOut(page);
});

test('admin runs an AI assessment and records a reasoned review', async ({ page }) => {
  await signIn(page, 'admin');
  await page.getByRole('link', { name: 'Offender Directory' }).click();
  await page.getByLabel('Search records').fill('Volkov');
  await page.getByRole('link', { name: /Open record for Dmitri Volkov/ }).click();
  await expect(page.getByText('Unverified decision support, not evidence.').first()).toBeVisible();
  await page.getByRole('button', { name: 'Run assessment' }).click();
  await expect(page.getByText(/AI assessment created/)).toBeVisible();

  await page.getByRole('link', { name: 'Review queue' }).click();
  await expect(page.getByText('DEMO / RESEARCH MODE').first()).toBeVisible();
  await page.getByRole('button', { name: 'Review' }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(/Reject/).check();
  await dialog.getByLabel('Reasoning *').fill('short');
  await dialog.getByRole('button', { name: 'Record decision' }).click();
  await expect(dialog.getByRole('alert')).toContainText('at least 10 characters');
  await dialog.getByLabel('Reasoning *').fill('Synthetic model; no corroborating arrest or forensic record supports this category.');
  await dialog.getByRole('button', { name: 'Record decision' }).click();
  await expect(dialog.getByText('Review history (append-only)')).toBeVisible();
  await expect(dialog.getByText(/Pending → Rejected/)).toBeVisible();
});

test('admin sees model governance and a verified audit trail; logout ends the session', async ({ page }) => {
  await signIn(page, 'admin');
  await page.getByRole('link', { name: 'Model Governance' }).click();
  await expect(page.getByRole('heading', { name: 'AI Model Governance' })).toBeVisible();
  await expect(page.getByText('Release quality gate').first()).toBeVisible();

  await page.getByRole('link', { name: 'Audit Trail' }).click();
  await page.getByRole('button', { name: 'Verify integrity' }).click();
  await expect(page.getByText(/Integrity verified/)).toBeVisible();

  await signOut(page);
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/login$/);
  // The old session cannot be resurrected: signing in again needs the new password.
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});
