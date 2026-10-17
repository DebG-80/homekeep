// AT-30: axe finds nothing on the talk, household and staff views; the keyboard controls work;
// nothing scrolls sideways at 200% zoom (TDD §8.5; NFR-03).

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { sayText, signIn, stubSpeech } from "./helpers";

async function noViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

async function noSidewaysScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test("talk, household and staff views pass axe", async ({ page, browser }) => {
  await stubSpeech(page);
  await signIn(page, "a_owner");
  await sayText(page, "Hello");
  await noViolations(page);
  await page.locator('a[href="#/household"]').click();
  await expect(page.locator(".appliances")).toBeVisible();
  await noViolations(page);

  const staffContext = await browser.newContext();
  const staff = await staffContext.newPage();
  await stubSpeech(staff);
  await signIn(staff, "coordinator");
  await expect(staff.locator("#staff-heading")).toHaveText("All cases");
  await noViolations(staff);
  await staffContext.close();
});

test("keyboard: Space, Esc, Enter and R", async ({ page }) => {
  await stubSpeech(page);
  await signIn(page, "a_owner");
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("Space");
  await expect(page.locator("#state")).toHaveText("Listening…");
  await expect(page.locator("#mic")).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Space");
  await expect(page.locator("#state")).toHaveText("Ready");

  await page.locator("#say").fill("Hello");
  await page.locator("#say").press("Enter");
  await expect(page.locator("#transcript li.you")).toHaveText("You: Hello");
  await expect(page.locator(".talk")).toHaveAttribute("data-state", "IDLE");

  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("r");
  await expect(page.locator(".talk")).toHaveAttribute("data-state", "IDLE"); // replayed and done
  await page.keyboard.press("Escape");
  await expect(page.locator("#transcript li.homekeep").last()).toContainText("Okay, I've stopped.");
});

test("no sideways scrolling at 200% zoom", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 640, height: 900 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await stubSpeech(page);
  await signIn(page, "a_owner");
  await sayText(page, "Hello");
  await noSidewaysScroll(page);
  await page.locator('a[href="#/household"]').click();
  await expect(page.locator(".appliances")).toBeVisible();
  await noSidewaysScroll(page);
  await context.close();
});
