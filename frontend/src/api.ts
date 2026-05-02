import type { ProviderKeyView, ProviderMetadata, RunCreate, RunView } from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function getProviders(): Promise<ProviderMetadata[]> {
  const data = await request<{ providers: ProviderMetadata[] }>("/api/providers");
  return data.providers;
}

export async function getKeys(): Promise<ProviderKeyView[]> {
  const data = await request<{ keys: ProviderKeyView[] }>("/api/keys");
  return data.keys;
}

export async function saveKey(provider: string, apiKey: string): Promise<ProviderKeyView> {
  return request<ProviderKeyView>("/api/keys", {
    method: "POST",
    body: JSON.stringify({ provider, api_key: apiKey }),
  });
}

export async function deleteKey(provider: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/keys/${provider}`, { method: "DELETE" });
}

export async function createRun(payload: RunCreate): Promise<RunView> {
  return request<RunView>("/api/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getRuns(): Promise<RunView[]> {
  const data = await request<{ runs: RunView[] }>("/api/runs");
  return data.runs;
}

export async function getRun(runId: string): Promise<RunView> {
  return request<RunView>(`/api/runs/${runId}`);
}

export function exportUrl(runId: string): string {
  return `${API_BASE}/api/runs/${runId}/export`;
}

export function runEventSource(runId: string): EventSource {
  return new EventSource(`${API_BASE}/api/runs/${runId}/events`);
}
