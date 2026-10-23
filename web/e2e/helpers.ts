// Shared E2E steps. The fake model is driven through the local-only script endpoint (plan G4-7),
// and record IDs are read back through the household API, as a real client would.

import { expect, type APIRequestContext, type Page } from "@playwright/test";

export type Step = { call: string; input?: Record<string, unknown> } | { say: string };

/**
 * Speech stubs. "silent": speech output finishes at once and recognition hears nothing.
 * "denied": the microphone is blocked. "controlled": the test drives both through
 * `window.__speech.finish()` and `window.__rec.emit(text, isFinal)`, as Chrome would, including
 * the `error` events that `cancel()` fires on unfinished utterances.
 */
export async function stubSpeech(
  page: Page,
  mode: "silent" | "denied" | "controlled" | "none" = "silent",
): Promise<void> {
  await page.addInitScript((mode) => {
    const pending: SpeechSynthesisUtterance[] = [];
    const speech = {
      cancelled: 0,
      finishedAt: 0,
      finish(): void {
        speech.finishedAt = Date.now();
        for (const u of pending.splice(0)) u.onend?.(new Event("end") as SpeechSynthesisEvent);
      },
    };
    const synth = {
      get speaking() {
        return pending.length > 0;
      },
      pending: false,
      paused: false,
      onvoiceschanged: null,
      getVoices: () => [],
      pause: () => undefined,
      resume: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      cancel: () => {
        speech.cancelled += 1;
        for (const u of pending.splice(0)) {
          u.onerror?.(new Event("error") as SpeechSynthesisErrorEvent);
        }
      },
      speak: (utterance: SpeechSynthesisUtterance) => {
        if (mode === "controlled") pending.push(utterance);
        else setTimeout(() => utterance.onend?.(new Event("end") as SpeechSynthesisEvent), 0);
      },
    };
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
    Object.defineProperty(window, "__speech", { value: speech, configurable: true });
    if (mode === "none") return;
    const rec = { active: false, instance: null as unknown as FakeRecognition | null };
    class FakeRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      onresult: ((event: unknown) => void) | null = null;
      onspeechstart: (() => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      start(): void {
        rec.active = true;
        rec.instance = this;
        if (mode === "denied") setTimeout(() => this.onerror?.({ error: "not-allowed" }), 0);
      }
      stop(): void {
        rec.active = false;
        setTimeout(() => this.onend?.(), 0);
      }
    }
    const emit = (text: string, isFinal: boolean): void => {
      const instance = rec.instance;
      if (!rec.active || !instance) return;
      instance.onspeechstart?.();
      instance.onresult?.({ resultIndex: 0, results: [{ isFinal, 0: { transcript: text } }] });
    };
    Object.defineProperty(window, "__rec", { value: { rec, emit }, configurable: true });
    Object.defineProperty(window, "SpeechRecognition", { value: FakeRecognition, configurable: true });
  }, mode);
}

export async function signIn(page: Page, identity: string): Promise<void> {
  await page.goto("/");
  await page.locator(`[data-identity="${identity}"]`).click();
  await expect(page.locator("header .demo-tag")).toHaveText("Demo — simulated service desk");
}

export async function token(request: APIRequestContext, identity: string): Promise<string> {
  const minted = await request.post("/local/token", { data: { identity } });
  expect(minted.ok()).toBeTruthy();
  return ((await minted.json()) as { access_token: string }).access_token;
}

export async function apiGet<T>(request: APIRequestContext, identity: string, path: string): Promise<T> {
  const response = await request.get(path, {
    headers: { Authorization: `Bearer ${await token(request, identity)}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as T;
}

export async function resetJudge(request: APIRequestContext, identity: string): Promise<void> {
  const response = await request.post("/api/household/reset", {
    headers: { Authorization: `Bearer ${await token(request, identity)}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

export async function script(request: APIRequestContext, ...turns: Step[][]): Promise<void> {
  const response = await request.post("/local/fake-model/script", { data: { turns } });
  expect(response.ok(), await response.text()).toBeTruthy();
}

/** Type a line on the Talk page and wait for HomeKeep's reply to finish. */
export async function sayText(page: Page, text: string): Promise<string> {
  const replies = page.locator("#transcript li.homekeep");
  const before = await replies.count();
  await page.locator("#say").fill(text);
  await page.locator("#say").press("Enter");
  await expect(replies).toHaveCount(before + 1);
  await expect(page.locator(".talk")).not.toHaveAttribute("data-state", /PROCESSING|SPEAKING/);
  return (await replies.last().textContent()) ?? "";
}

/** Tomorrow's morning slot in Asia/Kolkata, as the demo provider names it. */
export function tomorrowMorning(): string {
  const now = new Date(Date.now() + 24 * 3600 * 1000);
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(now);
  return `${day}#AM`;
}
