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

/** FHIR administrative gender. */
export const GENDER_LABELS: Record<string, string> = {
  female: "Female",
  male: "Male",
  other: "Other",
  unknown: "Unknown",
};

export const RELATIONSHIP_LABELS: Record<string, string> = {
  spouse: "Spouse",
  son: "Son",
  daughter: "Daughter",
  sibling: "Brother or sister",
  parent: "Parent",
  other_family: "Other family member",
  friend: "Friend or neighbour",
  caregiver: "Paid caregiver",
};

export const PRIVACY_LAW_NAMES: Record<string, string> = {
  "DPDP-2023": "the Digital Personal Data Protection Act, 2023",
  HIPAA: "HIPAA",
};

export const CONSENT_LABELS: Record<string, string> = {
  remote_monitoring: "Remote monitoring and WhatsApp messages",
  data_processing: "Cloud processing of health data",
  contact_sharing: "Discussing recovery with emergency contacts",
};

/** "Female, 68 years"; parts that were not recorded are left out. */
export function formatSexAge(gender: string, ageYears: number | null): string {
  const sex = gender === "unknown" ? null : (GENDER_LABELS[gender] ?? gender);
  return [sex, ageYears !== null ? `${ageYears} years` : null].filter(Boolean).join(", ");
}

/** "08:00:00", "10:00:00" -> "08:00–10:00". */
export function formatTimeWindow(start: string, end: string): string {
  return `${start.slice(0, 5)}–${end.slice(0, 5)}`;
}

/** One line for an ambulance crew: parts left blank are skipped, and a district that repeats the city is not said twice. */
export function formatAddress(address: {
  line: string | null;
  city: string | null;
  district: string | null;
  state: string | null;
  postal_code: string | null;
}): string {
  const district = address.district && address.district !== address.city ? address.district : null;
  const place = [address.line, address.city, district, address.state].filter(Boolean).join(", ");
  return [place, address.postal_code].filter(Boolean).join(" ");
}

export const OUTCOME_LABELS: Record<string, string> = {
  reassured: "Reassured, continuing plan",
  plan_adjusted: "Care plan adjusted",
  same_day_review: "Same-day review arranged",
  emergency: "Escalated to emergency care",
};
