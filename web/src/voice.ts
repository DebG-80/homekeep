// Speech in and out for the elder (TDD §8.1, §8.4; plan G4-8). Chrome's SpeechRecognition with
// en-IN, continuous, interim results, restarted automatically while wanted; speechSynthesis split
// into sentences, preferring an en-IN voice. Audio is never stored by HomeKeep.

export type ClientState = "IDLE" | "LISTENING" | "PROCESSING" | "SPEAKING" | "PAUSED" | "DISCONNECTED";

// Barge-in grammar heard while HomeKeep is speaking, mirroring the server's (app/channel/guards.py).
const BARGE_IN: Record<"STOP" | "REPEAT" | "SLOWER", string[]> = {
  STOP: ["stop", "cancel", "never mind", "nevermind", "stop it", "stop talking", "no stop"],
  REPEAT: ["repeat", "say that again", "say it again", "pardon", "what did you say", "repeat that"],
  SLOWER: ["slower", "speak slowly", "speak slower", "slow down", "more slowly", "talk slower"],
};
const FILLER = /\b(please|ok(ay)?|can you|could you|just)\b/g;
export const ECHO_THRESHOLD = 0.6;

export function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z' ]/g, " ")
    .replace(FILLER, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function bargeInCommand(text: string): "STOP" | "REPEAT" | "SLOWER" | null {
  const said = normalise(text);
  for (const [command, phrases] of Object.entries(BARGE_IN)) {
    if (phrases.includes(said)) return command as "STOP" | "REPEAT" | "SLOWER";
  }
  return null;
}

/** Word-set overlap, as the server's echo rule (TDD §4.3 rule 5). */
export function similarity(a: string, b: string): number {
  const left = new Set(normalise(a).split(" ").filter(Boolean));
  const right = new Set(normalise(b).split(" ").filter(Boolean));
  if (!left.size || !right.size) return 0;
  let shared = 0;
  for (const word of left) if (right.has(word)) shared += 1;
  return shared / new Set([...left, ...right]).size;
}

interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}
interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onspeechstart: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
type RecognitionConstructor = new () => RecognitionLike;

function recognitionConstructor(): RecognitionConstructor | null {
  const scope = window as unknown as Record<string, RecognitionConstructor | undefined>;
  return scope["SpeechRecognition"] ?? scope["webkitSpeechRecognition"] ?? null;
}

export function voiceSupported(): boolean {
  return recognitionConstructor() !== null && "speechSynthesis" in window;
}

export interface Heard {
  text: string;
  startedAt: Date;
}

export class Recognizer {
  private recognition: RecognitionLike | null = null;
  private wanted = false;
  private utteranceStart: Date | null = null;

  constructor(
    private readonly onFinal: (heard: Heard) => void,
    private readonly onInterim: (text: string) => void,
    private readonly onError: (code: string) => void,
  ) {}

  get listening(): boolean {
    return this.wanted;
  }

  start(): void {
    const Recognition = recognitionConstructor();
    if (!Recognition) {
      this.onError("unsupported");
      return;
    }
    this.wanted = true;
    if (this.recognition) return;
    const recognition = new Recognition();
    recognition.lang = "en-IN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onspeechstart = () => {
      this.utteranceStart ??= new Date();
    };
    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (!result) continue;
        const text = result[0].transcript.trim();
        this.utteranceStart ??= new Date();
        if (result.isFinal) {
          const startedAt = this.utteranceStart;
          this.utteranceStart = null;
          if (text) this.onFinal({ text, startedAt });
        } else if (text) {
          this.onInterim(text);
        }
      }
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        this.wanted = false;
      }
      if (event.error !== "no-speech" && event.error !== "aborted") this.onError(event.error);
    };
    recognition.onend = () => {
      this.recognition = null;
      if (this.wanted) this.start(); // Chrome ends sessions on its own; keep listening
    };
    this.recognition = recognition;
    recognition.start();
  }

  stop(): void {
    // Muting stops recognition entirely: no audio is captured (FR-21-AC2).
    this.wanted = false;
    this.utteranceStart = null;
    this.recognition?.stop();
    this.recognition = null;
  }
}

/** How a call to `speak` ended. Only `completed` playback may set the read-back time (§4.3). */
export interface Played {
  completed: boolean; // every utterance ended normally: the whole text was played
  superseded: boolean; // cancelled, or replaced by later speech: the caller must not act on it
  endedAt: Date;
}

export class Speaker {
  private current = "";
  private generation = 0;
  private settle: (() => void) | null = null;

  get text(): string {
    return this.current;
  }

  /** Speak the chunks in order. Resolves when playback really ends, or when it is cancelled or
   * replaced (then `superseded`). An `error` event, which `cancel()` also fires, is never
   * counted as finishing. */
  speak(chunks: string[], rate: number): Promise<Played> {
    this.cancel();
    const generation = ++this.generation;
    this.current = chunks.join(" ");
    if (!("speechSynthesis" in window) || chunks.length === 0) {
      return Promise.resolve({ completed: true, superseded: false, endedAt: new Date() });
    }
    const synth = window.speechSynthesis;
    const voice = synth.getVoices().find((v) => v.lang === "en-IN") ?? null;
    const sentences = chunks.flatMap((chunk) => chunk.match(/[^.?!]+[.?!]*/g) ?? [chunk]);
    return new Promise((resolve) => {
      let remaining = sentences.length;
      let failed = false;
      let heardSpeaking = false;
      let done = false;
      const finish = (completed: boolean): void => {
        if (done) return;
        done = true;
        clearInterval(poll);
        if (this.generation === generation) this.settle = null;
        resolve({
          completed: completed && !failed && this.generation === generation,
          superseded: this.generation !== generation,
          endedAt: new Date(),
        });
      };
      this.settle = () => finish(false);
      // Some browsers never fire `end` (no voices installed): the synthesiser going quiet after
      // it was heard speaking is a real end of playback, never a guess at its length.
      const poll = window.setInterval(() => {
        if (synth.speaking || synth.pending) heardSpeaking = true;
        else if (heardSpeaking && remaining > 0 && !failed) finish(true);
      }, 250);
      for (const sentence of sentences) {
        const utterance = new SpeechSynthesisUtterance(sentence.trim());
        utterance.lang = "en-IN";
        utterance.rate = rate;
        if (voice) utterance.voice = voice;
        utterance.onend = () => {
          remaining -= 1;
          if (remaining === 0) finish(true);
        };
        utterance.onerror = () => {
          failed = true;
          remaining -= 1;
          if (remaining === 0) finish(false);
        };
        synth.speak(utterance);
      }
    });
  }

  /** Stop speaking at once; any outstanding `speak` resolves as superseded. */
  cancel(): void {
    this.generation += 1;
    const settle = this.settle;
    this.settle = null;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    settle?.();
  }
}
