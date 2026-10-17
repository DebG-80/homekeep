// The elder conversation surface (BRD §11.1; TDD §8.2–8.5; plan G4-8).
//
// Large microphone and stop controls, text input, transcript, the current appliance or issue and
// one next action. States IDLE → LISTENING → PROCESSING → SPEAKING → LISTENING, plus PAUSED and
// DISCONNECTED, shown by a large label and announced through a live region. Every outcome is the
// server's text; this view never claims a booking or a write on its own.

import { Api, ApiError, NetworkError, type TurnRequest, type TurnResponse } from "../api";
import { h, newId } from "../dom";
import {
  bargeInCommand,
  ECHO_THRESHOLD,
  Recognizer,
  similarity,
  Speaker,
  voiceSupported,
  type ClientState,
  type Heard,
} from "../voice";

const STATE_LABELS: Record<ClientState, string> = {
  IDLE: "Ready",
  LISTENING: "Listening…",
  PROCESSING: "Working on it…",
  SPEAKING: "Speaking…",
  PAUSED: "Paused",
  DISCONNECTED: "Connection lost",
};

// Spoken by the client itself (TDD §8.3); everything else comes from the server.
const LOCAL = {
  stillWorking: "One moment, I'm still working on that.",
  reprompt: "Are you still there? Take your time.",
  paused: "I'll pause here. Your progress is saved.",
  lost: "I lost the connection. I'll check what was saved.",
  micBlocked: "I need the microphone to hear you. You can type instead.",
  noVoice: "Voice isn't available in this browser. Please type instead.",
  signedOut: "You no longer have access. Please sign in again.",
};
const SLOW_MS = 4_000;
const REPROMPT_MS = 15_000;
const PAUSE_MS = 20_000;
const SESSION_KEY = "hk.session";

interface HouseholdSummary {
  appliances: { appliance_id: string; nickname: string }[];
  open_issues: { appliance_id: string; summary: string; status: string }[];
}

export type View = HTMLElement & { dispose?: () => void };
const STOP_ECHO_MS = 3_000;

