import type { AnalyzeRequest } from "../api/types";
import { money } from "../lib/format";

type Props = {
  payload: AnalyzeRequest;
  onChange: (next: AnalyzeRequest) => void;
  onReset: () => void;
  currency: string;
  isDirty: boolean;
};

const METHODS = ["full_payment", "partial_payment", "installments"] as const;

function Slider({
  label,
  value,
  display,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  display: string;
  min: number;
  max: number;
  step: number;
  onChange: (next: number) => void;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          {label}
        </span>
        <span className="text-sm font-semibold tabular-nums text-zinc-900">
          {display}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-zinc-200 accent-blue-600"
      />
    </label>
  );
}

export function WhatIfPanel({
  payload,
  onChange,
  onReset,
  currency,
  isDirty,
}: Props) {
  // Read as Number at the edge: the generated type is `string | number` because
  // Pydantic's Decimal accepts both, but every control here is numeric.
  const minimumBalance = Number(payload.profile.minimum_balance_to_keep);
  const balance = Number(payload.profile.current_available_balance);
  const requested = Number(payload.request.requested_amount);
  const accepted = payload.profile.payment_methods_user_will_consider ?? [];

  const patchProfile = (patch: Partial<AnalyzeRequest["profile"]>) =>
    onChange({ ...payload, profile: { ...payload.profile, ...patch } });

  const toggleMethod = (method: string) =>
    patchProfile({
      payment_methods_user_will_consider: accepted.includes(method)
        ? accepted.filter((m) => m !== method)
        : [...accepted, method],
    });

  return (
    <div className="rounded-b-2xl border-t border-zinc-100 bg-zinc-50/70 px-6 py-5">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          What if…
        </h3>
        {isDirty && (
          <button
            onClick={onReset}
            className="rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-xs text-zinc-600 transition hover:border-zinc-400 hover:text-zinc-900"
          >
            Reset to original
          </button>
        )}
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Slider
          label="Minimum balance"
          value={minimumBalance}
          display={money(minimumBalance, currency)}
          min={0}
          max={Math.round(balance * 1.2)}
          step={Math.max(1, Math.round(balance / 200))}
          onChange={(next) => patchProfile({ minimum_balance_to_keep: next })}
        />

        <Slider
          label="Requested amount"
          value={requested}
          display={money(requested, currency)}
          min={Math.round(requested * 0.1)}
          max={Math.round(requested * 2)}
          step={Math.max(1, Math.round(requested / 200))}
          onChange={(next) =>
            onChange({
              ...payload,
              request: { ...payload.request, requested_amount: next },
            })
          }
        />

        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            Methods allowed
          </p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {METHODS.map((method) => {
              const active = accepted.includes(method);
              return (
                <button
                  key={method}
                  onClick={() => toggleMethod(method)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition ${
                    active
                      ? "border-blue-600 bg-blue-600 text-white"
                      : "border-zinc-300 bg-white text-zinc-500 hover:border-zinc-400"
                  }`}
                >
                  {method.replace(/_/g, " ")}
                </button>
              );
            })}
          </div>
        </div>

        <label className="block">
          <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            Max installment months
          </span>
          <input
            type="number"
            min={0}
            max={36}
            value={payload.profile.max_installment_months ?? 0}
            onChange={(e) =>
              patchProfile({ max_installment_months: Number(e.target.value) })
            }
            className="mt-2.5 w-full rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-sm tabular-nums outline-none focus:border-blue-500"
          />
        </label>
      </div>
    </div>
  );
}