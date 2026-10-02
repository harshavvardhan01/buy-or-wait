import type { AnalyzeRequest, AnalyzeResponse, SampleSummary, AccuracySummary } from "./types";

/**
 * `base` is empty in dev because Vite proxies /api to the backend. In a
 * deployed build it comes from the environment, so the same bundle works
 * against any API host without a rebuild of the source.
 */
const base = import.meta.env.VITE_API_BASE ?? "";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export const listSamples = () => json<SampleSummary[]>("/api/samples");

export const getSample = (requestId: string) =>
  json<AnalyzeRequest>(`/api/samples/${requestId}`);

export const analyze = (payload: AnalyzeRequest) =>
  json<AnalyzeResponse>("/api/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });


export const getAccuracy = () => json<AccuracySummary>("/api/accuracy");