// Visual capture of key screens for design review (not part of CI):
//   PW_CHANNEL=msedge npx playwright test -c playwright.visual.config.js
import { test } from '@playwright/test';
import { signIn } from '../e2e/helpers';

const OUT = process.env.SHOT_DIR || 'test-results/screens';

test.describe.configure({ mode: 'serial' });

test('login', async ({ page }) => {
  await page.goto('/login');
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/01-login.png`, fullPage: true });
});

test('admin screens', async ({ page }) => {
  await signIn(page, 'admin');
  const shots = [
    ['/dashboard', '02-dashboard'],
    ['/criminals', '03-criminals'],
    ['/cases', '05-cases'],
    ['/ai-predictions', '07-ai'],
    ['/admin/ai-models', '08-models'],
    ['/admin/audit', '09-audit'],
    ['/admin/users', '10-users'],
    ['/alerts', '11-alerts'],
  ];
  for (const [path, name] of shots) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  }
  await page.goto('/criminals');
  await page.waitForLoadState('networkidle');
  await page.locator('a[aria-label^="Open record"]').first().click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/04-profile.png`, fullPage: true });
  await page.goto('/cases');
  await page.waitForLoadState('networkidle');
  await page.locator('a[aria-label^="Open case"]').first().click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/06-case.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/12-mobile-dashboard.png`, fullPage: false });
});
