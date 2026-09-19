"use client";

import React, { useEffect, useRef, useState } from "react";
import { ApiError, EpisodeSummary, Outcome, QueueRow, fetchEpisodeSummary, resolveAlert } from "@/lib/api";
import { formatReading, isConcerning, reasonText } from "@/lib/triage";
import { TierBadge } from "@/components/RiskQueueTable";

interface PatientDetailDrawerProps {
  row: QueueRow;
  onClose: () => void;
  onResolved: () => void;
}

const OUTCOMES: { id: Outcome; label: string }[] = [
  { id: "reassured", label: "Reassured, continuing plan" },
  { id: "plan_adjusted", label: "Care plan adjusted" },
  { id: "same_day_review", label: "Same-day review arranged" },
  { id: "emergency", label: "Escalated to emergency care" },
];

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function PatientDetailDrawer({ row, onClose, onResolved }: PatientDetailDrawerProps) {
  const [summary, setSummary] = useState<EpisodeSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEpisodeSummary(row.episode_id)
      .then((s) => !cancelled && setSummary(s))
      .catch((err) => !cancelled && setSummaryError(err instanceof ApiError ? err.message : "Could not load the patient record."));
    return () => {
      cancelled = true;
    };
  }, [row.episode_id]);

  // Modal behaviour: focus moves in, Escape closes, focus returns on close.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab" || !panelRef.current) return;
    const nodes = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const handleResolve = async () => {
    if (!outcome) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await resolveAlert(row.alert_id, outcome, note);
      onResolved();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Could not record the outcome.");
      setSubmitting(false);
    }
  };

  const latest = summary?.latest_check_in ?? null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/30"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onKeyDown={trapTab}
        className="w-full max-w-xl bg-surface-container-lowest h-full shadow-2xl border-l border-outline-variant/40 flex flex-col"
      >
        <header className="p-space-lg border-b border-outline-variant/30 flex items-start justify-between gap-space-md">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 id="drawer-title" className="font-headline-md text-on-surface">
                {row.patient_name}
              </h2>
              {summary && (
                <span className="font-label-sm px-2 py-0.5 rounded bg-surface-container-low text-primary font-semibold">
                  POD {summary.post_op_day}
                </span>
              )}
            </div>
            <p className="font-body-sm text-on-surface-variant">
              MRN {row.mrn ?? "not recorded"} · {summary?.procedure_name ?? row.procedure_code} · {row.hospital_name}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close patient details"
            className="p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-bright hover:text-on-surface cursor-pointer"
          >
            <span className="material-symbols-outlined text-[22px]" aria-hidden="true">close</span>
          </button>
        </header>

        <div className="p-space-lg overflow-y-auto flex-1 flex flex-col gap-space-lg">
          <section className="bg-surface-bright/50 border border-outline-variant/30 rounded-xl p-space-md flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <TierBadge tier={row.tier} />
              <span className="font-body-sm text-on-surface-variant">Raised on POD {row.day_after_discharge}</span>
            </div>
            <ul className="flex flex-col gap-1.5">
              {row.reasons.map((reason, i) => (
                <li key={i} className="font-body-md text-on-surface bg-surface-container-lowest px-3 py-2 rounded-lg border border-outline-variant/30">
                  {reasonText(reason)}
                </li>
              ))}
            </ul>
            <p className="font-body-sm text-on-surface-variant">
              {row.acknowledged
                ? `Acknowledged by ${row.acknowledged_by_name ?? "a former clinician"}.`
                : "Not yet acknowledged."}
            </p>
          </section>

          {summaryError && (
            <p role="alert" className="font-body-md text-on-error-container bg-error-container rounded-lg px-3 py-2">
              {summaryError}
            </p>
          )}
          {!summary && !summaryError && (
            <p className="font-body-md text-on-surface-variant">Loading patient record…</p>
          )}

          {summary && (
            <>
              <a
                href={`tel:${summary.phone_e164}`}
                className="self-start inline-flex items-center gap-1.5 px-3 py-1.5 border border-primary text-primary font-label-md rounded hover:bg-surface-container-low"
              >
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">call</span>
                Call patient · {summary.phone_e164}
              </a>

              <section className="border border-outline-variant/30 rounded-xl overflow-hidden">
                <div className="px-space-md py-space-sm bg-surface-bright/50 border-b border-outline-variant/30">
                  <h3 className="font-title-sm text-on-surface">Discharge baseline vs latest check-in</h3>
                  <p className="font-body-sm text-on-surface-variant">
                    {latest
                      ? `Latest: POD ${latest.day_after_discharge}, ${new Date(latest.submitted_at).toLocaleString()} (${latest.source})`
                      : "No check-in has been received yet."}
                  </p>
                </div>
                {summary.readings.length === 0 ? (
                  <p className="px-space-md py-space-sm font-body-md text-on-surface-variant">No readings recorded.</p>
                ) : (
                  <table className="w-full text-left">
                    <thead>
                      <tr className="font-label-sm uppercase tracking-wider text-on-surface-variant border-b border-outline-variant/30">
                        <th scope="col" className="px-space-md py-2">Measure</th>
                        <th scope="col" className="px-space-md py-2">Discharge</th>
                        <th scope="col" className="px-space-md py-2">Latest</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-outline-variant/20">
                      {summary.readings.map((r) => (
                        <tr key={r.code} className="font-body-md">
                          <th scope="row" className="px-space-md py-2 font-normal text-on-surface-variant">{r.name}</th>
                          <td className="px-space-md py-2 text-on-surface">{formatReading(r, r.baseline)}</td>
                          <td className={`px-space-md py-2 ${isConcerning(r) ? "text-error font-semibold" : "text-on-surface"}`}>
                            {formatReading(r, r.current)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <p className="px-space-md py-2 font-body-sm text-on-surface-variant border-t border-outline-variant/20">
                  {latest?.photo_submitted
                    ? "A wound photo was submitted, but image storage is not connected yet, so it cannot be shown here."
                    : "No wound photo with the latest check-in."}{" "}
                  Ruleset {summary.ruleset_version}.
                </p>
              </section>
            </>
          )}

          <section className="border border-outline-variant/40 rounded-xl p-space-md">
            <h3 className="font-label-sm text-primary uppercase tracking-wider font-semibold mb-1">
              Record outcome and resolve
            </h3>
            <p className="font-body-sm text-on-surface-variant mb-3">
              Every alert is closed with a recorded clinical outcome.
              {!row.acknowledged && " Resolving also acknowledges it in your name."}
            </p>

            <fieldset className="grid grid-cols-2 gap-2 mb-3">
              <legend className="sr-only">Outcome</legend>
              {OUTCOMES.map((item) => (
                <label
                  key={item.id}
                  className={`p-2.5 rounded-lg border font-label-md cursor-pointer transition-colors ${
                    outcome === item.id
                      ? "border-primary bg-surface-container-low text-primary font-semibold"
                      : "border-outline-variant/40 text-on-surface-variant hover:border-outline-variant"
                  }`}
                >
                  <input
                    type="radio"
                    name="outcome"
                    value={item.id}
                    checked={outcome === item.id}
                    onChange={() => setOutcome(item.id)}
                    className="sr-only"
                  />
                  {item.label}
                </label>
              ))}
            </fieldset>

            <label className="flex flex-col gap-1">
              <span className="font-label-md text-on-surface">Clinical note (optional)</span>
              <textarea
                rows={3}
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full p-2.5 bg-surface-bright border border-outline-variant/40 rounded-lg font-body-sm text-on-surface focus:outline-none focus:border-primary"
              />
            </label>

            {submitError && (
              <p role="alert" className="mt-2 font-body-sm text-on-error-container bg-error-container rounded-lg px-3 py-2">
                {submitError}
              </p>
            )}
          </section>
        </div>

        <footer className="p-space-lg border-t border-outline-variant/30 flex items-center justify-end gap-space-sm">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg font-label-md text-on-surface-variant hover:bg-surface-bright cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!outcome || submitting}
            onClick={handleResolve}
            className="px-5 py-2 rounded-lg bg-primary text-on-primary font-label-md flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className={`material-symbols-outlined text-[16px] ${submitting ? "animate-spin" : ""}`} aria-hidden="true">
              {submitting ? "progress_activity" : "task_alt"}
            </span>
            {submitting ? "Recording…" : outcome ? "Record outcome & resolve" : "Choose an outcome"}
          </button>
        </footer>
      </div>
    </div>
  );
}
