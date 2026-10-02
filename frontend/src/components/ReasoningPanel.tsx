import type { ReasoningOut } from "../api/types";
import { money } from "../lib/format";

export function ReasoningPanel({
  reasoning,
  currency,
}: {
  reasoning: ReasoningOut;
  currency: string;
}) {
  // Sorted by monthly impact so the biggest drivers of the forecast lead; that
  // ordering is the reason this table is worth showing at all.
  const series = [...reasoning.detected_series].sort(
    (a, b) => Number(b.monthly_equivalent) - Number(a.monthly_equivalent)
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
      <section className="rounded-2xl border border-zinc-200 bg-white">
        <div className="flex items-center justify-between border-b border-zinc-100 px-6 py-4">
          <h2 className="text-sm font-semibold">Detected recurring flows</h2>
          <span
            className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
              reasoning.income_projected
                ? "bg-emerald-50 text-emerald-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            Income {reasoning.income_projected ? "projected" : "stopped"}
          </span>
        </div>

        <table className="w-full max-w-2xl text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-zinc-400">
              <th className="px-6 py-2 font-medium">Category</th>
              <th className="py-2 font-medium">Cycle</th>
              <th className="px-6 py-2 text-right font-medium">Per month</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-50">
            {series.map((item) => (
              <tr key={`${item.category}-${item.direction}`}>
                <td className="px-6 py-2.5">
                  <span className="capitalize">
                    {item.category.replace(/_/g, " ")}
                  </span>
                  {item.flexibility !== "fixed" && (
                    <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700">
                      {item.flexibility.replace(/_/g, " ")}
                    </span>
                  )}
                </td>
                <td className="py-2.5 text-xs text-zinc-400">
                  {item.period_days}d
                </td>
                <td
                  className={`px-6 py-2.5 text-right font-medium tabular-nums ${
                    item.direction === "credit"
                      ? "text-emerald-600"
                      : "text-zinc-700"
                  }`}
                >
                  {item.direction === "credit" ? "+" : "−"}
                  {money(item.monthly_equivalent, currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white">
        <div className="border-b border-zinc-100 px-6 py-4">
          <h2 className="text-sm font-semibold">Options ruled out</h2>
          <p className="mt-0.5 text-xs text-zinc-500">
            Every plan the engine considered and rejected, with the reason
          </p>
        </div>
        <ul className="divide-y divide-zinc-50">
          {reasoning.rejected_plans.map((reason) => (
            <li
              key={reason}
              className="px-6 py-2.5 font-mono text-[11px] leading-relaxed text-zinc-600"
            >
              {reason}
            </li>
          ))}
          {reasoning.rejected_plans.length === 0 && (
            <li className="px-6 py-4 text-xs text-zinc-400">
              Nothing rejected — the first candidate was safe.
            </li>
          )}
        </ul>
      </section>
    </div>
  );
}