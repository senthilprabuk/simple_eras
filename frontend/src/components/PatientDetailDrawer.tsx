"use client";

import React, { useState } from "react";
import { PatientQueueItem } from "@/data/mockPatients";

interface PatientDetailDrawerProps {
  patient: PatientQueueItem | null;
  onClose: () => void;
  onResolveAlert?: (patientId: string, outcome: string, note: string) => void;
}

export default function PatientDetailDrawer({
  patient,
  onClose,
  onResolveAlert,
}: PatientDetailDrawerProps) {
  const [outcome, setOutcome] = useState<string>("reassured");
  const [note, setNote] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  if (!patient) return null;

  const handleResolve = () => {
    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      onResolveAlert?.(patient.id, outcome, note);
      onClose();
    }, 600);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-xs transition-opacity animate-in fade-in">
      <div className="w-full max-w-xl bg-surface-container-lowest h-full shadow-2xl border-l border-outline-variant/40 flex flex-col justify-between">
        {/* Header */}
        <div className="p-space-lg border-b border-outline-variant/30 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-headline-md text-headline-md font-bold text-on-surface">
                {patient.name}
              </h3>
              <span className="font-label-sm text-label-sm px-2 py-0.5 rounded bg-surface-container-low text-primary font-semibold">
                POD {patient.post_op_day}
              </span>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              MRN #{patient.mrn} · {patient.procedure} · St. Mary's Orthopedic
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-bright hover:text-on-surface cursor-pointer"
          >
            <span className="material-symbols-outlined text-[22px]">close</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-space-lg overflow-y-auto flex-1 flex flex-col gap-space-lg">
          {/* Active Tiers & Flags */}
          <div className="bg-surface-bright/50 border border-outline-variant/30 rounded-xl p-space-md">
            <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider block mb-2">
              Current Evaluation Signals (TKR Ruleset v1.3.0)
            </span>
            <div className="flex flex-col gap-2">
              {patient.reasons.map((r, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between bg-surface-container-lowest px-3 py-2 rounded-lg border border-outline-variant/30"
                >
                  <span className="font-body-md text-body-md text-on-surface">
                    {r.text}
                  </span>
                  <span
                    className={`font-label-sm text-label-sm px-2 py-0.5 rounded ${
                      r.isSevere
                        ? "bg-error text-on-error font-semibold"
                        : "bg-surface-bright text-on-surface-variant"
                    }`}
                  >
                    {r.isSevere ? "Score: 3 (Override)" : "Score: 2"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Vitals Trajectory vs Baseline */}
          <div className="bg-surface-bright/50 border border-outline-variant/30 rounded-xl p-space-md">
            <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider block mb-3">
              Baseline vs Current Submission
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-surface-container-lowest p-3 rounded-lg border border-outline-variant/20">
                <span className="font-label-sm text-label-sm text-on-surface-variant block">Temp</span>
                <span className="font-headline-sm font-bold text-error">38.6°C</span>
                <span className="font-body-sm text-on-surface-variant block text-xs">Base: 36.8°C</span>
              </div>
              <div className="bg-surface-container-lowest p-3 rounded-lg border border-outline-variant/20">
                <span className="font-label-sm text-label-sm text-on-surface-variant block">Pulse (HR)</span>
                <span className="font-headline-sm font-bold text-on-surface">96 bpm</span>
                <span className="font-body-sm text-on-surface-variant block text-xs">Base: 72 bpm</span>
              </div>
              <div className="bg-surface-container-lowest p-3 rounded-lg border border-outline-variant/20">
                <span className="font-label-sm text-label-sm text-on-surface-variant block">Pain Scale</span>
                <span className="font-headline-sm font-bold text-error">7 / 10</span>
                <span className="font-body-sm text-on-surface-variant block text-xs">Base: 3 / 10</span>
              </div>
              <div className="bg-surface-container-lowest p-3 rounded-lg border border-outline-variant/20">
                <span className="font-label-sm text-label-sm text-on-surface-variant block">Daily Steps</span>
                <span className="font-headline-sm font-bold text-tertiary">150</span>
                <span className="font-body-sm text-on-surface-variant block text-xs">Drop from 520</span>
              </div>
            </div>
          </div>

          {/* Wound Photo Review */}
          <div className="bg-surface-bright/50 border border-outline-variant/30 rounded-xl p-space-md">
            <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider block mb-2">
              Wound Photograph (Signed S3 Access)
            </span>
            <div className="flex gap-3">
              <div className="flex-1 border border-outline-variant/40 rounded-lg p-3 bg-surface-container-lowest flex flex-col items-center justify-center min-h-[130px] text-center">
                <span className="material-symbols-outlined text-[32px] text-primary mb-1">
                  image
                </span>
                <span className="font-label-sm text-label-sm text-on-surface font-medium">
                  POD {patient.post_op_day} (Today)
                </span>
                <span className="font-body-sm text-[11px] text-on-surface-variant">
                  Exudate &amp; mild erythema reported
                </span>
              </div>
              <div className="flex-1 border border-outline-variant/40 rounded-lg p-3 bg-surface-container-lowest flex flex-col items-center justify-center min-h-[130px] text-center opacity-70">
                <span className="material-symbols-outlined text-[32px] text-outline mb-1">
                  history
                </span>
                <span className="font-label-sm text-label-sm text-on-surface font-medium">
                  POD {patient.post_op_day - 1} (Yesterday)
                </span>
                <span className="font-body-sm text-[11px] text-on-surface-variant">
                  Comparison baseline
                </span>
              </div>
            </div>
          </div>

          {/* Outcome Recording Section (LLD Section 3 / POST /v1/clinic/alerts/{id}/resolve) */}
          <div className="bg-surface-container-lowest border border-outline-variant/40 rounded-xl p-space-md">
            <span className="font-label-sm text-label-sm text-primary uppercase tracking-wider font-semibold block mb-2">
              Record Clinical Decision &amp; Resolve Alert
            </span>
            <p className="font-body-sm text-body-sm text-on-surface-variant mb-3">
              Per clinical governance (PRD FR-27), every alert must reach a recorded outcome before closure.
            </p>

            <div className="grid grid-cols-2 gap-2 mb-3">
              {[
                { id: "reassured", label: "Reassured & Continuing" },
                { id: "plan_adjusted", label: "Care Plan Adjusted" },
                { id: "same_day_review", label: "Same-Day Review Arranged" },
                { id: "emergency", label: "Escalated to Emergency Care" },
              ].map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setOutcome(item.id)}
                  className={`p-2.5 rounded-lg border text-left font-label-md text-label-md transition-colors cursor-pointer ${
                    outcome === item.id
                      ? "border-primary bg-surface-container-low text-primary font-semibold"
                      : "border-outline-variant/40 bg-surface-container-lowest text-on-surface-variant hover:border-outline-variant"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <textarea
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Clinical note: Reviewed by phone with patient and daughter. Instructions reiterated..."
              className="w-full p-2.5 bg-surface-bright border border-outline-variant/40 rounded-lg font-body-sm text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        {/* Footer Actions */}
        <div className="p-space-lg border-t border-outline-variant/30 flex items-center justify-end gap-space-sm bg-surface-container-lowest">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg font-label-md text-label-md text-on-surface-variant hover:bg-surface-bright cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleResolve}
            className="px-5 py-2 rounded-lg bg-primary text-on-primary font-label-md text-label-md hover:bg-primary/90 transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
          >
            <span className="material-symbols-outlined text-[16px]">task_alt</span>
            <span>{isSubmitting ? "Recording..." : "Record Outcome & Resolve"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
