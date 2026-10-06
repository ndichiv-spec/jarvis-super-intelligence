import { test, expect } from '@playwright/test';

test.describe('JARVIS Frontend Smoke Tests', () => {
  test('dashboard page loads', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveTitle(/jarvis/i);
  });

  test('chat input is visible', async ({ page }) => {
    await page.goto('/dashboard');
    const chatInput = page.locator('textarea[placeholder="Ask JARVIS anything..."]');
    await expect(chatInput).toBeVisible();
  });

  test('file attachment button is visible', async ({ page }) => {
    await page.goto('/dashboard');
    const attachButton = page.locator('button[title="Attach file"], button[title="Attach more files"]');
    await expect(attachButton).toBeVisible();
  });

  test('model selector is visible in header', async ({ page }) => {
    await page.goto('/dashboard');
    const modelSelector = page.locator('button').filter({ hasText: /Select model|Auto Select/i }).first();
    await expect(modelSelector).toBeVisible();
  });

  test('settings panel toggle is visible', async ({ page }) => {
    await page.goto('/dashboard');
    const settingsToggle = page.locator('button', { hasText: /Chat Settings/i });
    await expect(settingsToggle).toBeVisible();
  });

  test('voice input button is visible', async ({ page }) => {
    await page.goto('/dashboard');
    const micButton = page.locator('button[title="Voice input"]');
    await await expect(micButton).toBeVisible();
  });
});
