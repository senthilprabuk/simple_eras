/** Checks and previews WhatsApp template wording, mirroring the API's validation. */

const PLACEHOLDER = /\{([^{}]*)\}/g;
export const TEMPLATE_MAX_LENGTH = 1024;

export function placeholdersIn(body: string): string[] {
  return Array.from(body.matchAll(PLACEHOLDER), (m) => m[1]);
}

/** Problems that would make the API refuse this wording, in plain language. */
export function templateProblems(body: string, allowed: string[]): string[] {
  const problems: string[] = [];
  if (!body.trim()) problems.push("The message is empty.");
  if (body.length > TEMPLATE_MAX_LENGTH) problems.push(`WhatsApp allows at most ${TEMPLATE_MAX_LENGTH} characters.`);
  if ((body.match(/\{/g) ?? []).length !== (body.match(/\}/g) ?? []).length) {
    problems.push("A { or } is missing its partner.");
  }
  const unknown = [...new Set(placeholdersIn(body).filter((p) => !allowed.includes(p)))];
  if (unknown.length) problems.push(`Unknown placeholder: ${unknown.map((p) => `{${p}}`).join(", ")}.`);
  return problems;
}

/** The message as a patient would read it, with sample values filled in. */
export function renderTemplate(body: string, values: Record<string, string>): string {
  return body.replace(PLACEHOLDER, (whole, name: string) => values[name] ?? whole);
}
