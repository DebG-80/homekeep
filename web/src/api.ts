// The HomeKeep REST API: bearer token on every call. Network failures and HTTP errors are
// distinct, so the talk view can say "I lost the connection" without claiming any write.

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly reason: string,
  ) {
    super(`${status} ${reason}`);
  }
}

export class NetworkError extends Error {}

export interface TurnResponse {
  session_id: string;
  turn_id: string;
  correlation_id: string;
  speech: string[];
  speech_rate: "normal" | "slow";
  handled_by: string;
  guarded: boolean;
  display: { citation: Record<string, string> | null; demo_badge: string };
  awaiting_approval?: { pending_ref: string; expires_at: string } | null;
}

export interface TurnRequest {
  session_id: string;
  turn_id: string;
  text: string;
  channel: "voice" | "text";
  client_state?: string;
  speech_started_at?: string;
  playback_ended_at?: string;
}

export class Api {
  constructor(private readonly token: () => Promise<string>) {}

  async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    let token: string;
    try {
      token = await this.token();
    } catch {
      token = "";
    }
    if (!token) {
      // The sign-in ended (revoked, or the refresh token expired): not a lost connection.
      throw new ApiError(401, "SIGNED_OUT");
    }
    let response: Response;
    try {
      response = await fetch(path, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new NetworkError("network");
    }
    if (!response.ok) {
      let reason = String(response.status);
      try {
        const data = (await response.json()) as { error?: { reason?: string } };
        reason = data.error?.reason ?? reason;
      } catch {
        // not JSON
      }
      throw new ApiError(response.status, reason);
    }
    return (await response.json()) as T;
  }

  startSession(): Promise<{ session_id: string }> {
    return this.request("POST", "/api/sessions");
  }

  turn(body: TurnRequest): Promise<TurnResponse> {
    return this.request("POST", "/api/turns", body);
  }

  stop(sessionId: string, turnId: string, channel: "voice" | "text"): Promise<TurnResponse> {
    return this.request("POST", `/api/sessions/${sessionId}/stop`, { turn_id: turnId, channel });
  }

  sessionState(sessionId: string): Promise<{ pending_approval_id: string | null }> {
    return this.request("GET", `/api/sessions/${sessionId}/state`);
  }
}
