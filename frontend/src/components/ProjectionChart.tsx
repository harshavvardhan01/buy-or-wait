import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DecisionOut, ProjectionOut } from "../api/types";
import { compactMoney, money, shortDate } from "../lib/format";

type Props = {
  projection: ProjectionOut;
  decision: DecisionOut;
  currency: string;
};

export function ProjectionChart({ projection, decision, currency }: Props) {
  // A Set because the chart checks membership per point; at 91 points a scan
  // would be fine, but the Set states the intent.
  const paymentDates = new Set(decision.payment_plan.map((p) => p.date));
  const data = projection.points.map((point) => ({
    date: point.date,
    balance: point.balance,
    isPayment: paymentDates.has(point.date),
  }));

  const breached = projection.trough_balance < projection.minimum_balance;
  const accent = breached ? "#dc2626" : "#2563eb";

  // Clamping the domain to the data keeps the gap between curve and floor
  // legible; anchoring at zero flattens it for high-balance users.
  const values = data.map((d) => d.balance);
  const span = Math.max(...values) - Math.min(...values);
  const pad = Math.max(span * 0.15, projection.minimum_balance * 0.05);
  const low = Math.min(Math.min(...values), projection.minimum_balance) - pad;
  const high = Math.max(...values) + pad;

  return (
    <div style={{ width: "100%", height: 380 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 12, right: 24, bottom: 4, left: 12 }}
        >
          <defs>
            <linearGradient id="balanceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity={0.18} />
              <stop offset="100%" stopColor={accent} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="#e4e4e7" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            minTickGap={48}
            tick={{ fontSize: 11, fill: "#71717a" }}
            axisLine={{ stroke: "#e4e4e7" }}
            tickLine={false}
          />
          <YAxis
            domain={[low, high]}
            tickFormatter={(v: number) => compactMoney(v, currency)}
            width={76}
            tick={{ fontSize: 11, fill: "#71717a" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ stroke: "#a1a1aa", strokeDasharray: "3 3" }}
            contentStyle={{
              borderRadius: 10,
              border: "1px solid #e4e4e7",
              fontSize: 12,
              boxShadow: "0 4px 12px rgb(0 0 0 / 0.08)",
            }}
            formatter={(value) =>
              [money(Number(value), currency), "Balance"] as [string, string]
            }
            labelFormatter={(label) =>
              new Date(String(label)).toLocaleDateString("en-IE", {
                dateStyle: "medium",
              })
            }
          />

          <Area
            type="monotone"
            dataKey="balance"
            stroke="none"
            fill="url(#balanceFill)"
          />

          <ReferenceLine
            y={projection.minimum_balance}
            stroke={breached ? "#dc2626" : "#d97706"}
            strokeDasharray="5 5"
            strokeWidth={1.5}
            label={{
              value: `Minimum ${compactMoney(projection.minimum_balance, currency)}`,
              position: "insideTopRight",
              fontSize: 11,
              fill: breached ? "#dc2626" : "#d97706",
            }}
          />

          {decision.payment_plan.map((payment) => (
            <ReferenceLine
              key={payment.date}
              x={payment.date}
              stroke="#10b981"
              strokeWidth={1.5}
              strokeDasharray="3 3"
            />
          ))}

          <Line
            type="monotone"
            dataKey="balance"
            stroke={accent}
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff" }}
          />

          <ReferenceDot
            x={projection.trough_date}
            y={projection.trough_balance}
            r={6}
            fill={accent}
            stroke="#fff"
            strokeWidth={2.5}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}