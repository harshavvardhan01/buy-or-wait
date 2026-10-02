import type { DecisionOut } from "../api/types";
import { money } from "../lib/format";

type Tone = {
  label: string;
  card: string;
  chip: string;
  accent: string;
};

const TONES: Record<string, Tone> = {
  affordable_now: {
    label: "Affordable now",
    card: "border-emerald-200 bg-gradient-to-br from-emerald-50 to-white",
    chip: "bg-emerald-600 text-white",
    accent: "text-emerald-700",
  },
  affordable_with_plan: {
    label: "Affordable with a plan",
    card: "border-blue-200 bg-gradient-to-br from-blue-50 to-white",
    chip: "bg-blue-600 text-white",
    accent: "text-blue-700",
  },
  affordable_later: {
    label: "Affordable later",
    card: "border-amber-200 bg-gradient-to-br from-amber-50 to-white",
    chip: "bg-amber-600 text-white",
    accent: "text-amber-700",
  },
  not_affordable: {
    label: "Not affordable",
    card: "border-red-200 bg-gradient-to-br from-red-50 to-white",
    chip: "bg-red-600 text-white",
    accent: "text-red-700",
  },
};

export function VerdictCard({
  decision,
  currency,
}: {
  decision: DecisionOut;
  currency: string;
}) {
  const tone = TONES[decision.affordability_status] ?? {
    label: decision.affordability_status,
    card: "border-zinc-200 bg-white",
    chip: "bg-zinc-800 text-white",
    accent: "text-zinc-700",
  };

  return (
    <section className={`rounded-2xl border p-7 ${tone.card}`}>
      <div className="grid gap-7 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-2xl font-semibold tracking-tight">
              {tone.label}
            </h2>
            <span
              className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-wider ${tone.chip}`}
            >
              {decision.recommended_payment_method.replace(/_/g, " ")}
            </span>
          </div>

          <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-zinc-700">
            {decision.decision_explanation}
          </p>

          <div className="mt-6 flex flex-wrap gap-10">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                Safe to pay today
              </p>
              <p
                className={`mt-1 text-3xl font-semibold tabular-nums ${tone.accent}`}
              >
                {money(decision.amount_safe_to_pay, currency)}
              </p>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                Earliest full payment
              </p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-zinc-800">
                {decision.earliest_date_for_full_payment ?? "—"}
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {decision.payment_plan.length > 0 && (
            <div className="rounded-xl border border-white bg-white/70 p-4 backdrop-blur">
              <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                Recommended schedule
              </p>
              <ol className="mt-2 space-y-1.5">
                {decision.payment_plan.map((payment, index) => (
                  <li
                    key={payment.date}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="flex items-center gap-2 text-zinc-600">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-zinc-200 text-[10px] font-semibold text-zinc-700">
                        {index + 1}
                      </span>
                      {payment.date}
                    </span>
                    <span className="font-semibold tabular-nums">
                      {money(payment.amount, currency)}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {decision.spending_changes_needed.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
              <p className="text-[11px] font-medium uppercase tracking-wider text-amber-800">
                Requires spending changes
              </p>
              <ul className="mt-2 space-y-1">
                {decision.spending_changes_needed.map((change) => (
                  <li key={change} className="font-mono text-xs text-amber-900">
                    {change}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}