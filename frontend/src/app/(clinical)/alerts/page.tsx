"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import { TierBadge } from "@/components/RiskQueueTable";
import { ErrorBanner, Loading, PageBody, PageHeader, Segmented, StatusPill, secondaryButtonClass } from "@/components/ui";
import { acknowledgeAlert, type Tier } from "@/lib/api";
import { fetchAlertHistory, sideLabel, type AlertHistoryItem, type AlertStatus } from "@/lib/clinicalApi";
import { OUTCOME_LABELS, formatDateTime, formatPhone } from "@/lib/format";
import { DOMAIN_META, formatDuration, groupReasons, reasonText } from "@/lib/triage";
import { useApiData } from "@/lib/useApiData";

const PAGE = 100;

/** Filters from a link such as a patient's "Alert history"; read once, client-only. */
function initialPatientFilter(): { episodeId: string | null; name: string | null } {
  if (typeof window === "undefined") return { episodeId: null, name: null };
  const params = new URLSearchParams(window.location.search);
  return { episodeId: params.get("episode"), name: params.get("patient") };
}

/**
 * Acknowledging from the list rather than the dashboard.
 *
 * The escalation sweep pages every admin at the hospital once an open critical
 * alert passes its SLA, so the cost of making a clinician navigate elsewhere to
 * stop that timer is measured in pages to colleagues. `reload` rather than local
 * state after success, so the row shows the server's own acknowledged_at.
 */
