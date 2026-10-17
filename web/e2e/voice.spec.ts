// The voice client's approval timing and barge-in rules (TDD §4.3 rules 2–3, §8.3, §8.4), with
// speech stubbed. These check the client's state machine; they are not a voice pass (FR-21-AC2).

import { expect, test, type Page, type Request } from "@playwright/test";
import { script, signIn, stubSpeech } from "./helpers";

type TurnBody = {
  text: string;
  client_state?: string;
  playback_ended_at?: string;
  speech_started_at?: string;
};

const hear = (page: Page, text: string, isFinal = true) =>
  page.evaluate(
    ([t, f]) => (window as unknown as { __rec: { emit: (t: string, f: boolean) => void } }).__rec.emit(t as string, f as boolean),
    [text, isFinal],
  );
const finishSpeaking = (page: Page) =>
  page.evaluate(() => (window as unknown as { __speech: { finish: () => void } }).__speech.finish());
const state = (page: Page) => page.locator(".talk");

function turns(page: Page): TurnBody[] {
  const seen: TurnBody[] = [];
  page.on("request", (request: Request) => {
    if (request.url().endsWith("/api/turns")) seen.push(request.postDataJSON() as TurnBody);
  });
  return seen;
}

test("c1: a yes is never sent during or after an unfinished read-back", async ({ page, request }) => {
  test.setTimeout(60_000);
  await stubSpeech(page, "controlled");
  await signIn(page, "a_owner");
  const sent = turns(page);
  await page.locator("#mic").click();
  await expect(state(page)).toHaveAttribute("data-state", "LISTENING");

  await script(request, [{ call: "prepare_action", input: { kind: "CONSENT_SHARING" } }, { say: "" }]);
  await hear(page, "Please share updates with my family");
  await expect(state(page)).toHaveAttribute("data-state", "SPEAKING"); // read-back R1 playing

  await hear(page, "repeat that"); // barge-in: R1 is cancelled, the repeat request goes out
  await expect.poll(() => sent.length).toBe(2);
  await expect(state(page)).toHaveAttribute("data-state", "SPEAKING"); // R2 (the repeat) playing
  // Neither R1's cancelled playback nor a guess at R2's length may end SPEAKING: only R2
  // really finishing does. (A time estimate for this read-back would have fired by now.)
  await page.waitForTimeout(10_000);
  await expect(state(page)).toHaveAttribute("data-state", "SPEAKING");
  await hear(page, "yes"); // while R2 is still playing
  await page.waitForTimeout(300);
  expect(sent.map((t) => t.text)).toEqual(["Please share updates with my family", "repeat that"]);
  await expect(state(page)).toHaveAttribute("data-state", "SPEAKING");

  await finishSpeaking(page); // R2 finishes properly
  await expect(state(page)).toHaveAttribute("data-state", "LISTENING");
  const finishedAt = await page.evaluate(() => (window as unknown as { __speech: { finishedAt: number } }).__speech.finishedAt);
  await hear(page, "yes");
  await expect.poll(() => sent.length).toBe(3);
  const yes = sent[2]!;
  expect(yes.client_state).toBe("LISTENING");
  expect(Date.parse(yes.playback_ended_at!)).toBeGreaterThanOrEqual(finishedAt - 5);
  expect(Date.parse(yes.speech_started_at!)).toBeGreaterThan(Date.parse(yes.playback_ended_at!));
  await expect(page.locator("#transcript li.homekeep").last()).toContainText("share updates");
});

test("i5: an interim 'stop' cuts speech at once and stops only once", async ({ page, request }) => {
  await stubSpeech(page, "controlled");
  await signIn(page, "a_owner");
  const stops: string[] = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/stop")) stops.push(r.url());
  });
  await page.locator("#mic").click();
  await script(request, [{ call: "prepare_action", input: { kind: "CONSENT_SHARING" } }, { say: "" }]);
  await hear(page, "Please share updates with my family");
  await expect(state(page)).toHaveAttribute("data-state", "SPEAKING");
  const before = await page.evaluate(() => (window as unknown as { __speech: { cancelled: number } }).__speech.cancelled);

  await hear(page, "stop", false); // the interim result, before Chrome finalises it
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __speech: { cancelled: number } }).__speech.cancelled))
    .toBeGreaterThan(before);
  await expect.poll(() => stops.length).toBe(1);
  await hear(page, "stop", true); // the final result for the same word
  await page.waitForTimeout(500);
  expect(stops.length).toBe(1);
});

test("i4: leaving the Talk page turns the microphone off", async ({ page }) => {
  await stubSpeech(page, "controlled");
  await signIn(page, "a_owner");
  const sent = turns(page);
  await page.locator("#mic").click();
  await expect(state(page)).toHaveAttribute("data-state", "LISTENING");
  await page.locator('a[href="#/household"]').click();
  await expect(page.locator("#household-heading")).toBeVisible();
  const active = await page.evaluate(() => (window as unknown as { __rec: { rec: { active: boolean } } }).__rec.rec.active);
  expect(active).toBe(false); // no audio is captured once the view is gone
  await hear(page, "hello");
  await page.waitForTimeout(300);
  expect(sent).toEqual([]);
});
