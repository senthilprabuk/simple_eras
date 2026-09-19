"use client";

import React, { useState } from "react";
import {
  Card,
  ErrorBanner,
  FieldError,
  Loading,
  Notice,
  PageBody,
  StatusPill,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import type { PrivacyLaw } from "@/lib/clinicalApi";
import { hospitalDraft, toHospitalFields, validateHospital, type HospitalDraft } from "@/lib/appAdmin";
import {
  createHospital,
  createHospitalAccount,
  fetchHospital,
  fetchHospitals,
  fetchPlatformOptions,
  updateHospital,
  type AccountInput,
  type PlatformHospitalDetail,
  type PlatformOptions,
} from "@/lib/appAdminApi";
import { formatDate } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";

const PRIVACY_LAW_CHOICES: Record<string, string> = {
  "DPDP-2023": "DPDP Act 2023 (India)",
  HIPAA: "HIPAA (United States)",
};

function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-label-md text-on-surface">{label}</span>
      {children}
      {hint && !error && <span className="font-body-sm text-on-surface-variant">{hint}</span>}
      <FieldError message={error} />
    </label>
  );
}

const message = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

function HospitalForm({
  hospital,
  options,
  onSaved,
  onCancel,
}: {
  hospital: PlatformHospitalDetail | null;
  options: PlatformOptions;
  onSaved: (saved: PlatformHospitalDetail) => void;
  onCancel: () => void;
}) {
  const isNew = hospital === null;
  const [draft, setDraft] = useState<HospitalDraft>(() => hospitalDraft(hospital ?? undefined));
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const errors = attempted ? validateHospital(draft, isNew, options.timezones) : {};
  const set = <K extends keyof HospitalDraft>(key: K, value: HospitalDraft[K]) => {
    setDraft({ ...draft, [key]: value });
    setSaved(false);
  };
  const toggleProcedure = (code: string) =>
    set("procedure_codes", draft.procedure_codes.includes(code)
      ? draft.procedure_codes.filter((c) => c !== code)
      : [...draft.procedure_codes, code]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    setError(null);
    if (Object.keys(validateHospital(draft, isNew, options.timezones)).length) return;
    setSaving(true);
    try {
      const fields = toHospitalFields(draft);
      const result = isNew
        ? await createHospital({ ...fields, hospital_code: draft.hospital_code.trim().toUpperCase() })
        : await updateHospital(hospital.hospital_id, fields);
      setSaved(true);
      onSaved(result);
    } catch (err) {
      setError(message(err, "Could not save the hospital."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} noValidate className="flex flex-col gap-space-md">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-md">
        <Field label="Code" hint={isNew ? "Short and permanent, e.g. CBE-02" : "Cannot change"} error={errors.hospital_code}>
          <input
            className={inputClass}
            value={draft.hospital_code}
            disabled={!isNew}
            onChange={(e) => set("hospital_code", e.target.value.toUpperCase())}
            autoComplete="off"
          />
        </Field>
        <Field label="City (optional)">
          <input className={inputClass} value={draft.city} onChange={(e) => set("city", e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Hospital name" error={errors.hospital_name}>
            <input className={inputClass} value={draft.hospital_name} onChange={(e) => set("hospital_name", e.target.value)} />
          </Field>
        </div>
        <Field label="Time zone" hint="Decides what 'today' and post-op day mean" error={errors.timezone}>
          <input className={inputClass} list="timezones" value={draft.timezone} onChange={(e) => set("timezone", e.target.value)} />
        </Field>
        <Field label="Escalation window (minutes)" hint="Unacknowledged alerts escalate after this" error={errors.ack_window_mins}>
          <input
            className={inputClass}
            type="number"
            min={1}
            max={120}
            value={draft.ack_window_mins}
            onChange={(e) => set("ack_window_mins", e.target.value)}
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Privacy law" hint="Patient consent is recorded under this law">
            <select className={inputClass} value={draft.privacy_law} onChange={(e) => set("privacy_law", e.target.value as PrivacyLaw)}>
              {options.privacy_laws.map((law) => (
                <option key={law} value={law}>{PRIVACY_LAW_CHOICES[law] ?? law}</option>
              ))}
            </select>
          </Field>
        </div>
      </div>
      <datalist id="timezones">
        {options.timezones.map((tz) => (
          <option key={tz} value={tz} />
        ))}
      </datalist>

      <fieldset className="flex flex-col gap-1.5">
        <legend className="font-label-md text-on-surface mb-1">Procedures offered</legend>
        {options.procedures.map((p) => (
          <label key={p.procedure_code} className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="mt-1"
              checked={draft.procedure_codes.includes(p.procedure_code)}
              onChange={() => toggleProcedure(p.procedure_code)}
            />
            <span className="font-body-md text-on-surface">
              {p.procedure_name}{" "}
              <span className="text-on-surface-variant font-body-sm">
                {p.approved_version ? `· ruleset ${p.approved_version}` : "· no approved ruleset yet, so no one can be enrolled"}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <label className="flex items-start gap-2 cursor-pointer">
        <input type="checkbox" className="mt-1" checked={draft.is_active} onChange={(e) => set("is_active", e.target.checked)} />
        <span className="font-body-md text-on-surface">
          Active
          <span className="block font-body-sm text-on-surface-variant">
            Clinicians at an inactive hospital are signed out and cannot sign in.
          </span>
        </span>
      </label>

      {error && <ErrorBanner message={error} />}
      <div className="flex items-center justify-end gap-space-sm">
        {saved && <span role="status" className="font-body-sm text-primary">Saved</span>}
        <button type="button" onClick={onCancel} className="px-4 py-2 rounded-lg font-label-md text-on-surface-variant hover:bg-surface-bright cursor-pointer">
          {isNew ? "Cancel" : "Close"}
        </button>
        <button type="submit" disabled={saving} className={primaryButtonClass}>
          {saving ? "Saving…" : isNew ? "Add hospital" : "Save changes"}
        </button>
      </div>
    </form>
  );
}

function Accounts({ hospital, onChanged }: { hospital: PlatformHospitalDetail; onChanged: (h: PlatformHospitalDetail) => void }) {
  const blank: AccountInput = { email: "", full_name: "", role: "superadmin", password: "" };
  const [account, setAccount] = useState<AccountInput>(blank);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!account.full_name.trim() || !account.email.includes("@") || account.password.length < 12) {
      setError("Enter a name, an email address and a temporary password of at least 12 characters.");
      return;
    }
    setBusy(true);
    try {
      onChanged(await createHospitalAccount(hospital.hospital_id, account));
      setAccount(blank);
      setAdding(false);
    } catch (err) {
      setError(message(err, "Could not add the account."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-space-sm">
      {hospital.accounts.length === 0 ? (
        <Notice icon="person_add">
          Nobody can sign in to this hospital yet. Add its first superadmin, who can then add the other clinicians.
        </Notice>
      ) : (
        <ul className="flex flex-col divide-y divide-outline-variant/20">
          {hospital.accounts.map((a) => (
            <li key={a.admin_user_id} className="py-2 flex items-center justify-between gap-space-sm">
              <span className="min-w-0">
                <span className="font-label-md text-on-surface block truncate">{a.full_name}</span>
                <span className="font-body-sm text-on-surface-variant block truncate">{a.email}</span>
              </span>
              <span className="flex items-center gap-1.5 shrink-0">
                <StatusPill status={a.role === "superadmin" ? "approved" : "draft"} label={a.role === "superadmin" ? "Superadmin" : "Clinician"} />
                {!a.is_active && <StatusPill status="inactive" />}
              </span>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <form onSubmit={add} noValidate className="flex flex-col gap-space-sm border-t border-outline-variant/20 pt-space-sm">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-sm">
            <Field label="Full name">
              <input className={inputClass} value={account.full_name} onChange={(e) => setAccount({ ...account, full_name: e.target.value })} />
            </Field>
            <Field label="Email">
              <input className={inputClass} type="email" value={account.email} onChange={(e) => setAccount({ ...account, email: e.target.value })} />
            </Field>
            <Field label="Role">
              <select
                className={inputClass}
                value={account.role}
                onChange={(e) => setAccount({ ...account, role: e.target.value as AccountInput["role"] })}
              >
                <option value="superadmin">Superadmin (manages clinicians and settings)</option>
                <option value="admin">Clinician</option>
              </select>
            </Field>
            <Field label="Temporary password" hint="At least 12 characters; share it securely">
              <input
                className={inputClass}
                type="password"
                autoComplete="new-password"
                value={account.password}
                onChange={(e) => setAccount({ ...account, password: e.target.value })}
              />
            </Field>
          </div>
          {error && <ErrorBanner message={error} />}
          <div className="flex justify-end gap-space-sm">
            <button type="button" onClick={() => setAdding(false)} className="px-4 py-2 rounded-lg font-label-md text-on-surface-variant hover:bg-surface-bright cursor-pointer">
              Cancel
            </button>
            <button type="submit" disabled={busy} className={primaryButtonClass}>{busy ? "Adding…" : "Add account"}</button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setAdding(true)} className={`${secondaryButtonClass} w-fit`}>
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">person_add</span>
          Add account
        </button>
      )}
    </div>
  );
}

export default function HospitalsAdminPage() {
  const options = useApiData(fetchPlatformOptions);
  const hospitals = useApiData(fetchHospitals);
  // null: nothing open; "new": the add form; a detail: that hospital's editor
  const [editing, setEditing] = useState<PlatformHospitalDetail | "new" | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

  const open = async (hospitalId: number) => {
    setOpenError(null);
    try {
      setEditing(await fetchHospital(hospitalId));
    } catch (err) {
      setOpenError(message(err, "Could not open the hospital."));
    }
  };

  const saved = (detail: PlatformHospitalDetail) => {
    setEditing(detail);
    hospitals.reload();
  };

  const selectedId = editing && editing !== "new" ? editing.hospital_id : null;

  return (
    <PageBody>
      <div className="flex items-center justify-between gap-space-md flex-wrap">
        <p className="font-body-md text-on-surface-variant max-w-2xl">
          Every hospital on the platform. Patients are shown only as counts: the admin area cannot open a patient record.
        </p>
        <button type="button" className={primaryButtonClass} onClick={() => setEditing("new")}>
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">add</span>
          Add hospital
        </button>
      </div>

      {(options.error || hospitals.error || openError) && (
        <ErrorBanner
          message={options.error ?? hospitals.error ?? openError ?? ""}
          onRetry={() => {
            options.reload();
            hospitals.reload();
          }}
        />
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-space-lg items-start">
        <Card title="Hospitals">
          {!hospitals.data ? (
            <Loading />
          ) : (
            <div className="overflow-x-auto -mx-space-md">
              <table className="w-full text-left">
                <thead>
                  <tr className="font-label-sm uppercase tracking-wider text-on-surface-variant border-b border-outline-variant/30">
                    <th scope="col" className="px-space-md py-2">Hospital</th>
                    <th scope="col" className="px-space-md py-2">Procedures</th>
                    <th scope="col" className="px-space-md py-2 text-right">Accounts</th>
                    <th scope="col" className="px-space-md py-2 text-right">Patients</th>
                    <th scope="col" className="px-space-md py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/20">
                  {hospitals.data.map((h) => (
                    <tr
                      key={h.hospital_id}
                      className={`font-body-md ${selectedId === h.hospital_id ? "bg-surface-container-low" : "hover:bg-surface-bright"}`}
                    >
                      <td className="px-space-md py-2.5">
                        <button
                          type="button"
                          onClick={() => open(h.hospital_id)}
                          className="text-left font-label-md text-on-surface hover:text-primary hover:underline cursor-pointer"
                        >
                          {h.hospital_name}
                        </button>
                        <div className="font-body-sm text-on-surface-variant">
                          {h.hospital_code}
                          {h.city ? ` · ${h.city}` : ""} · {h.timezone}
                        </div>
                      </td>
                      <td className="px-space-md py-2.5 text-on-surface">{h.procedure_codes.join(", ") || "—"}</td>
                      <td className="px-space-md py-2.5 text-right tabular-nums">{h.account_count}</td>
                      <td className="px-space-md py-2.5 text-right tabular-nums">{h.active_patients}</td>
                      <td className="px-space-md py-2.5">
                        <StatusPill status={h.is_active ? "active" : "inactive"} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {editing === null ? (
          <Card>
            <p className="font-body-md text-on-surface-variant">Choose a hospital to edit it or manage its accounts, or add a new one.</p>
          </Card>
        ) : (
          <div className="flex flex-col gap-space-lg xl:sticky xl:top-20">
            <Card
              title={editing === "new" ? "Add a hospital" : editing.hospital_name}
              subtitle={editing === "new" ? undefined : `${editing.hospital_code} · added ${formatDate(editing.created_at)}`}
            >
              {options.data && (
                <HospitalForm
                  key={editing === "new" ? "new" : editing.hospital_id}
                  hospital={editing === "new" ? null : editing}
                  options={options.data}
                  onSaved={saved}
                  onCancel={() => setEditing(null)}
                />
              )}
            </Card>
            {editing !== "new" && (
              <Card title="Accounts" subtitle="Clinicians who can sign in to this hospital">
                <Accounts hospital={editing} onChanged={saved} />
              </Card>
            )}
          </div>
        )}
      </div>
    </PageBody>
  );
}
