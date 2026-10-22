// Sign-in (TDD §9.1; plan G4-2). On AWS: Cognito managed login with PKCE through oidc-client-ts,
// with the refresh token in sessionStorage so a reload resumes the session. Locally: a picker of
// the seeded fixture identities (ENV=local only). The client never handles a household ID.

import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import type { ClientConfig } from "./config";
import { h } from "./dom";

export class SignInError extends Error {}

export interface Identity {
  token: () => Promise<string>;
  groups: string[];
  name: string;
  signOut: () => Promise<void>;
}

const LOCAL_KEY = "hk.local.identity";
export const LOCAL_IDENTITIES: ReadonlyArray<[string, string]> = [
  ["j1_owner", "Judge household 1 (owner)"],
  ["j2_owner", "Judge household 2 (owner)"],
  ["a_owner", "QA household A (owner)"],
  ["a_helper_booking", "QA household A (booking helper)"],
  ["a_helper_view", "QA household A (view-only helper)"],
  ["tech_assigned", "Technician (assigned)"],
  ["coordinator", "Coordinator"],
];

function claims(token: string): Record<string, unknown> {
  const payload = token.split(".")[1] ?? "";
  const json = atob(payload.replaceAll("-", "+").replaceAll("_", "/"));
  return JSON.parse(json) as Record<string, unknown>;
}

export function groupsOf(token: string): string[] {
  const value = claims(token)["cognito:groups"];
  return Array.isArray(value) ? value.map(String) : [];
}

async function localToken(identity: string): Promise<string> {
  const response = await fetch("/local/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identity }),
  });
  if (!response.ok) throw new Error(`local sign-in ${response.status}`);
  return ((await response.json()) as { access_token: string }).access_token;
}

function localIdentity(identity: string, token: string): Identity {
  let current = token;
  return {
    token: async () => current,
    groups: groupsOf(token),
    name: LOCAL_IDENTITIES.find(([key]) => key === identity)?.[1] ?? identity,
    signOut: async () => {
      sessionStorage.removeItem(LOCAL_KEY);
      current = "";
      location.hash = "";
      location.reload();
    },
  };
}

function pickLocal(root: HTMLElement): Promise<Identity> {
  return new Promise((resolve) => {
    const list = h("ul", { class: "identity-list" });
    for (const [key, label] of LOCAL_IDENTITIES) {
      list.append(
        h(
          "li",
          {},
          h(
            "button",
            {
              type: "button",
              class: "big",
              "data-identity": key,
              onclick: async () => {
                const token = await localToken(key);
                sessionStorage.setItem(LOCAL_KEY, key);
                resolve(localIdentity(key, token));
              },
            },
            label,
          ),
        ),
      );
    }
    root.replaceChildren(
      h(
        "main",
        { id: "main" },
        h("h1", {}, "HomeKeep"),
        h("p", {}, "Local sign-in: choose a test identity. This appears only in local runs."),
        list,
      ),
    );
  });
}

async function cognitoIdentity(config: ClientConfig): Promise<Identity> {
  const cognito = config.cognito;
  if (!cognito) throw new Error("no sign-in configured");
  const manager = new UserManager({
    authority: cognito.authority,
    client_id: cognito.client_id,
    redirect_uri: cognito.redirect_uri,
    post_logout_redirect_uri: cognito.post_logout_redirect_uri,
    response_type: "code",
    scope: cognito.scope,
    userStore: new WebStorageStateStore({ store: sessionStorage }),
    automaticSilentRenew: false,
  });
  const query = new URLSearchParams(location.search);
  if (query.has("error")) {
    // Cognito sent the user back with an error: say so, rather than redirecting in a loop.
    history.replaceState(null, "", "/");
    throw new SignInError("Sign-in didn't complete. Please reload the page to try again.");
  }
  if (query.has("code") && query.has("state")) {
    await manager.signinRedirectCallback();
    history.replaceState(null, "", "/"); // leave /auth/callback: the app lives at /
  }
  let user = await manager.getUser();
  if (!user || user.expired) {
    try {
      user = user?.refresh_token ? await manager.signinSilent() : null;
    } catch {
      user = null;
    }
  }
  if (!user) {
    await manager.signinRedirect();
    return new Promise(() => undefined); // the browser is leaving for the sign-in page
  }
  return {
    token: async () => {
      const latest = await manager.getUser();
      if (latest && !latest.expired) return latest.access_token;
      const renewed = await manager.signinSilent();
      return renewed?.access_token ?? "";
    },
    groups: groupsOf(user.access_token),
    name: String(user.profile["cognito:username"] ?? user.profile.sub),
    signOut: async () => {
      await manager.removeUser();
      location.href = `${cognito.domain}/logout?client_id=${encodeURIComponent(
        cognito.client_id,
      )}&logout_uri=${encodeURIComponent(cognito.post_logout_redirect_uri)}`;
    },
  };
}

export async function signIn(config: ClientConfig, root: HTMLElement): Promise<Identity> {
  if (config.local_sign_in) {
    const remembered = sessionStorage.getItem(LOCAL_KEY);
    if (remembered) {
      try {
        return localIdentity(remembered, await localToken(remembered));
      } catch {
        sessionStorage.removeItem(LOCAL_KEY);
      }
    }
    return pickLocal(root);
  }
  return cognitoIdentity(config);
}
