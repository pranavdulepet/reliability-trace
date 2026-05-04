import type {
  ConversationMessage,
  ConversationSummary,
  ConversationView,
  DocumentMatch,
  DocumentView,
  ProviderKeyView,
  ProviderMetadata,
  ProviderPreferenceResponse,
  RunCreate,
  RunView,
  SearchMode,
  SearchPreferenceResponse,
} from "./types";

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

export async function getProviderPreference(): Promise<ProviderPreferenceResponse> {
  return request<ProviderPreferenceResponse>("/api/provider-preferences");
}

export async function saveProviderPreference(payload: {
  provider: string | null;
  model: string | null;
  samples: number;
  max_cost_usd: number;
}): Promise<ProviderPreferenceResponse> {
  return request<ProviderPreferenceResponse>("/api/provider-preferences", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function getSearchPreference(): Promise<SearchPreferenceResponse> {
  return request<SearchPreferenceResponse>("/api/search-preferences");
}

export async function saveSearchPreference(payload: {
  search_mode: SearchMode;
  max_results: number;
}): Promise<SearchPreferenceResponse> {
  return request<SearchPreferenceResponse>("/api/search-preferences", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function saveSearchKey(apiKey: string): Promise<SearchPreferenceResponse["key"]> {
  return request<SearchPreferenceResponse["key"]>("/api/search-key", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function deleteSearchKey(): Promise<void> {
  await request<{ deleted: boolean }>("/api/search-key", { method: "DELETE" });
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

export async function getConversations(): Promise<ConversationSummary[]> {
  const data = await request<{ conversations: ConversationSummary[] }>("/api/conversations");
  return data.conversations;
}

export async function createConversation(title?: string): Promise<ConversationView> {
  return request<ConversationView>("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export async function getConversation(conversationId: string): Promise<ConversationView> {
  return request<ConversationView>(`/api/conversations/${conversationId}`);
}

export async function sendConversationMessage(
  conversationId: string,
  payload: {
    content: string;
    attachment_document_ids: string[];
    search_mode?: SearchMode;
  },
): Promise<{ message: ConversationMessage; run: RunView }> {
  return request<{ message: ConversationMessage; run: RunView }>(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDocuments(): Promise<DocumentView[]> {
  const data = await request<{ documents: DocumentView[] }>("/api/documents");
  return data.documents;
}

export async function uploadDocument(payload: {
  title: string;
  text: string;
  source_url?: string | null;
  source_type?: string;
}): Promise<DocumentView> {
  return request<DocumentView>("/api/documents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchSourceUrl(url: string): Promise<DocumentView> {
  return request<DocumentView>("/api/documents/fetch", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function searchDocuments(q: string): Promise<DocumentMatch[]> {
  const data = await request<{ matches: DocumentMatch[] }>(`/api/documents/search?q=${encodeURIComponent(q)}`);
  return data.matches;
}

export function exportUrl(runId: string): string {
  return `${API_BASE}/api/runs/${runId}/export`;
}

export function runEventSource(runId: string): EventSource {
  return new EventSource(`${API_BASE}/api/runs/${runId}/events`);
}
