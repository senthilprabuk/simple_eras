import type { EpisodeSummary } from "@/lib/api";
import { RELATIONSHIP_LABELS, formatAddress } from "@/lib/format";

/** Emergency contacts, second channels and the home address: what a nurse needs when the patient does not answer. */
export default function WhoToCall({ summary }: { summary: EpisodeSummary }) {
  const contacts = summary.emergency_contacts;
  const sharing = summary.consents.find((c) => c.code === "contact_sharing");

  return (
    <div className="flex flex-col gap-space-sm">
      {contacts.length === 0 ? (
        <p className="font-body-md text-on-surface-variant">No emergency contact recorded.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {contacts.map((c, i) => (
            <li key={c.phone_e164} className="flex items-center justify-between gap-x-space-sm gap-y-0.5 flex-wrap">
              <span>
                <span className="font-label-md text-on-surface">{c.name}</span>{" "}
                <span className="font-body-sm text-on-surface-variant">
                  {RELATIONSHIP_LABELS[c.relationship] ?? c.relationship}
                  {i === 0 && contacts.length > 1 ? " · call first" : ""}
                </span>
              </span>
              <a href={`tel:${c.phone_e164}`} className="inline-flex items-center gap-1 font-label-md text-primary hover:underline">
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">call</span>
                {c.phone_e164}
              </a>
            </li>
          ))}
        </ul>
      )}

      {sharing && !sharing.granted && (
        <p className="font-body-sm text-on-surface-variant flex items-start gap-1.5">
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">info</span>
          The patient has not agreed to the team discussing their recovery with these contacts.
        </p>
      )}

      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-space-md gap-y-1 font-body-md border-t border-outline-variant/20 pt-space-sm">
        <dt className="text-on-surface-variant">Home</dt>
        <dd className="text-on-surface">{summary.address ? formatAddress(summary.address) : "Not recorded"}</dd>
        {summary.alt_phone_e164 && (
          <>
            <dt className="text-on-surface-variant">SMS</dt>
            <dd>
              <a href={`sms:${summary.alt_phone_e164}`} className="text-primary hover:underline">{summary.alt_phone_e164}</a>
            </dd>
          </>
        )}
        {summary.email && (
          <>
            <dt className="text-on-surface-variant">Email</dt>
            <dd className="break-all">
              <a href={`mailto:${summary.email}`} className="text-primary hover:underline">{summary.email}</a>
            </dd>
          </>
        )}
      </dl>
    </div>
  );
}
