import { expect } from '@playwright/test';

export const NEW_PASSWORD = 'E2E-Strong-Passphrase-2026';

const DEMO_PASSWORDS = { admin: 'admin123', officer1: 'officer123', officer2: 'officer123', clerk1: 'clerk123' };
const changed = new Set();

/**
 * Sign in as a seeded demo user. Demo accounts are forced to change their
 * password on first sign-in, so the first login per run completes that flow.
 */
export async function signIn(page, username) {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(changed.has(username) ? NEW_PASSWORD : DEMO_PASSWORDS[username]);
  await page.getByRole('button', { name: 'Sign in' }).click();

  if (!changed.has(username)) {
    // On a Playwright retry this module is reloaded but the database is not,
    // so the demo password may already have been replaced in an earlier attempt.
    const rejected = page.getByRole('alert').filter({ hasText: 'Incorrect username or password' });
    await expect(page.getByRole('heading', { name: 'Set a new password' }).or(rejected)).toBeVisible();
    if (await rejected.isVisible()) {
      changed.add(username);
      await page.getByLabel('Password', { exact: true }).fill(NEW_PASSWORD);
      await page.getByRole('button', { name: 'Sign in' }).click();
    }
  }

  if (!changed.has(username)) {
    await expect(page).toHaveURL(/\/change-password$/);
    await expect(page.getByRole('heading', { name: 'Set a new password' })).toBeVisible();
    await page.getByLabel('Current password').fill(DEMO_PASSWORDS[username]);
    await page.getByLabel('New password', { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel('Confirm new password').fill(NEW_PASSWORD);
    await page.getByRole('button', { name: 'Update password' }).click();
    changed.add(username);
  }
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
}

export async function signOut(page) {
  // The sidebar is a collapsed icon rail; its account actions appear once it is hovered open.
  await page.getByRole('navigation', { name: 'Main navigation' }).hover();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
}
