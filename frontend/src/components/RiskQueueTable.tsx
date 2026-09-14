"use client";

import React, { useState } from "react";
import { PatientQueueItem } from "@/data/mockPatients";

interface RiskQueueTableProps {
  patients: PatientQueueItem[];
  onSelectPatient?: (patient: PatientQueueItem) => void;
}

export default function RiskQueueTable({
  patients: initialPatients,
  onSelectPatient,
}: RiskQueueTableProps) {
  const [patients, setPatients] = useState<PatientQueueItem[]>(initialPatients);
  const [actionLoading, setActionLoading] = useState<{ [key: string]: boolean }>({});

  const handleActionClick = (patientId: string, actionType: string) => {
    setActionLoading((prev) => ({ ...prev, [patientId]: true }));

    setTimeout(() => {
      setActionLoading((prev) => ({ ...prev, [patientId]: false }));
      setPatients((prevList) =>
        prevList.map((item) => {
          if (item.id === patientId) {
            if (actionType === "call") {
              return {
                ...item,
                acknowledged: true,
                acknowledged_text: "Call initiated & Ack by On-Call",
                action_type: "none",
              };
            } else if (actionType === "ping") {
              return {
                ...item,
                acknowledged_text: "WhatsApp Reminder Dispatched (Just now)",
                action_type: "none",
              };
            } else {
              return {
                ...item,
                acknowledged: true,
                acknowledged_text: "Ack by Nurse Sarah J. (Just now)",
                action_type: "none",
              };
            }
          }
          return item;
        })
      );
    }, 600);
  };

  return (
    <section
      aria-label="Risk Queue Table"
      className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 overflow-hidden shadow-sm"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[980px]">
          <thead>
            <tr className="bg-surface-bright/70 border-b border-outline-variant/30 text-on-surface-variant font-label-sm text-label-sm uppercase tracking-wider">
              <th className="py-3 px-space-md w-[140px]">Tier Severity</th>
              <th className="py-3 px-space-md w-[220px]">Patient &amp; Cohort Day</th>
              <th className="py-3 px-space-md">Clinical Flag Reasons</th>
              <th className="py-3 px-space-md w-[130px]">Alert Age / SLA</th>
              <th className="py-3 px-space-md w-[260px]">Protocol Action</th>
              <th className="py-3 px-space-md text-right w-[60px]">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/30">
            {patients.map((patient) => {
              const isLoading = !!actionLoading[patient.id];

              return (
                <tr
                  key={patient.id}
                  className="hover:bg-surface-bright/60 transition-colors group"
                >
                  {/* Tier Severity */}
                  <td className="py-3.5 px-space-md align-middle">
                    {patient.tier === "emergency" && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-error text-on-error font-label-sm text-label-sm font-semibold tracking-wide">
                        <span className="material-symbols-outlined text-[14px]">
                          e911_emergency
                        </span>
                        EMERGENCY
                      </span>
                    )}

                    {patient.tier === "critical" && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-surface-container-lowest border border-error text-error font-label-sm text-label-sm font-semibold tracking-wide">
                        <span className="material-symbols-outlined text-[14px]">
                          crisis_alert
                        </span>
                        CRITICAL
                      </span>
                    )}

                    {patient.tier === "review" && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-tertiary-fixed text-on-tertiary-fixed font-label-sm text-label-sm font-semibold tracking-wide">
                        <span className="material-symbols-outlined text-[14px]">
                          search
                        </span>
                        REVIEW
                      </span>
                    )}

                    {patient.tier === "missed" && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-surface-bright border border-outline-variant/50 text-on-surface-variant font-label-sm text-label-sm font-semibold tracking-wide">
                        <span className="material-symbols-outlined text-[14px]">
                          schedule
                        </span>
                        MISSED
                      </span>
                    )}
                  </td>

                  {/* Patient & Cohort Day */}
                  <td className="py-3.5 px-space-md align-middle">
                    <div className="flex flex-col">
                      <div className="flex items-center gap-1.5">
                        <span className="font-title-sm text-title-sm font-semibold text-on-surface">
                          {patient.name}
                        </span>
                        <span className="font-body-sm text-body-sm text-on-surface-variant">
                          · POD {patient.post_op_day} ({patient.procedure})
                        </span>
                      </div>
                      <span className="font-label-sm text-label-sm text-on-surface-variant">
                        MRN: #{patient.mrn}
                      </span>
                    </div>
                  </td>

                  {/* Clinical Flag Reasons */}
                  <td className="py-3.5 px-space-md align-middle">
                    <div className="flex flex-wrap gap-1.5">
                      {patient.reasons.map((r, i) => (
                        <span
                          key={i}
                          className={`inline-flex items-center px-2 py-0.5 rounded bg-surface-bright border font-body-sm text-body-sm ${
                            r.isSevere
                              ? "border-error/30 text-error font-medium"
                              : "border-outline-variant/40 text-on-surface"
                          }`}
                        >
                          {r.text}
                        </span>
                      ))}
                    </div>
                  </td>

                  {/* Alert Age / SLA */}
                  <td className="py-3.5 px-space-md align-middle">
                    {patient.tier === "emergency" ? (
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-error opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-error"></span>
                          </span>
                          <span className="font-title-sm text-title-sm font-semibold text-error">
                            {patient.alert_age_text}
                          </span>
                        </div>
                        <span className="font-label-sm text-label-sm text-on-surface-variant">
                          {patient.sla_text}
                        </span>
                      </div>
                    ) : patient.tier === "critical" ? (
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-tertiary"></span>
                          <span className="font-title-sm text-title-sm font-semibold text-tertiary">
                            {patient.alert_age_text}
                          </span>
                        </div>
                        <span className="font-label-sm text-label-sm text-on-surface-variant">
                          {patient.sla_text}
                        </span>
                      </div>
                    ) : (
                      <div>
                        <span className="font-title-sm text-title-sm font-medium text-on-surface-variant">
                          {patient.alert_age_text}
                        </span>
                        <span className="block font-label-sm text-label-sm text-on-surface-variant">
                          {patient.sla_text}
                        </span>
                      </div>
                    )}
                  </td>

                  {/* Protocol Action */}
                  <td className="py-3.5 px-space-md align-middle">
                    {patient.action_type === "call" && !patient.acknowledged && (
                      <div className="flex flex-col gap-1">
                        <button
                          type="button"
                          disabled={isLoading}
                          onClick={() => handleActionClick(patient.id, "call")}
                          className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-surface-container-lowest border border-primary text-primary font-label-md text-label-md rounded hover:bg-surface-container-low transition-colors w-fit cursor-pointer"
                        >
                          <span className="material-symbols-outlined text-[16px]">
                            {isLoading ? "sync" : "call"}
                          </span>
                          {isLoading ? "Connecting..." : "Acknowledge & Call"}
                        </button>
                        <span className="font-label-sm text-label-sm text-on-surface-variant">
                          Protocol: Rapid On-Call Escalation
                        </span>
                      </div>
                    )}

                    {patient.action_type === "acknowledge" && !patient.acknowledged && (
                      <button
                        type="button"
                        disabled={isLoading}
                        onClick={() => handleActionClick(patient.id, "acknowledge")}
                        className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-surface-container-lowest border border-primary text-primary font-label-md text-label-md rounded hover:bg-surface-container-low transition-colors cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[16px]">
                          {isLoading ? "sync" : "check_circle"}
                        </span>
                        {isLoading ? "Updating..." : "Acknowledge"}
                      </button>
                    )}

                    {patient.action_type === "ping" && !patient.acknowledged_text && (
                      <button
                        type="button"
                        disabled={isLoading}
                        onClick={() => handleActionClick(patient.id, "ping")}
                        className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-surface-container-lowest border border-outline-variant/60 text-secondary font-label-md text-label-md rounded hover:bg-surface-container-low hover:border-secondary transition-colors cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[16px] text-primary">
                          {isLoading ? "sync" : "chat"}
                        </span>
                        {isLoading ? "Dispatching..." : "Ping WhatsApp Reminder"}
                      </button>
                    )}

                    {(patient.acknowledged || patient.acknowledged_text) && (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface-bright border border-outline-variant/30 text-on-surface-variant font-label-sm text-label-sm">
                        <span className="material-symbols-outlined text-[15px] text-primary">
                          verified
                        </span>
                        <span>{patient.acknowledged_text}</span>
                      </div>
                    )}
                  </td>

                  {/* Details chevron */}
                  <td className="py-3.5 px-space-md align-middle text-right">
                    <button
                      type="button"
                      onClick={() => onSelectPatient?.(patient)}
                      aria-label={`View records for ${patient.name}`}
                      className="p-1 rounded text-on-surface-variant hover:text-primary hover:bg-surface-container-low transition-colors cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-[20px]">
                        chevron_right
                      </span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
