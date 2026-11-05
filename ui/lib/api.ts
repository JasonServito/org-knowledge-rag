// The API client (ADR-016 D1): one function per route the UI uses, each called on the UI's own
// address (`/api/*`), which next.config.ts forwards to the API. Each returns the parsed body, or
// a failure: the API's error, or no answer from the API at all.

import type { Answer, Chain, DecisionSummary, ErrorCode, ErrorEnvelope } from "./types";

export type ApiFailure =
  // The API answered with its error envelope (docs/interfaces.md, "Errors"). Its `message` is
  // left out: the UI shows its own message per code (S17-R1 c6).
  | { kind: "api"; status: number; code: ErrorCode; requestId: string }
  // No answer from the API: the browser couldn't reach the UI's server (status null), or the
  // forwarder couldn't reach the API or waited past API_TIMEOUT_S (Next's own plain-text 500).
  | { kind: "network"; status: number | null };

export type ApiResult<T> = { ok: true; data: T } | { ok: false; failure: ApiFailure };

// `POST /query`: paid on the API's side; ~12 s on the laptop, ~54 s on AWS.
export function askQuestion(question: string): Promise<ApiResult<Answer>> {
  return call("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

// `GET /decisions`: the stored chains, by seed (ADR-016 D4).
export function listDecisions(): Promise<ApiResult<DecisionSummary[]>> {
  return call("/api/decisions");
}

// `GET /decisions/{canonical_id}`: one stored chain, e.g. `kep:2572`.
export function getDecision(canonicalId: string): Promise<ApiResult<Chain>> {
  return call(`/api/decisions/${encodeURIComponent(canonicalId)}`);
}

async function call<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    return { ok: false, failure: { kind: "network", status: null } };
  }
  if (response.ok) {
    return { ok: true, data: (await response.json()) as T };
  }
  // Any body that isn't the envelope (e.g. "Internal Server Error") came from the forwarder.
  const body = (await response.json().catch(() => null)) as Partial<ErrorEnvelope> | null;
  const error = body?.error;
  if (error?.code === undefined || error.request_id === undefined) {
    return { ok: false, failure: { kind: "network", status: response.status } };
  }
  const { code, request_id: requestId } = error;
  return { ok: false, failure: { kind: "api", status: response.status, code, requestId } };
}