export function talkView(api: Api): View {
  const speaker = new Speaker();
  const listeners = new AbortController(); // removed when the view goes (dispose)
  let state: ClientState = "IDLE";
  let sessionId = sessionStorage.getItem(SESSION_KEY);
  let unsent: TurnRequest | null = null;
  let lastSpoken = "";
  let lastPlaybackEnd: Date | null = null;
  let rate = 1;
  let awaitingApproval = false;
  let silenceTimer: number | undefined;
  let reprompted = false;
  let interimStopAt = 0;

  const stateLabel = h("p", { id: "state", class: "state", role: "status", "aria-live": "assertive" });
  const notice = h("p", { id: "notice", class: "notice", "aria-live": "polite" });
  const voiceNote = h("p", { id: "voice-note", class: "voice-note" });
  const transcript = h("ol", { id: "transcript", class: "transcript", "aria-live": "polite" });
  const context = h("p", { id: "context", class: "context" });
  const nextAction = h("p", { id: "next-action", class: "next-action" });
  const input = h("input", {
    id: "say",
    type: "text",
    autocomplete: "off",
    "aria-label": "Type what you want to say",
    placeholder: "Type here and press Enter",
  });
  const mic = h("button", { id: "mic", type: "button", class: "big mic", "aria-pressed": "false" });
  const stop = h("button", { id: "stop", type: "button", class: "big stop" }, "Stop");
  const root: View = h("section", { class: "talk", "aria-label": "Talk to HomeKeep" });

  const recognizer = new Recognizer(onHeard, onInterim, onRecognitionError);

  function setState(next: ClientState): void {
    state = next;
    root.dataset["state"] = next;
    stateLabel.textContent = STATE_LABELS[next];
    mic.textContent = recognizer.listening ? "Mute microphone" : "Start talking";
    mic.setAttribute("aria-pressed", String(recognizer.listening));
    clearTimeout(silenceTimer);
    if (next === "LISTENING") resetSilence();
  }

  function addLine(who: "You" | "HomeKeep", text: string): void {
    transcript.append(h("li", { class: who === "You" ? "you" : "homekeep" }, h("strong", {}, `${who}: `), text));
    transcript.lastElementChild?.scrollIntoView({ block: "nearest" });
  }

  async function say(chunks: string[]): Promise<void> {
    setState("SPEAKING");
    const played = await speaker.speak(chunks, rate);
    if (played.superseded) return; // cancelled or replaced: whoever replaced it owns the state
    // Only playback that really finished can count as "the read-back ended" (TDD §4.3 rule 2).
    if (played.completed) lastPlaybackEnd = played.endedAt;
    setState(recognizer.listening ? "LISTENING" : "IDLE");
  }

  function resetSilence(): void {
    clearTimeout(silenceTimer);
    if (state !== "LISTENING") return;
    silenceTimer = window.setTimeout(
      () => {
        if (state !== "LISTENING") return;
        if (!reprompted) {
          reprompted = true;
          void say([LOCAL.reprompt]);
        } else {
          recognizer.stop();
          reprompted = false;
          void say([LOCAL.paused]).then(() => setState("PAUSED"));
        }
      },
      reprompted ? PAUSE_MS : REPROMPT_MS,
    );
  }

  async function ensureSession(): Promise<string> {
    if (!sessionId) {
      sessionId = (await api.startSession()).session_id;
      sessionStorage.setItem(SESSION_KEY, sessionId);
    }
    return sessionId;
  }

  async function show(response: TurnResponse): Promise<void> {
    unsent = null;
    notice.textContent = "";
    lastSpoken = response.speech.join(" ");
    rate = response.speech_rate === "slow" ? 0.8 : 1;
    awaitingApproval = Boolean(response.awaiting_approval);
    addLine("HomeKeep", lastSpoken);
    void refreshContext();
    await say(response.speech);
  }

  async function submit(turn: TurnRequest): Promise<void> {
    unsent = turn;
    setState("PROCESSING");
    const slow = window.setTimeout(() => {
      if (state === "PROCESSING" && "speechSynthesis" in window) {
        void speaker.speak([LOCAL.stillWorking], rate);
      }
    }, SLOW_MS);
    try {
      await show(await api.turn(turn));
    } catch (error) {
      if (error instanceof NetworkError) {
        setState("DISCONNECTED");
        notice.textContent = LOCAL.lost; // never claims the write (TDD §8.3)
        void speaker.speak([LOCAL.lost], rate);
      } else if (error instanceof ApiError && error.reason === "NOT_FOUND") {
        sessionStorage.removeItem(SESSION_KEY); // the session ended (a reset, say): start anew
        sessionId = null;
        unsent = null;
        await dispatch(turn.text, turn.channel, turn.client_state, turn.speech_started_at);
      } else if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        unsent = null;
        notice.textContent = LOCAL.signedOut;
        setState("IDLE");
      } else {
        unsent = null;
        notice.textContent = "Something went wrong. Please try again.";
        setState("IDLE");
      }
    } finally {
      clearTimeout(slow);
    }
  }

  async function send(
    text: string,
    channel: "voice" | "text",
    heardIn?: ClientState,
    startedAt?: string,
  ): Promise<void> {
    addLine("You", text);
    await dispatch(text, channel, heardIn, startedAt);
  }

  async function dispatch(
    text: string,
    channel: "voice" | "text",
    heardIn?: string,
    startedAt?: string,
  ): Promise<void> {
    let id: string;
    try {
      id = await ensureSession();
    } catch {
      setState("DISCONNECTED");
      notice.textContent = LOCAL.lost;
      return;
    }
    const turn: TurnRequest = { session_id: id, turn_id: newId("turn"), text, channel };
    if (channel === "voice") {
      turn.client_state = heardIn ?? state; // the state the words were heard in, never assumed
      if (startedAt) turn.speech_started_at = startedAt;
    }
    if (lastPlaybackEnd) turn.playback_ended_at = lastPlaybackEnd.toISOString();
    await submit(turn);
  }

  async function reconnect(): Promise<void> {
    if (state !== "DISCONNECTED" || !unsent || !sessionId) return;
    try {
      await api.sessionState(sessionId); // what was saved, before retrying (TDD §8.3)
    } catch {
      return;
    }
    await submit(unsent); // the same turn_id: never a duplicate request (FR-22-AC1)
  }

  async function stopNow(): Promise<void> {
    speaker.cancel();
    if (!sessionId) {
      setState(recognizer.listening ? "LISTENING" : "IDLE");
      return;
    }
    try {
      await show(await api.stop(sessionId, newId("stop"), recognizer.listening ? "voice" : "text"));
    } catch {
      setState(recognizer.listening ? "LISTENING" : "IDLE");
    }
  }

  function repeatLast(): void {
    if (lastSpoken) void say([lastSpoken]);
  }

  function bargeIn(text: string): "STOP" | "REPEAT" | "SLOWER" | null {
    // While speaking, only stop, repeat and slower count, and never an echo of our own words.
    const command = bargeInCommand(text);
    return command && similarity(text, speaker.text) < ECHO_THRESHOLD ? command : null;
  }

  function onInterim(text: string): void {
    if (!root.isConnected) return;
    resetSilence();
    // "Stop" acts on the interim result: Chrome's final one can lag by a second or two (§8.3).
    if (state === "SPEAKING" && bargeIn(text) === "STOP") {
      interimStopAt = Date.now();
      void stopNow();
    }
  }

  function onHeard(heard: Heard): void {
    if (!root.isConnected) return;
    resetSilence();
    reprompted = false;
    const command = bargeInCommand(heard.text);
    if (command === "STOP" && Date.now() - interimStopAt < STOP_ECHO_MS) return; // already done
    if (state === "SPEAKING") {
      const heardCommand = bargeIn(heard.text);
      if (!heardCommand) return; // everything else heard while speaking is discarded (§8.4)
      if (heardCommand === "STOP") void stopNow();
      else {
        speaker.cancel();
        void send(heard.text, "voice", "SPEAKING", heard.startedAt.toISOString());
      }
      return;
    }
    if (state !== "LISTENING") return; // approvals are never taken outside LISTENING
    void send(heard.text, "voice", "LISTENING", heard.startedAt.toISOString());
  }

  function onRecognitionError(code: string): void {
    if (code === "not-allowed" || code === "service-not-allowed" || code === "unsupported") {
      recognizer.stop();
      notice.textContent = code === "unsupported" ? LOCAL.noVoice : LOCAL.micBlocked;
      voiceNote.textContent = "Voice test: blocked. Text mode works, but it is not a voice pass.";
      setState("IDLE");
      input.focus();
    }
  }

  function toggleMic(): void {
    if (recognizer.listening) {
      recognizer.stop();
      setState("IDLE");
      return;
    }
    if (!voiceSupported()) {
      onRecognitionError("unsupported");
      return;
    }
    reprompted = false;
    recognizer.start();
    setState(state === "SPEAKING" ? "SPEAKING" : "LISTENING");
  }

  async function refreshContext(): Promise<void> {
    nextAction.textContent = awaitingApproval
      ? "Next: say “yes” to go ahead, or “no” to stop."
      : "Next: tell me what's wrong, or ask about a visit.";
    try {
      const household = await api.request<HouseholdSummary>("GET", "/api/household");
      const issue = household.open_issues[0];
      const appliance = household.appliances.find((a) => a.appliance_id === issue?.appliance_id);
      context.textContent = issue
        ? `Now: ${appliance?.nickname ?? "your appliance"}: ${issue.summary}`
        : "Now: no open problems.";
    } catch {
      // the context line is a convenience; the conversation does not depend on it
    }
  }

  const form = h(
    "form",
    {
      class: "say-form",
      onsubmit: (event: Event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text || state === "PROCESSING") return;
        input.value = "";
        speaker.cancel();
        void send(text, "text");
      },
    },
    input,
    h("button", { id: "send", type: "submit", class: "send" }, "Send"),
  );
  mic.addEventListener("click", toggleMic);
  stop.addEventListener("click", () => void stopNow());
  window.addEventListener("online", () => void reconnect(), { signal: listeners.signal });

  document.addEventListener(
    "keydown",
    (event) => {
      if (!root.isConnected) return;
      const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement;
      if (event.key === "Escape") {
        event.preventDefault();
        void stopNow();
      } else if (!typing && event.key === " " && !(event.target instanceof HTMLButtonElement)) {
        event.preventDefault();
        toggleMic();
      } else if (!typing && (event.key === "r" || event.key === "R")) {
        repeatLast();
      }
    },
    { signal: listeners.signal },
  );

  root.append(
    stateLabel,
    h("div", { class: "controls" }, mic, stop),
    h(
      "p",
      { class: "hint" },
      "Keys: Space starts or mutes the microphone, Esc stops, R repeats, Enter sends typed text.",
    ),
    notice,
    voiceNote,
    context,
    nextAction,
    h("h2", { class: "visually-hidden" }, "Conversation"),
    transcript,
    form,
    h(
      "button",
      { id: "retry", type: "button", class: "retry", onclick: () => void reconnect() },
      "Check the connection again",
    ),
  );
  root.dispose = () => {
    // Leaving the page: no microphone, no speech, no background retries (FR-21-AC2).
    recognizer.stop();
    speaker.cancel();
    clearTimeout(silenceTimer);
    listeners.abort();
  };
  setState("IDLE");
  void refreshContext();
  return root;
}
