import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('renders signed evidence without console errors or broken internal links', async ({
  page,
  request,
}) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => consoleErrors.push(error.message));

  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    'Faster queries',
  );
  await expect(
    page.getByText('LOCALNET EVIDENCE', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('TESTNET PENDING', { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText('TESTNET VERIFIED', { exact: true })).toHaveCount(
    0,
  );

  const internalLinks = await page
    .locator('a[href]')
    .evaluateAll((links) =>
      links
        .map((link) => (link as HTMLAnchorElement).getAttribute('href'))
        .filter((href): href is string => Boolean(href?.startsWith('/'))),
    );
  for (const href of new Set(internalLinks)) {
    const response = await request.get(href);
    expect(response.status(), `${href} should resolve`).toBe(200);
  }

  const fragmentLinks = await page
    .locator('a[href^="#"]')
    .evaluateAll((links) =>
      links.map((link) => (link as HTMLAnchorElement).hash.slice(1)),
    );
  for (const id of fragmentLinks) {
    expect(
      await page.locator(`[id="${id}"]`).count(),
      `#${id} should resolve`,
    ).toBe(1);
  }
  expect(consoleErrors).toEqual([]);
});

test('passes automated accessibility and keyboard smoke checks', async ({
  page,
}) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);

  await page.keyboard.press('Tab');
  await expect(page.locator('.skip-link')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#evidence')).toBeFocused();
});

test('has no horizontal overflow at the 320px mobile boundary', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/');
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});
