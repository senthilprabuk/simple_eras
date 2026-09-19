"use client";

import React, { useState } from "react";
import { useSession } from "@/components/SessionContext";
import {
  Card,
  ErrorBanner,
  FieldError,
  Loading,
  Notice,
  PageBody,
  PageHeader,
  StatTile,
  StatusPill,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { fetchHospital, updateHospital, type HospitalProfile } from "@/lib/clinicalApi";
import { formatDate } from "@/lib/format";
import { formatDuration } from "@/lib/triage";
import { useApiData } from "@/lib/useApiData";

const COMMON_TIMEZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York"];

function SettingsForm({ hospital, onSaved, onCancel }: { hospital: HospitalProfile; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(hospital.hospital_name);
  const [city, setCity] = useState(hospital.city ?? "");
  const [timezone, setTimezone] = useState(hospital.timezone);
  const [minutes, setMinutes] = useState(String(hospital.ack_window_secs / 60));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const minutesValue = Number(minutes);
  const minutesError = !Number.isInteger(minutesValue) || minutesValue < 1 || minutesValue > 120
    ? "A whole number of minutes from 1 to 120."
    : undefined;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (minutesError || !name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await updateHospital({ hospital_name: name.trim(), city: city.trim(), timezone: timezone.trim(), ack_window_secs: minutesValue * 60 });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="flex flex-col gap-space-md">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
        <label className="flex flex-col gap-1">
          <span className="font-label-md text-on-surface">Hospital name</span>
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
          <FieldError message={name.trim() ? undefined : "Enter a name."} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-label-md text-on-surface">City</span>
          <input className={inputClass} value={city} onChange={(e) => setCity(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-label-md text-on-surface">Timezone</span>
          <input className={inputClass} list="timezones" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          <datalist id="timezones">
            {COMMON_TIMEZONES.map((tz) => <option key={tz} value={tz} />)}
          </datalist>
          <span className="font-body-sm text-on-surface-variant">Decides what &ldquo;today&rdquo; and post-op day mean.</span>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-label-md text-on-surface">Acknowledgement window (minutes)</span>
          <input className={inputClass} type="number" min={1} max={120} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
          <FieldError message={minutesError} />
          {!minutesError && (
            <span className="font-body-sm text-on-surface-variant">
              Critical and emergency alerts not acknowledged within this are escalated.
            </span>
          )}
        </label>
      </div>
      {error && <ErrorBanner message={error} />}
      <div className="flex gap-space-sm justify-end">
        <button type="button" className={secondaryButtonClass} onClick={onCancel}>Cancel</button>
        <button type="submit" className={primaryButtonClass} disabled={saving || !!minutesError || !name.trim()}>
          {saving ? "Saving…" : "Save settings"}
        </button>
      </div>
    </form>
  );
}

export default function HospitalsPage() {
  const session = useSession();
  const { data, error, reload } = useApiData(fetchHospital);
  const [editing, setEditing] = useState(false);
  const canEdit = session.role === "superadmin";

  return (
    <>
      <PageHeader title="Hospitals" />
      <PageBody>
        <Notice>You can see and manage only your own hospital. Other hospitals on this service are not visible here.</Notice>

        {error && <ErrorBanner message={error} onRetry={reload} />}
        {!data && !error && <Loading label="Loading hospital…" />}

        {data && (
          <>
            <Card
              title={data.hospital_name}
              subtitle={`${data.hospital_code}${data.city ? ` · ${data.city}` : ""}`}
              actions={
                canEdit && !editing ? (
                  <button type="button" className={secondaryButtonClass} onClick={() => setEditing(true)}>
                    <span className="material-symbols-outlined text-[16px]" aria-hidden="true">edit</span>
                    Edit settings
                  </button>
                ) : (
                  <StatusPill status={data.is_active ? "active" : "inactive"} />
                )
              }
            >
              {editing ? (
                <SettingsForm
                  hospital={data}
                  onCancel={() => setEditing(false)}
                  onSaved={() => {
                    setEditing(false);
                    reload();
                  }}
                />
              ) : (
                <dl className="grid grid-cols-1 sm:grid-cols-3 gap-space-md">
                  <div>
                    <dt className="font-label-sm text-on-surface-variant uppercase tracking-wider">Timezone</dt>
                    <dd className="font-body-md text-on-surface">{data.timezone}</dd>
                  </div>
                  <div>
                    <dt className="font-label-sm text-on-surface-variant uppercase tracking-wider">Acknowledgement window</dt>
                    <dd className="font-body-md text-on-surface">{formatDuration(data.ack_window_secs)}</dd>
                  </div>
                  <div>
                    <dt className="font-label-sm text-on-surface-variant uppercase tracking-wider">Your access</dt>
                    <dd className="font-body-md text-on-surface">{canEdit ? "Can change settings" : "View only; superadmins change settings"}</dd>
                  </div>
                </dl>
              )}
            </Card>

            <section aria-label="Activity" className="grid grid-cols-2 lg:grid-cols-5 gap-gutter">
              <StatTile label="Active patients" value={String(data.stats.active_patients)} icon="personal_injury" />
              <StatTile label="Completed" value={String(data.stats.completed_patients)} icon="task_alt" />
              <StatTile label="Clinicians" value={String(data.stats.active_clinicians)} icon="badge" />
              <StatTile label="Unresolved alerts" value={String(data.stats.unresolved_alerts)} icon="notification_important" />
              <StatTile label="Check-ins, 7 days" value={String(data.stats.check_ins_last_7_days)} icon="fact_check" />
            </section>

            <Card title="Procedures offered">
              {data.procedures.length === 0 ? (
                <p className="font-body-md text-on-surface-variant">No procedures are enabled for this hospital.</p>
              ) : (
                <table className="w-full text-left">
                  <thead>
                    <tr className="text-on-surface-variant font-label-sm uppercase tracking-wider border-b border-outline-variant/30">
                      <th scope="col" className="py-2">Procedure</th>
                      <th scope="col" className="py-2">Monitoring period</th>
                      <th scope="col" className="py-2">Offered since</th>
                      <th scope="col" className="py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {data.procedures.map((p) => (
                      <tr key={p.procedure_code}>
                        <td className="py-2 font-body-md text-on-surface">{p.procedure_name} ({p.procedure_code})</td>
                        <td className="py-2 font-body-md text-on-surface">{p.observation_days} days</td>
                        <td className="py-2 font-body-md text-on-surface">{formatDate(p.enabled_on)}</td>
                        <td className="py-2"><StatusPill status={p.is_active ? "active" : "inactive"} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </>
        )}
      </PageBody>
    </>
  );
}
