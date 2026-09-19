/** Pure presentation rules for the triage queue. No I/O, so they are unit tested. */

import type { KpiResponse, ParameterReading, QueueRow, Reason, Tier } from "@/lib/api";

export const TIERS: Tier[] = ["emergency", "critical", "review", "missed"];

/**
 * Age as of `now`, advanced from the server's own age_secs at fetch time rather
 * than from raised_at, so a skewed workstation clock cannot distort it.
 */
export function currentAgeSecs(row: Pick<QueueRow, "age_secs">, fetchedAt: number, now: number): number {
  return row.age_secs + Math.max(0, Math.floor((now - fetchedAt) / 1000));
}

export function formatDuration(secs: number): string {
  if (secs < 60) return "under 1m";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return mins % 60 ? `${hours}h ${mins % 60}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  return hours % 24 ? `${days}d ${hours % 24}h` : `${days}d`;
}

export type Sla =
  | { state: "acknowledged" }
  | { state: "due"; remainingSecs: number }
  | { state: "breached"; overdueSecs: number };

export function slaFor(ageSecs: number, windowSecs: number, acknowledged: boolean): Sla {
  if (acknowledged) return { state: "acknowledged" };
  const remaining = windowSecs - ageSecs;
  return remaining > 0
    ? { state: "due", remainingSecs: remaining }
    : { state: "breached", overdueSecs: -remaining };
}

export function slaLabel(sla: Sla): string {
  switch (sla.state) {
    case "acknowledged":
      return "Acknowledged";
    case "due":
      return `${formatDuration(sla.remainingSecs)} to acknowledge`;
    case "breached":
      return `SLA breached ${formatDuration(sla.overdueSecs)} ago`;
  }
}

export function reasonText(reason: Reason): string {
  return reason.detail || reason.name.replace(/_/g, " ");
}

export function tierCounts(rows: Pick<QueueRow, "tier">[]): Record<Tier, number> {
  const counts: Record<Tier, number> = { emergency: 0, critical: 0, review: 0, missed: 0 };
  for (const row of rows) counts[row.tier] += 1;
  return counts;
}

export function matchesSearch(row: Pick<QueueRow, "patient_name" | "mrn">, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return row.patient_name.toLowerCase().includes(q) || (row.mrn ?? "").toLowerCase().includes(q);
}

/** Active patients with no unresolved alert. */
export function quietCohort(kpis: Pick<KpiResponse, "active_patients" | "patients_with_open_alerts">): number {
  return Math.max(0, kpis.active_patients - kpis.patients_with_open_alerts);
}

export function initials(fullName: string): string {
  const words = fullName.replace(/^(dr|mr|mrs|ms|nurse)\.?\s+/i, "").split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
}

export function formatReading(reading: ParameterReading, value: ParameterReading["current"]): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  const text = value.toFixed(reading.decimals);
  return reading.unit ? `${text} ${reading.unit === "C" ? "°C" : reading.unit}` : text;
}

/** True when a yes/no answer is the worrying one, e.g. "Yes" to calf pain. */
export function isConcerning(reading: ParameterReading): boolean {
  return reading.type === "boolean" && reading.current !== null && reading.current === reading.concerning_when_true;
}