function AcknowledgeButton({ alert, onDone }: { alert: AlertHistoryItem; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const acknowledge = async () => {
    setBusy(true);
    setError(null);
    try {
      await acknowledgeAlert(alert.alert_id);
      onDone();
    } catch (err) {
      // 409 means someone else got there first; reloading shows their name.
      setError(err instanceof Error ? err.message : "Could not acknowledge");
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className={secondaryButtonClass}
        disabled={busy}
        onClick={acknowledge}
        aria-label={`Acknowledge the ${alert.tier} alert for ${alert.patient_name}`}
      >
        {busy ? "Acknowledging…" : "Acknowledge"}
      </button>
      {error && <p className="font-body-sm text-error mt-1">{error}</p>}
    </>
  );
}

function Acknowledgement({ alert, onDone }: { alert: AlertHistoryItem; onDone: () => void }) {
  if (alert.ack_secs === null) {
    return alert.status === "open" ? (
      <AcknowledgeButton alert={alert} onDone={onDone} />
    ) : (
      <span className="font-body-sm text-outline italic">Not acknowledged</span>
    );
  }
  const late = alert.ack_secs > alert.ack_window_secs;
  return (
    <>
      <div className="font-body-md text-on-surface">{alert.acknowledged_by_name ?? "A former clinician"}</div>
      <div className={`font-body-sm ${late ? "text-error font-semibold" : "text-on-surface-variant"}`}>
        after {formatDuration(alert.ack_secs)}
        {late && ` · over the ${formatDuration(alert.ack_window_secs)} SLA`}
      </div>
    </>
  );
}

/**
 * Reasons under the complication they point at, most time-critical domain
 * first. The individual findings stay visible underneath: the grouping is there
 * to say what the picture is, not to replace the reading behind it.
 */
function Reasons({ alert }: { alert: AlertHistoryItem }) {
  return (
    <div className="flex flex-col gap-2 max-w-xs">
      {groupReasons(alert.reasons).map(({ domain, reasons }) => (
        <div key={domain}>
          <div className="inline-flex items-center gap-1 font-label-sm text-on-surface-variant uppercase tracking-wider">
            <span className="material-symbols-outlined text-[14px]" aria-hidden="true">
              {DOMAIN_META[domain].icon}
            </span>
            {DOMAIN_META[domain].label}
          </div>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {reasons.map((r, i) => (
              <span
                key={i}
                className="px-2 py-0.5 rounded bg-surface-bright border border-outline-variant/40 font-body-sm text-on-surface"
              >
                {reasonText(r)}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AlertsPage() {
  const [patient, setPatient] = useState(initialPatientFilter);
  const [status, setStatus] = useState<AlertStatus | "all">("all");
  const [tier, setTier] = useState<Tier | "all">("all");
  const [days, setDays] = useState(patient.episodeId ? 365 : 30);
  const [offset, setOffset] = useState(0);

  const load = useCallback(
    () => fetchAlertHistory({ status, tier, days, episodeId: patient.episodeId, limit: PAGE, offset }),
    [status, tier, days, patient.episodeId, offset],
  );
  const { data, error, loading, reload } = useApiData(load);

  const filter = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setOffset(0);
  };

  return (
    <>
      <PageHeader title="Alerts" />
      <PageBody>
        <div className="flex flex-wrap items-center gap-space-sm">
          <Segmented
            label="Period"
            value={days}
            onChange={filter(setDays)}
            options={[
              { value: 7, label: "7 days" },
              { value: 30, label: "30 days" },
              { value: 90, label: "90 days" },
              { value: 365, label: "1 year" },
            ]}
          />
          <Segmented
            label="Status"
            value={status}
            onChange={filter(setStatus)}
            options={[
              { value: "all", label: "All" },
              { value: "open", label: "Open" },
              { value: "acknowledged", label: "Acknowledged" },
              { value: "resolved", label: "Resolved" },
              { value: "expired", label: "Expired" },
            ]}
          />
          <Segmented
            label="Tier"
            value={tier}
            onChange={filter(setTier)}
            options={[
              { value: "all", label: "All tiers" },
              { value: "emergency", label: "Emergency" },
              { value: "critical", label: "Critical" },
              { value: "review", label: "Review" },
              { value: "missed", label: "Missed" },
            ]}
          />
          {patient.episodeId && (
            <span className="inline-flex items-center gap-1 pl-2.5 pr-1 py-0.5 rounded-full bg-primary/10 text-primary font-label-md">
              {patient.name ?? "One patient"}
              <button
                type="button"
                aria-label="Show alerts for all patients"
                onClick={() => {
                  setPatient({ episodeId: null, name: null });
                  setOffset(0);
                  window.history.replaceState(null, "", "/alerts");
                }}
                className="p-0.5 rounded-full hover:bg-primary/15 cursor-pointer"
              >
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">close</span>
              </button>
            </span>
          )}
        </div>

        {error && <ErrorBanner message={error} onRetry={reload} />}
        {!data && !error && <Loading label="Loading alerts…" />}

        {data && (
          <section
            aria-label="Alert history"
            className={`bg-surface-container-lowest rounded-xl border border-outline-variant/30 overflow-hidden shadow-sm transition-opacity ${
              loading ? "opacity-60" : ""
            }`}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left min-w-[1080px]">
                <thead>
                  <tr className="bg-surface-bright/70 border-b border-outline-variant/30 text-on-surface-variant font-label-sm uppercase tracking-wider">
                    <th scope="col" className="py-3 px-space-md">Raised</th>
                    <th scope="col" className="py-3 px-space-md">Patient</th>
                    <th scope="col" className="py-3 px-space-md">Tier</th>
                    <th scope="col" className="py-3 px-space-md">Reasons</th>
                    <th scope="col" className="py-3 px-space-md">Acknowledged</th>
                    <th scope="col" className="py-3 px-space-md">Resolution</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {data.items.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-space-xl text-center font-body-md text-on-surface-variant">
                        No alerts match these filters.
                      </td>
                    </tr>
                  )}
                  {data.items.map((a) => (
                    <tr key={a.alert_id} className="align-top">
                      <td className="py-3 px-space-md">
                        <div className="font-body-md text-on-surface whitespace-nowrap">{formatDateTime(a.raised_at)}</div>
                        <div className="font-body-sm text-on-surface-variant">POD {a.day_after_discharge}</div>
                        {a.escalated_at && (
                          <div className="inline-flex items-center gap-1 mt-1 font-label-sm text-error">
                            <span className="material-symbols-outlined text-[14px]" aria-hidden="true">campaign</span>
                            Escalated
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-space-md">
                        <Link href={`/patients/${a.episode_id}`} className="font-title-sm text-on-surface hover:text-primary hover:underline">
                          {a.patient_name}
                        </Link>
                        <div className="font-body-sm text-on-surface-variant">
                          MRN {a.mrn ?? "not recorded"}
                          {" · "}
                          {a.operative_side ? (
                            <span className="font-semibold text-on-surface">
                              {sideLabel(a.operative_side, a.procedure_code)}
                            </span>
                          ) : (
                            <span className="italic">side not recorded</span>
                          )}
                        </div>
                        {a.phone_e164 && (
                          <a
                            href={`tel:${a.phone_e164}`}
                            className="inline-flex items-center gap-1 mt-1 font-body-sm text-primary hover:underline"
                            aria-label={`Call ${a.patient_name} on ${formatPhone(a.phone_e164)}`}
                          >
                            <span className="material-symbols-outlined text-[14px]" aria-hidden="true">call</span>
                            {formatPhone(a.phone_e164)}
                          </a>
                        )}
                      </td>
                      <td className="py-3 px-space-md">
                        <div className="flex flex-col items-start gap-1">
                          <TierBadge tier={a.tier} />
                          <StatusPill status={a.status} />
                        </div>
                      </td>
                      <td className="py-3 px-space-md">
                        <Reasons alert={a} />
                      </td>
                      <td className="py-3 px-space-md">
                        <Acknowledgement alert={a} onDone={reload} />
                      </td>
                      <td className="py-3 px-space-md max-w-xs">
                        {a.outcome ? (
                          <>
                            <div className="font-body-md text-on-surface">{OUTCOME_LABELS[a.outcome]}</div>
                            <div className="font-body-sm text-on-surface-variant">
                              {a.resolved_by_name ?? "A former clinician"}
                              {a.resolved_at && `, ${formatDateTime(a.resolved_at)}`}
                            </div>
                            {a.outcome_note && <p className="font-body-sm text-on-surface mt-1">&ldquo;{a.outcome_note}&rdquo;</p>}
                          </>
                        ) : a.status === "expired" ? (
                          // A missed check-in closes itself when the patient checks in again.
                          <>
                            <div className="font-body-md text-on-surface">Closed automatically</div>
                            {a.resolved_at && (
                              <div className="font-body-sm text-on-surface-variant">{formatDateTime(a.resolved_at)}</div>
                            )}
                            {a.outcome_note && <p className="font-body-sm text-on-surface mt-1">{a.outcome_note}</p>}
                          </>
                        ) : (
                          <span className="font-body-sm text-outline italic">Not resolved</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {data && data.total > PAGE && (
          <div className="flex items-center justify-between">
            <span className="font-body-sm text-on-surface-variant">
              {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
            </span>
            <div className="flex gap-space-sm">
              <button type="button" className={secondaryButtonClass} disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>
                Newer
              </button>
              <button
                type="button"
                className={secondaryButtonClass}
                disabled={offset + PAGE >= data.total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Older
              </button>
            </div>
          </div>
        )}
      </PageBody>
    </>
  );
}
