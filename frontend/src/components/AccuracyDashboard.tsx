import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAccuracy } from "../api/client";
import type { AccuracyRow } from "../api/types";
import { money } from "../lib/format";

function Metric({
  label,
  value,
  total,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  total?: string;
  hint?: string;
  tone?: "default" | "good" | "warn";
}) {
  const accent =
    tone === "good"
      ? "text-emerald-600"
      : tone === "warn"
        ? "text-amber-600"
        : "text-zinc-900";

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </p>
      <p className={`mt-2 text-3xl font-semibold tabular-nums ${accent}`}>
        {value}
        {total && (
          <span className="text-lg font-normal text-zinc-400"> / {total}</span>
        )}
      </p>
      {hint && <p className="mt-1.5 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

function Row({ row }: { row: AccuracyRow }) {
  // Only failures expand. Twenty-five open accordions is unreadable, and a
  // matching row needs no explanation.
  const failed = !row.status_match;

  return (
    <>
      <tr className={failed ? "bg-red-50/50" : undefined}>
        <td className="px-5 py-3 font-mono text-xs text-zinc-500">
          {row.request_id.replace("request_", "#")}
        </td>
        <td className="py-3 text-xs capitalize text-zinc-500">
          {row.request_type.replace(/_/g, " ")}
        </td>
        <td className="py-3">
          <div className="flex items-center gap-2">
            <span
              className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                row.status_match
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-red-100 text-red-800"
              }`}
            >
              {row.predicted_status.replace(/_/g, " ")}
            </span>
            {!row.status_match && (
              <span className="text-xs text-zinc-400">
                → {row.expected_status.replace(/_/g, " ")}
              </span>
            )}
          </div>
        </td>
        <td className="py-3">
          <span
            className={`text-xs ${
              row.method_match ? "text-zinc-600" : "text-red-700"
            }`}
          >
            {row.predicted_method.replace(/_/g, " ")}
          </span>
        </td>
        <td className="py-3 text-right text-xs tabular-nums">
          <span className="font-medium text-zinc-800">
            {money(row.predicted_amount, row.currency)}
          </span>
          <span className="block text-zinc-400">
            {money(row.expected_amount, row.currency)}
          </span>
        </td>
        <td
          className={`px-5 py-3 text-right text-xs font-medium tabular-nums ${
            row.relative_error < 0.02
              ? "text-emerald-600"
              : row.relative_error < 0.1
                ? "text-amber-600"
                : "text-red-600"
          }`}
        >
          {(row.relative_error * 100).toFixed(1)}%
        </td>
      </tr>

      {failed && row.rejections.length > 0 && (
        <tr className="bg-red-50/50">
          <td colSpan={6} className="px-5 pb-3">
            <ul className="space-y-1 border-l-2 border-red-200 pl-3">
              {row.rejections.map((reason) => (
                <li
                  key={reason}
                  className="font-mono text-[11px] leading-relaxed text-zinc-600"
                >
                  {reason}
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}

export function AccuracyDashboard() {
  // `failuresOnly` defaults to false so the first impression is the full set,
  // not a wall of red. The toggle is for working, not for presenting.
  const [failuresOnly, setFailuresOnly] = useState(false);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["accuracy"],
    queryFn: getAccuracy,
  });

  if (isLoading)
    return (
      <div className="space-y-6">
        <div className="h-36 animate-pulse rounded-xl bg-white" />
        <div className="h-96 animate-pulse rounded-xl bg-white" />
      </div>
    );

  if (isError)
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        {(error as Error).message}
      </p>
    );

  if (!data) return null;

  const rows = failuresOnly
    ? data.rows.filter((row) => !row.status_match)
    : data.rows;
  const failureCount = data.total - data.status_correct;

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-zinc-200 bg-white p-7">
        <h2 className="text-xl font-semibold tracking-tight">
          Measured accuracy
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-zinc-600">
          Scored live against the {data.total} labelled cases shipped with the
          dataset — the engine runs on every page load rather than reading a
          cached result. It is deterministic, so these numbers reproduce exactly.
          Each failure lists the reason every candidate plan was rejected.
        </p>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Affordability status"
            value={String(data.status_correct)}
            total={String(data.total)}
            hint="exact enum match"
            tone="good"
          />
          <Metric
            label="Payment method"
            value={String(data.method_correct)}
            total={String(data.total)}
            hint="exact enum match"
            tone="good"
          />
          <Metric
            label="Amount within 10%"
            value={String(data.amount_within_10pct)}
            total={String(data.total)}
            hint={`${data.amount_within_2pct} within 2%`}
            tone="warn"
          />
          <Metric
            label="Median error"
            value={`${(data.median_relative_error * 100).toFixed(1)}%`}
            hint="on amount_safe_to_pay"
            tone="warn"
          />
        </div>
      </section>

      <section className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
        <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-4">
          <h3 className="text-sm font-semibold">
            Case-by-case results
            {failuresOnly && (
              <span className="ml-2 font-normal text-zinc-500">
                showing {failureCount} failures
              </span>
            )}
          </h3>
          <button
            onClick={() => setFailuresOnly((previous) => !previous)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              failuresOnly
                ? "border-red-300 bg-red-50 text-red-700"
                : "border-zinc-300 bg-white text-zinc-600 hover:border-zinc-400"
            }`}
          >
            {failuresOnly ? "Show all 25" : `Failures only (${failureCount})`}
          </button>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-100 text-left text-[11px] uppercase tracking-wider text-zinc-400">
              <th className="px-5 py-3 font-medium">Case</th>
              <th className="py-3 font-medium">Type</th>
              <th className="py-3 font-medium">Status · predicted → expected</th>
              <th className="py-3 font-medium">Method</th>
              <th className="py-3 text-right font-medium">
                Safe to pay · expected
              </th>
              <th className="px-5 py-3 text-right font-medium">Error</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-50">
            {rows.map((row) => (
              <Row key={row.request_id} row={row} />
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}