import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analyze, getSample, listSamples } from "./api/client";
import { AccuracyDashboard } from "./components/AccuracyDashboard";
import { ProjectionChart } from "./components/ProjectionChart";
import { ReasoningPanel } from "./components/ReasoningPanel";
import { VerdictCard } from "./components/VerdictCard";
import { WhatIfPanel } from "./components/WhatIfPanel";
import { useDebounced } from "./hooks/useDebounced";
import type { AnalyzeRequest } from "./api/types";

const TABS = [
  { id: "explore", label: "Explore" },
  { id: "accuracy", label: "Accuracy" },
] as const;

type View = (typeof TABS)[number]["id"];

export default function App() {
  const [selectedId, setSelectedId] = useState("request_12");
  const [view, setView] = useState<View>("explore");

  // Two pieces of state for one payload: `payload` updates on every slider tick
  // so the controls stay responsive, while `debounced` drives the query key so
  // the network only fires once the user pauses.
  const [payload, setPayload] = useState<AnalyzeRequest | null>(null);
  const debounced = useDebounced(payload, 250);

  const samples = useQuery({ queryKey: ["samples"], queryFn: listSamples });
  const sample = useQuery({
    queryKey: ["sample", selectedId],
    queryFn: () => getSample(selectedId),
  });

  useEffect(() => {
    if (sample.data) setPayload(sample.data);
  }, [sample.data]);

  const result = useQuery({
    queryKey: ["analyze", debounced],
    queryFn: () => analyze(debounced!),
    enabled: debounced !== null,
  });

  const currency = payload?.profile.home_currency ?? "EUR";
  // `isDirty` compares against the pristine sample so the Reset affordance only
  // appears once something has actually been changed.
  const isDirty =
    payload !== null &&
    sample.data !== undefined &&
    JSON.stringify(payload) !== JSON.stringify(sample.data);

  return (
    <div className="min-h-screen bg-zinc-100 text-zinc-900 antialiased">
      <header className="bg-zinc-900 text-white">
        <div className="mx-auto max-w-[1400px] px-8 pt-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">
                Buy or Wait?
              </h1>
              <p className="mt-1 text-sm text-zinc-400">
                Affordability decisions derived from a deterministic 90-day
                cash-flow projection
              </p>
            </div>

            {view === "explore" && (
              <label className="flex items-center gap-3 text-sm">
                <span className="text-zinc-400">Scenario</span>
                <select
                  value={selectedId}
                  onChange={(e) => setSelectedId(e.target.value)}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
                >
                  {samples.data?.map((s) => (
                    <option key={s.request_id} value={s.request_id}>
                      {s.request_id} · {s.request_type.replace(/_/g, " ")} ·{" "}
                      {s.currency} {Number(s.requested_amount).toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <nav className="mt-6 flex gap-6">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setView(tab.id)}
                className={`relative pb-3 text-sm font-medium transition ${
                  view === tab.id
                    ? "text-white"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {tab.label}
                {view === tab.id && (
                  <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-blue-500" />
                )}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {view === "accuracy" ? (
        <main className="mx-auto max-w-[1400px] px-8 py-8">
          <AccuracyDashboard />
        </main>
      ) : (
        <main className="mx-auto max-w-[1400px] space-y-6 px-8 py-8">
          {result.isError && (
            <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              {(result.error as Error).message}
            </p>
          )}

          {!result.data && !result.isError && (
            <div className="h-40 animate-pulse rounded-2xl bg-white" />
          )}

          {result.data && payload && (
            <>
              <VerdictCard decision={result.data.decision} currency={currency} />

              <section className="rounded-2xl border border-zinc-200 bg-white">
                <div className="flex items-baseline justify-between border-b border-zinc-100 px-6 py-4">
                  <h2 className="text-sm font-semibold text-zinc-900">
                    90-day balance projection
                  </h2>
                  <p className="text-xs text-zinc-500">
                    Lowest point{" "}
                    <span className="font-medium text-zinc-700">
                      {result.data.projection.trough_date}
                    </span>
                  </p>
                </div>

                <div className="px-3 py-5">
                  <ProjectionChart
                    projection={result.data.projection}
                    decision={result.data.decision}
                    currency={currency}
                  />
                </div>

                <WhatIfPanel
                  payload={payload}
                  onChange={setPayload}
                  onReset={() => sample.data && setPayload(sample.data)}
                  currency={currency}
                  isDirty={isDirty}
                />
              </section>

              <ReasoningPanel
                reasoning={result.data.reasoning}
                currency={currency}
              />
            </>
          )}
        </main>
      )}
    </div>
  );
}