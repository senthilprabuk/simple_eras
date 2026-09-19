/** Date and number formatting shared by the clinical screens. */

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const SHORT_DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/**
 * A calendar date ("2026-09-19") as written, never shifted by the viewer's
 * timezone: parsing it as a Date would put it at UTC midnight, which is the
 * previous day west of Greenwich.
 */
function calendarDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function formatDate(iso: string): string {
  return DAY.format(calendarDate(iso));
}

export function formatShortDate(iso: string): string {
  return SHORT_DAY.format(calendarDate(iso));
}

/** An instant (with a time) in the viewer's own timezone. */
export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

export function formatPct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(1)}%`;
}

export function formatNumber(value: number): string {
  return value.toLocaleString("en-GB");
}

export const LANGUAGE_NAMES: Record<string, string> = { en: "English", ta: "Tamil", hi: "Hindi" };

export const OUTCOME_LABELS: Record<string, string> = {
  reassured: "Reassured, continuing plan",
  plan_adjusted: "Care plan adjusted",
  same_day_review: "Same-day review arranged",
  emergency: "Escalated to emergency care",
};
