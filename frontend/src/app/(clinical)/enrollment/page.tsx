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
  type BaselineParameter,
  type EnrollmentOptions,
  type EnrollmentResponse,
  type Gender,
  type Language,
  type Relationship,
} from "@/lib/clinicalApi";
import {
  BODY_CODES,
  MAX_CONTACTS,
  bmi,
  describeErrors,
  emptyContact,
  emptyDraft,
  fieldId,
  toEnrollmentRequest,
  validateEnrollment,
  type ContactDraft,
  type EnrollmentDraft,
} from "@/lib/enrollment";
import {
  GENDER_LABELS,
  LANGUAGE_NAMES,
  PRIVACY_LAW_NAMES,
  RELATIONSHIP_LABELS,
  formatDate,
  formatTimeWindow,
} from "@/lib/format";
import { useApiData } from "@/lib/useApiData";

interface ControlProps {
  id: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
}

/** A labelled control. The render prop receives the id and ARIA wiring for its error. */
function Field({
  label,
  hint,
  fieldKey,
  errors,
  children,
}: {
  label: string;
  hint?: React.ReactNode;
  fieldKey: string;
  errors: Record<string, string>;
  children: (control: ControlProps) => React.ReactNode;
}) {
  const id = fieldId(fieldKey);
  const error = errors[fieldKey];
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-label-md text-on-surface">
        {label}
      </label>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error ? `${id}-error` : hint ? `${id}-hint` : undefined,
      })}
      {hint && !error && (
        <span id={`${id}-hint`} className="font-body-sm text-on-surface-variant">
          {hint}
        </span>
      )}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

