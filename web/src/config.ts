// Sign-in settings from the server (GET /api/config). None of them is secret.

export interface CognitoConfig {
  authority: string;
  domain: string;
  client_id: string;
  redirect_uri: string;
  scope: string;
}

export interface ClientConfig {
  env: string;
  local_sign_in: boolean;
  cognito: CognitoConfig | null;
}

export async function loadConfig(): Promise<ClientConfig> {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error(`config ${response.status}`);
  return (await response.json()) as ClientConfig;
}
