"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import {
  Card,
  ErrorBanner,
  FieldError,
  Loading,
  PageBody,
  PageHeader,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  enrollPatient,
  fetchEnrollmentOptions,
  fetchPatients,
  type EnrollmentOptions,
  type EnrollmentResponse,
  type Language,
} from "@/lib/clinicalApi";
import { emptyDraft, toEnrollmentRequest, validateEnrollment, type EnrollmentDraft } from "@/lib/enrollment";
import { LANGUAGE_NAMES, formatDate } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-label-md text-on-surface">{label}</span>
      {children}
      {hint && !error && <span className="font-body-sm text-on-surface-variant">{hint}</span>}
      <FieldError message={error} />
    </label>
  );
}

function EnrollmentForm({
  options,
  onEnrolled,
}: {
  options: EnrollmentOptions;
  onEnrolled: (result: EnrollmentResponse, name: string) => void;
}) {
  const [draft, setDraft] = useState<EnrollmentDraft>(() => emptyDraft(options));
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const errors = attempted ? validateEnrollment(draft, options) : {};
  const set = <K extends keyof EnrollmentDraft>(key: K, value: EnrollmentDraft[K]) => setDraft({ ...draft, [key]: value });
  const setBaseline = (code: string, value: string) => setDraft({ ...draft, baseline: { ...draft.baseline, [code]: value } });
  const procedure = options.procedures.find((p) => p.procedure_code === draft.procedure_code);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    setServerError(null);
    if (Object.keys(validateEnrollment(draft, options)).length) return;
    setSubmitting(true);
    try {
      const result = await enrollPatient(toEnrollmentRequest(draft, options));
      onEnrolled(result, draft.patient_name.trim());
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Enrollment failed. Try again.");
      setSubmitting(false);
    }
  };

  if (options.procedures.length === 0) {
    return (
      <ErrorBanner message="This hospital does not offer any procedure with an approved ruleset, so nobody can be enrolled yet." />
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-space-lg">
      <Card title="Patient">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
          <Field label="Full name" error={errors.patient_name}>
            <input className={inputClass} value={draft.patient_name} onChange={(e) => set("patient_name", e.target.value)} autoComplete="off" />
          </Field>
          <Field label="Hospital record number (MRN)" error={errors.mrn}>
            <input className={inputClass} value={draft.mrn} onChange={(e) => set("mrn", e.target.value)} autoComplete="off" />
          </Field>
          <Field label="WhatsApp number" hint="International format, e.g. +919876543210" error={errors.phone_e164}>
            <input className={inputClass} type="tel" value={draft.phone_e164} onChange={(e) => set("phone_e164", e.target.value)} />
          </Field>
          <Field label="Preferred language" hint="Check-ins and messages are sent in this language">
            <select className={inputClass} value={draft.language_code} onChange={(e) => set("language_code", e.target.value as Language)}>
              {options.languages.map((l) => (
                <option key={l} value={l}>{LANGUAGE_NAMES[l]}</option>
              ))}
            </select>
          </Field>
          <Field label="Date of birth (optional)" error={errors.date_of_birth}>
            <input className={inputClass} type="date" max={options.today} value={draft.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card title="Surgery and discharge">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
          <Field
            label="Procedure"
            hint={procedure ? `Monitored for ${procedure.observation_days} days · ruleset ${procedure.ruleset_version}` : undefined}
            error={errors.procedure_code}
          >
            <select className={inputClass} value={draft.procedure_code} onChange={(e) => set("procedure_code", e.target.value)}>
              {options.procedures.map((p) => (
                <option key={p.procedure_code} value={p.procedure_code}>{p.procedure_name}</option>
              ))}
            </select>
          </Field>
          <Field label="Surgery date" error={errors.surgery_date}>
            <input className={inputClass} type="date" max={options.today} value={draft.surgery_date} onChange={(e) => set("surgery_date", e.target.value)} />
          </Field>
          <Field label="Discharge date" hint="Post-op day 0" error={errors.discharge_date}>
            <input className={inputClass} type="date" max={options.today} value={draft.discharge_date} onChange={(e) => set("discharge_date", e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card title="Discharge baseline" subtitle="Optional. Later check-ins are compared with these, e.g. a pulse rise from baseline.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
          {options.baseline_parameters.map((p) => (
            <Field
              key={p.code}
              label={p.name}
              hint={p.type === "numeric" ? `${p.value_min}–${p.value_max}${p.unit ? ` ${p.unit === "C" ? "°C" : p.unit}` : ""}` : undefined}
              error={errors[`baseline.${p.code}`]}
            >
              {p.type === "ordinal" ? (
                <select className={inputClass} value={draft.baseline[p.code] ?? ""} onChange={(e) => setBaseline(p.code, e.target.value)}>
                  <option value="">Not recorded</option>
                  {p.options.map((o) => (
                    <option key={o.code} value={o.code}>{o.label}</option>
                  ))}
                </select>
              ) : (
                <input
                  className={inputClass}
                  type="number"
                  inputMode="decimal"
                  step={p.decimals > 0 ? 0.1 : 1}
                  min={p.value_min ?? undefined}
                  max={p.value_max ?? undefined}
                  value={draft.baseline[p.code] ?? ""}
                  onChange={(e) => setBaseline(p.code, e.target.value)}
                />
              )}
            </Field>
          ))}
        </div>
      </Card>

      <Card title="Consent">
        <div className="flex flex-col gap-space-md">
          <Field label="Consent form version" error={errors.consent_version}>
            <input className={`${inputClass} max-w-xs`} value={draft.consent_version} onChange={(e) => set("consent_version", e.target.value)} />
          </Field>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="mt-1"
              checked={draft.consent_confirmed}
              onChange={(e) => set("consent_confirmed", e.target.checked)}
            />
            <span className="font-body-md text-on-surface">
              The patient has given consent to remote monitoring and to receive WhatsApp messages.
            </span>
          </label>
          <FieldError message={errors.consent_confirmed} />
        </div>
      </Card>

      {serverError && <ErrorBanner message={serverError} />}

      <div className="flex justify-end">
        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          <span className={`material-symbols-outlined text-[16px] ${submitting ? "animate-spin" : ""}`} aria-hidden="true">
            {submitting ? "progress_activity" : "how_to_reg"}
          </span>
          {submitting ? "Enrolling…" : "Enroll patient"}
        </button>
      </div>
    </form>
  );
}

export default function EnrollmentPage() {
  const options = useApiData(fetchEnrollmentOptions);
  const loadRecent = useCallback(() => fetchPatients({ status: "all", sort: "recent", limit: 8 }), []);
  const recent = useApiData(loadRecent);
  const [enrolled, setEnrolled] = useState<{ result: EnrollmentResponse; name: string } | null>(null);
  const [formKey, setFormKey] = useState(0);

  return (
    <>
      <PageHeader title="Enrollment" />
      <PageBody>
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-space-lg items-start">
          <div className="flex flex-col gap-space-lg">
            {options.error && <ErrorBanner message={options.error} onRetry={options.reload} />}
            {!options.data && !options.error && <Loading label="Loading the enrollment form…" />}

            {enrolled && (
              <section role="status" className="bg-primary/5 border border-primary/30 rounded-xl p-space-md flex flex-col gap-space-sm">
                <h2 className="font-title-sm text-on-surface">
                  {enrolled.name} is enrolled{enrolled.result.returning_patient ? " (returning patient)" : ""}
                </h2>
                <p className="font-body-md text-on-surface-variant">
                  Post-op day {enrolled.result.post_op_day}. Monitoring runs until {formatDate(enrolled.result.monitoring_ends_on)}.{" "}
                  {enrolled.result.baseline_recorded} baseline reading{enrolled.result.baseline_recorded === 1 ? "" : "s"} recorded.
                </p>
                <div className="flex gap-space-sm">
                  <Link href={`/patients/${enrolled.result.episode_id}`} className={primaryButtonClass}>Open patient record</Link>
                  <button
                    type="button"
                    className={secondaryButtonClass}
                    onClick={() => {
                      setEnrolled(null);
                      setFormKey((k) => k + 1);
                    }}
                  >
                    Enroll another
                  </button>
                </div>
              </section>
            )}

            {options.data && !enrolled && (
              <EnrollmentForm
                key={formKey}
                options={options.data}
                onEnrolled={(result, name) => {
                  setEnrolled({ result, name });
                  recent.reload();
                }}
              />
            )}
          </div>

          <Card title="Recently enrolled">
            {!recent.data && <Loading />}
            {recent.data && recent.data.items.length === 0 && (
              <p className="font-body-md text-on-surface-variant">Nobody has been enrolled yet.</p>
            )}
            <ul className="flex flex-col divide-y divide-outline-variant/20">
              {recent.data?.items.map((p) => (
                <li key={p.episode_id} className="py-2">
                  <Link href={`/patients/${p.episode_id}`} className="font-label-md text-on-surface hover:text-primary hover:underline">
                    {p.patient_name}
                  </Link>
                  <div className="font-body-sm text-on-surface-variant">
                    {formatDate(p.enrolled_at)}
                    {p.enrolled_by_name ? ` by ${p.enrolled_by_name}` : ""} · POD {p.post_op_day}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </PageBody>
    </>
  );
}