function Check({
  fieldKey,
  errors,
  checked,
  onChange,
  children,
}: {
  fieldKey: string;
  errors: Record<string, string>;
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: React.ReactNode;
}) {
  const id = fieldId(fieldKey);
  const error = errors[fieldKey];
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="flex items-start gap-2 cursor-pointer">
        <input
          id={id}
          type="checkbox"
          className="mt-1"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        />
        <span className="font-body-md text-on-surface">{children}</span>
      </label>
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

const choiceClass = (selected: boolean) =>
  `p-3 rounded-lg border cursor-pointer transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary ${
    selected
      ? "border-primary bg-surface-container-low text-primary"
      : "border-outline-variant/40 text-on-surface hover:border-outline-variant"
  }`;

function unitLabel(unit: string | null): string {
  if (!unit) return "";
  return ` ${unit === "C" ? "°C" : unit}`;
}

function focusField(key: string) {
  const el = document.getElementById(fieldId(key));
  if (!el) return;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  el.focus({ preventScroll: true });
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
  const problems = describeErrors(errors, options);
  const set = <K extends keyof EnrollmentDraft>(key: K, value: EnrollmentDraft[K]) => setDraft({ ...draft, [key]: value });
  const setBaseline = (code: string, value: string) => setDraft({ ...draft, baseline: { ...draft.baseline, [code]: value } });
  const setContact = (index: number, patch: Partial<ContactDraft>) =>
    setDraft({ ...draft, contacts: draft.contacts.map((c, i) => (i === index ? { ...c, ...patch } : c)) });
  const procedure = options.procedures.find((p) => p.procedure_code === draft.procedure_code);
  const bodyParams = options.baseline_parameters.filter((p) => BODY_CODES.includes(p.code));
  const dischargeParams = options.baseline_parameters.filter((p) => !BODY_CODES.includes(p.code));
  const bodyMassIndex = bmi(draft.baseline.height_cm, draft.baseline.weight_kg);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    setServerError(null);
    const found = describeErrors(validateEnrollment(draft, options), options);
    if (found.length) {
      // The first problem may be far above the button: take the nurse to it.
      focusField(found[0].key);
      return;
    }
    setSubmitting(true);
    try {
      const result = await enrollPatient(toEnrollmentRequest(draft, options));
      onEnrolled(result, draft.patient_name.trim());
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Enrollment failed. Try again.");
      setSubmitting(false);
    }
  };

  const baselineField = (p: BaselineParameter) => (
    <Field
      key={p.code}
      label={p.name}
      fieldKey={`baseline.${p.code}`}
      errors={errors}
      hint={p.type === "numeric" ? `${p.value_min}–${p.value_max}${unitLabel(p.unit)}` : undefined}
    >
      {(control) =>
        p.type === "ordinal" ? (
          <select {...control} className={inputClass} value={draft.baseline[p.code] ?? ""} onChange={(e) => setBaseline(p.code, e.target.value)}>
            <option value="">Not recorded</option>
            {p.options.map((o) => (
              <option key={o.code} value={o.code}>{o.label}</option>
            ))}
          </select>
        ) : (
          <input
            {...control}
            className={inputClass}
            type="number"
            inputMode="decimal"
            step={p.decimals > 0 ? 0.1 : 1}
            min={p.value_min ?? undefined}
            max={p.value_max ?? undefined}
            value={draft.baseline[p.code] ?? ""}
            onChange={(e) => setBaseline(p.code, e.target.value)}
          />
        )
      }
    </Field>
  );

  if (options.procedures.length === 0) {
    return (
      <ErrorBanner message="This hospital does not offer any procedure with an approved ruleset, so nobody can be enrolled yet." />
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-space-lg">
      <Card title="Patient">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
          <Field label="Full name" fieldKey="patient_name" errors={errors}>
            {(c) => <input {...c} className={inputClass} value={draft.patient_name} onChange={(e) => set("patient_name", e.target.value)} autoComplete="off" />}
          </Field>
          <Field label="Hospital record number (MRN)" fieldKey="mrn" errors={errors}>
            {(c) => <input {...c} className={inputClass} value={draft.mrn} onChange={(e) => set("mrn", e.target.value)} autoComplete="off" />}
          </Field>
          <Field label="Sex" hint="As recorded by the hospital" fieldKey="gender" errors={errors}>
            {(c) => (
              <select {...c} className={inputClass} value={draft.gender} onChange={(e) => set("gender", e.target.value as Gender | "")}>
                <option value="">Choose…</option>
                {(["female", "male", "other", "unknown"] as Gender[]).map((g) => (
                  <option key={g} value={g}>{GENDER_LABELS[g]}</option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Date of birth (optional)" fieldKey="date_of_birth" errors={errors}>
            {(c) => <input {...c} className={inputClass} type="date" max={options.today} value={draft.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} />}
          </Field>
          <Field label="Preferred language" hint="Check-ins and messages are sent in this language" fieldKey="language_code" errors={errors}>
            {(c) => (
              <select {...c} className={inputClass} value={draft.language_code} onChange={(e) => set("language_code", e.target.value as Language)}>
                {options.languages.map((l) => (
                  <option key={l} value={l}>{LANGUAGE_NAMES[l]}</option>
                ))}
              </select>
            )}
          </Field>
        </div>
      </Card>

      <Card title="How to reach the patient" subtitle="WhatsApp carries the daily check-in. The other two are used if WhatsApp stops working.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
          <Field label="WhatsApp number" hint="With country code, e.g. +91 98765 43210" fieldKey="phone_e164" errors={errors}>
            {(c) => <input {...c} className={inputClass} type="tel" value={draft.phone_e164} onChange={(e) => set("phone_e164", e.target.value)} />}
          </Field>
          <Field label="SMS number (optional)" hint="A different phone, if there is one" fieldKey="alt_phone_e164" errors={errors}>
            {(c) => <input {...c} className={inputClass} type="tel" placeholder="+91" value={draft.alt_phone_e164} onChange={(e) => set("alt_phone_e164", e.target.value)} />}
          </Field>
          <Field label="Email (optional)" fieldKey="email" errors={errors}>
            {(c) => <input {...c} className={inputClass} type="email" value={draft.email} onChange={(e) => set("email", e.target.value)} />}
          </Field>
        </div>
      </Card>

      <Card title="Home address" subtitle="Where an ambulance or a home-visit nurse would go.">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-space-md">
          <div className="md:col-span-6">
            <Field label="House and street" fieldKey="address_line" errors={errors}>
              {(c) => <input {...c} className={inputClass} value={draft.address_line} onChange={(e) => set("address_line", e.target.value)} autoComplete="off" />}
            </Field>
          </div>
          <div className="md:col-span-2">
            <Field label="Town or city (optional)" fieldKey="address_city" errors={errors}>
              {(c) => <input {...c} className={inputClass} value={draft.address_city} onChange={(e) => set("address_city", e.target.value)} />}
            </Field>
          </div>
          <div className="md:col-span-2">
            <Field label="District" fieldKey="address_district" errors={errors}>
              {(c) => <input {...c} className={inputClass} value={draft.address_district} onChange={(e) => set("address_district", e.target.value)} />}
            </Field>
          </div>
          <div className="md:col-span-1">
            <Field label="State (optional)" fieldKey="address_state" errors={errors}>
              {(c) => <input {...c} className={inputClass} value={draft.address_state} onChange={(e) => set("address_state", e.target.value)} />}
            </Field>
          </div>
          <div className="md:col-span-1">
            <Field label="PIN code" fieldKey="address_postal_code" errors={errors}>
              {(c) => <input {...c} className={inputClass} inputMode="numeric" value={draft.address_postal_code} onChange={(e) => set("address_postal_code", e.target.value)} />}
            </Field>
          </div>
        </div>
      </Card>

      <Card
        title="Emergency contacts"
        subtitle="Who to call if the patient cannot answer, in the order to call them. Use someone else's number, not the patient's."
      >
        <div className="flex flex-col gap-space-md">
          {draft.contacts.map((contact, i) => (
            <fieldset key={i} className="flex flex-col gap-space-sm">
              <legend className="sr-only">Contact {i + 1}</legend>
              <div className="flex items-center justify-between gap-space-sm">
                <span className="font-label-md text-on-surface-variant" aria-hidden="true">
                  Contact {i + 1}
                  {draft.contacts.length > 1 && i === 0 ? " · call first" : ""}
                </span>
                {draft.contacts.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setDraft({ ...draft, contacts: draft.contacts.filter((_, j) => j !== i) })}
                    className="inline-flex items-center gap-1 font-label-md text-on-surface-variant hover:text-error cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[16px]" aria-hidden="true">delete</span>
                    Remove
                    <span className="sr-only"> contact {i + 1}</span>
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
                <Field label="Name" fieldKey={`contacts.${i}.name`} errors={errors}>
                  {(c) => <input {...c} className={inputClass} value={contact.name} onChange={(e) => setContact(i, { name: e.target.value })} autoComplete="off" />}
                </Field>
                <Field label="Relationship" fieldKey={`contacts.${i}.relationship`} errors={errors}>
                  {(c) => (
                    <select
                      {...c}
                      className={inputClass}
                      value={contact.relationship}
                      onChange={(e) => setContact(i, { relationship: e.target.value as Relationship | "" })}
                    >
                      <option value="">Choose…</option>
                      {Object.entries(RELATIONSHIP_LABELS).map(([code, label]) => (
                        <option key={code} value={code}>{label}</option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Phone" fieldKey={`contacts.${i}.phone_e164`} errors={errors}>
                  {(c) => <input {...c} className={inputClass} type="tel" value={contact.phone_e164} onChange={(e) => setContact(i, { phone_e164: e.target.value })} />}
                </Field>
              </div>
            </fieldset>
          ))}
          {draft.contacts.length < MAX_CONTACTS && (
            <button
              type="button"
              className={`${secondaryButtonClass} w-fit`}
              onClick={() => setDraft({ ...draft, contacts: [...draft.contacts, emptyContact()] })}
            >
              <span className="material-symbols-outlined text-[16px]" aria-hidden="true">person_add</span>
              Add another contact
            </button>
          )}
        </div>
      </Card>

      <Card title="Surgery and discharge">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
          <Field
            label="Procedure"
            hint={procedure ? `Monitored for ${procedure.observation_days} days · ruleset ${procedure.ruleset_version}` : undefined}
            fieldKey="procedure_code"
            errors={errors}
          >
            {(c) => (
              <select {...c} className={inputClass} value={draft.procedure_code} onChange={(e) => set("procedure_code", e.target.value)}>
                {options.procedures.map((p) => (
                  <option key={p.procedure_code} value={p.procedure_code}>{p.procedure_name}</option>
                ))}
              </select>
            )}
          </Field>
          <Field
            label="Operative side"
            hint="Shown beside every alert, so calf symptoms can be read against the right leg"
            fieldKey="operative_side"
            errors={errors}
          >
            {(c) => (
              <select
                {...c}
                className={inputClass}
                value={draft.operative_side}
                onChange={(e) => set("operative_side", e.target.value as EnrollmentDraft["operative_side"])}
              >
                <option value="">Choose…</option>
                <option value="left">Left knee</option>
                <option value="right">Right knee</option>
                <option value="bilateral">Both knees</option>
              </select>
            )}
          </Field>
          <Field label="Surgery date" fieldKey="surgery_date" errors={errors}>
            {(c) => <input {...c} className={inputClass} type="date" max={options.today} value={draft.surgery_date} onChange={(e) => set("surgery_date", e.target.value)} />}
          </Field>
          <Field label="Discharge date" hint="Post-op day 0" fieldKey="discharge_date" errors={errors}>
            {(c) => <input {...c} className={inputClass} type="date" max={options.today} value={draft.discharge_date} onChange={(e) => set("discharge_date", e.target.value)} />}
          </Field>
        </div>
      </Card>

      {bodyParams.length > 0 && (
        <Card title="Body measurements" subtitle="Optional. Measured once at discharge and not asked again.">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
            {bodyParams.filter((p) => p.code === "height_cm" || p.code === "weight_kg").map(baselineField)}
            <div className="flex flex-col gap-1">
              <span className="font-label-md text-on-surface">BMI</span>
              <output
                aria-live="polite"
                className={`px-3 py-2 rounded-lg bg-surface-container-low font-body-md ${
                  bodyMassIndex !== null && bodyMassIndex > 35 ? "text-error font-semibold" : "text-on-surface"
                }`}
              >
                {bodyMassIndex ?? "—"}
              </output>
              <span className="font-body-sm text-on-surface-variant">
                {bodyMassIndex !== null && bodyMassIndex > 35 ? "Above 35: higher risk" : "Worked out from height and weight"}
              </span>
            </div>
            {bodyParams.filter((p) => p.code === "bp_sys" || p.code === "bp_dia").map(baselineField)}
          </div>
        </Card>
      )}

      <Card title="Discharge baseline" subtitle="Optional. Later check-ins are compared with these, e.g. a pulse rise from baseline.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">{dischargeParams.map(baselineField)}</div>
      </Card>

      <Card title="Daily check-in time" subtitle="When the patient would rather be asked, in the hospital's time.">
        <fieldset className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <legend className="sr-only">Check-in time window</legend>
          {options.checkin_windows.map((w) => (
            <label key={w.code} className={choiceClass(draft.checkin_window === w.code)}>
              <input
                type="radio"
                name="checkin_window"
                value={w.code}
                checked={draft.checkin_window === w.code}
                onChange={() => set("checkin_window", w.code)}
                className="sr-only"
              />
              <span className="font-label-md block">{w.label}</span>
              <span className="font-body-sm text-on-surface-variant">{formatTimeWindow(w.start, w.end)}</span>
            </label>
          ))}
        </fieldset>
      </Card>

      <Card title="Consent">
        <div className="flex flex-col gap-space-md">
          <Field label="Consent form version" fieldKey="consent_version" errors={errors}>
            {(c) => <input {...c} className={`${inputClass} max-w-xs`} value={draft.consent_version} onChange={(e) => set("consent_version", e.target.value)} />}
          </Field>
          <Check fieldKey="consent_confirmed" errors={errors} checked={draft.consent_confirmed} onChange={(v) => set("consent_confirmed", v)}>
            The patient has given consent to remote monitoring and to receive WhatsApp messages.
          </Check>
          <Check
            fieldKey="data_processing_consent"
            errors={errors}
            checked={draft.data_processing_consent}
            onChange={(v) => set("data_processing_consent", v)}
          >
            The patient consents to their health data being stored and processed in the cloud, under{" "}
            {PRIVACY_LAW_NAMES[options.privacy_law] ?? options.privacy_law}.
          </Check>
          <fieldset className="flex flex-col gap-1.5" aria-describedby={errors.contact_sharing_consent ? `${fieldId("contact_sharing_consent")}-error` : undefined}>
            <legend className="font-body-md text-on-surface mb-1.5">
              May the care team discuss the patient&apos;s recovery with their emergency contacts?
            </legend>
            <div className="flex flex-wrap gap-2">
              {(["yes", "no"] as const).map((answer, i) => (
                <label key={answer} className={`${choiceClass(draft.contact_sharing_consent === answer)} py-2 min-w-24 text-center`}>
                  <input
                    id={i === 0 ? fieldId("contact_sharing_consent") : undefined}
                    type="radio"
                    name="contact_sharing_consent"
                    value={answer}
                    checked={draft.contact_sharing_consent === answer}
                    onChange={() => set("contact_sharing_consent", answer)}
                    className="sr-only"
                  />
                  <span className="font-label-md">{answer === "yes" ? "Yes" : "No"}</span>
                </label>
              ))}
            </div>
            <span className="font-body-sm text-on-surface-variant">Either answer is recorded with the enrollment.</span>
            <FieldError id={`${fieldId("contact_sharing_consent")}-error`} message={errors.contact_sharing_consent} />
          </fieldset>
        </div>
      </Card>

      {problems.length > 0 && (
        <div role="alert" className="bg-error-container/60 border border-error/30 rounded-xl p-space-md flex flex-col gap-1.5">
          <h2 className="font-title-sm text-on-error-container">
            {problems.length === 1 ? "1 field needs attention" : `${problems.length} fields need attention`}
          </h2>
          <ul className="flex flex-wrap gap-x-4 gap-y-1">
            {problems.map((p) => (
              <li key={p.key}>
                <button type="button" onClick={() => focusField(p.key)} className="font-body-md text-on-error-container underline cursor-pointer">
                  {p.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

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
