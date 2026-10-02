/**
 * Named aliases over the generated schema.
 *
 * Components import from here rather than reaching into `schema.d.ts` directly,
 * so a regenerated schema breaks in one file instead of twenty.
 */
import type { components } from "./schema";

export type AnalyzeRequest = components["schemas"]["AnalyzeRequest-Input"];
export type AnalyzeResponse = components["schemas"]["AnalyzeResponse"];
export type DecisionOut = components["schemas"]["DecisionOut"];
export type ProjectionOut = components["schemas"]["ProjectionOut"];
export type ReasoningOut = components["schemas"]["ReasoningOut"];
export type SeriesOut = components["schemas"]["SeriesOut"];
export type ProfileIn = components["schemas"]["ProfileIn-Input"];
export type AccuracySummary = components["schemas"]["AccuracySummary"];
export type AccuracyRow = components["schemas"]["AccuracyRow"];

export type AffordabilityStatus =
  | "affordable_now"
  | "affordable_with_plan"
  | "affordable_later"
  | "not_affordable";

export type SampleSummary = {
  request_id: string;
  user_id: string;
  request_type: string;
  requested_amount: string;
  request_date: string;
  currency: string;
  expected_status: AffordabilityStatus;
  expected_method: string;
};