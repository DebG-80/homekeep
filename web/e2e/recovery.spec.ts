// AT-23 with stubbed speech (plan G4-9): these check the client's recovery rules. They are not a
// voice pass (FR-21-AC2); Deb's recorded runs follow docs/voice-test-checklist.md.

import { expect, test } from "@playwright/test";
import { sayText, script, signIn, stubSpeech, token } from "./helpers";

test("a denied microphone falls back to text and says why", async ({ page }) => {
  await stubSpeech(page, "denied");
  await signIn(page, "a_owner");
  await page.locator("#mic").click();
  await expect(page.locator("#notice")).toHaveText("I need the microphone to hear you. You can type instead.");
  await expect(page.locator("#voice-note")).toContainText("not a voice pass");
  await expect(page.locator("#say")).toBeFocused();
  expect(await sayText(page, "Hello")).not.toBe(""); // text still works
});

test("offline: never claims the write, then retries the same turn on reconnect", async ({ page, context }) => {
  await stubSpeech(page);
  await signIn(page, "a_owner");
  await sayText(page, "Hello");

  await context.setOffline(true);
  const lost = page.waitForEvent("requestfailed", (r) => r.url().endsWith("/api/turns"));
  await page.locator("#say").fill("What appliances do I have?");
  await page.locator("#say").press("Enter");
  const lostTurn = (await lost).postDataJSON() as { turn_id: string };
  await expect(page.locator(".talk")).toHaveAttribute("data-state", "DISCONNECTED");
  await expect(page.locator("#notice")).toHaveText("I lost the connection. I'll check what was saved.");
  const replies = page.locator("#transcript li.homekeep");
  const before = await replies.count();

  const retried = page.waitForRequest((r) => r.url().endsWith("/api/turns") && r.method() === "POST");
  await context.setOffline(false); // the browser's "online" event triggers the retry
  const body = (await retried).postDataJSON() as { turn_id: string; text: string };
  expect(body.text).toBe("What appliances do I have?");
  expect(body.turn_id).toBe(lostTurn.turn_id); // the same turn: never a duplicate (FR-22-AC1)
  await expect(replies).toHaveCount(before + 1);
  await expect(page.locator("#notice")).toBeHidden();
});

test("stop cancels the pending action and keeps what was said", async ({ page, request }) => {
  await stubSpeech(page);
  await signIn(page, "a_owner");
  await script(request, [{ call: "prepare_action", input: { kind: "CONSENT_SHARING" } }, { say: "" }]);
  expect(await sayText(page, "Please share updates with my family")).toContain("May I share updates");

  const replies = page.locator("#transcript li.homekeep");
  const before = await replies.count();
  await page.keyboard.press("Escape");
  await expect(replies).toHaveCount(before + 1);
  await expect(replies.last()).toContainText("Okay, I've stopped. Nothing new was saved or sent.");

  const sessionId = await page.evaluate(() => sessionStorage.getItem("hk.session"));
  const state = await request.get(`/api/sessions/${sessionId}/state`, {
    headers: { Authorization: `Bearer ${await token(request, "a_owner")}` },
  });
  const saved = (await state.json()) as { pending_approval_id: string | null; messages: unknown[] };
  expect(saved.pending_approval_id).toBeNull();
  expect(saved.messages.length).toBeGreaterThanOrEqual(4);
});
