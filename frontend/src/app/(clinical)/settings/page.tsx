"use client";

import React, { useState } from "react";
import { useSession } from "@/components/SessionContext";
import {
  Card,
  ErrorBanner,
  FieldError,
  Loading,
  PageBody,
  PageHeader,
  StatusPill,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { changePassword, createClinician, fetchClinicians, updateClinician, type Clinician, type Role } from "@/lib/clinicalApi";
import { formatDate } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";

const MIN_PASSWORD = 12;

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const problem =
    next && next.length < MIN_PASSWORD ? `At least ${MIN_PASSWORD} characters.`
    : confirm && next !== confirm ? "The two new passwords do not match."
    : next && next === current ? "Choose a password different from the current one."
    : null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (problem || !current || !next) return;
    setSaving(true);
    setStatus(null);
    try {
      await changePassword(current, next);
      setStatus({ ok: true, message: "Password changed. Use the new one next time you sign in." });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setStatus({ ok: false, message: err instanceof ApiError ? err.message : "Could not change the password." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-space-sm max-w-sm">
      <label className="flex flex-col gap-1">
        <span className="font-label-md text-on-surface">Current password</span>
        <input className={inputClass} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-label-md text-on-surface">New password</span>
        <input className={inputClass} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-label-md text-on-surface">Repeat new password</span>
        <input className={inputClass} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </label>
      <FieldError message={problem ?? undefined} />
      {status && (
        <p role="status" className={`font-body-sm rounded-lg px-3 py-2 ${status.ok ? "bg-primary/10 text-primary" : "bg-error-container text-on-error-container"}`}>
          {status.message}
        </p>
      )}
      <button type="submit" className={`${primaryButtonClass} self-start`} disabled={saving || !!problem || !current || !next || next !== confirm}>
        {saving ? "Changing…" : "Change password"}
      </button>
    </form>
  );
}

function AddClinicianForm({ onAdded }: { onAdded: () => void }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const valid = fullName.trim() && email.includes("@") && password.length >= MIN_PASSWORD;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSaving(true);
    setError(null);
    try {
      await createClinician({ full_name: fullName.trim(), email: email.trim(), role, password });
      setFullName("");
      setEmail("");
      setPassword("");
      setRole("admin");
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the clinician.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-space-sm border-t border-outline-variant/30 pt-space-md mt-space-md">
      <h3 className="font-title-sm text-on-surface">Add a clinician</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-space-sm">
        <input className={inputClass} placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} aria-label="Full name" />
        <input className={inputClass} placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Email" />
        <select className={inputClass} value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Role">
          <option value="admin">Clinician</option>
          <option value="superadmin">Superadmin</option>
        </select>
        <input
          className={inputClass}
          placeholder={`Temporary password (${MIN_PASSWORD}+)`}
          type="text"
          autoComplete="off"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-label="Temporary password"
        />
      </div>
      <p className="font-body-sm text-on-surface-variant">Share the temporary password privately and ask them to change it after signing in.</p>
      {error && <ErrorBanner message={error} />}
      <button type="submit" className={`${primaryButtonClass} self-start`} disabled={saving || !valid}>
        {saving ? "Adding…" : "Add clinician"}
      </button>
    </form>
  );
}

function ClinicianRow({ clinician, isYou, canManage, onChanged }: { clinician: Clinician; isYou: boolean; canManage: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const change = async (changes: { role?: Role; is_active?: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      await updateClinician(clinician.admin_user_id, changes);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr className={clinician.is_active ? "" : "opacity-70"}>
      <td className="py-2.5 px-space-md">
        <div className="font-title-sm text-on-surface">
          {clinician.full_name} {isYou && <span className="font-body-sm text-on-surface-variant">(you)</span>}
        </div>
        <div className="font-body-sm text-on-surface-variant">{clinician.email}</div>
      </td>
      <td className="py-2.5 px-space-md font-body-md text-on-surface">{clinician.role === "superadmin" ? "Superadmin" : "Clinician"}</td>
      <td className="py-2.5 px-space-md"><StatusPill status={clinician.is_active ? "active" : "inactive"} /></td>
      <td className="py-2.5 px-space-md font-body-sm text-on-surface-variant">{formatDate(clinician.created_at)}</td>
      <td className="py-2.5 px-space-md">
        {canManage && !isYou && (
          <div className="flex flex-wrap gap-space-sm">
            <button type="button" className={secondaryButtonClass} disabled={busy} onClick={() => change({ is_active: !clinician.is_active })}>
              {clinician.is_active ? "Deactivate" : "Reactivate"}
            </button>
            <button
              type="button"
              className={secondaryButtonClass}
              disabled={busy}
              onClick={() => change({ role: clinician.role === "superadmin" ? "admin" : "superadmin" })}
            >
              {clinician.role === "superadmin" ? "Make clinician" : "Make superadmin"}
            </button>
          </div>
        )}
        {error && <p role="alert" className="font-body-sm text-error mt-1">{error}</p>}
      </td>
    </tr>
  );
}

export default function SettingsPage() {
  const session = useSession();
  const { data, error, reload } = useApiData(fetchClinicians);
  const canManage = session.role === "superadmin";
  const me = data?.find((c) => c.admin_user_id === session.adminUserId);

  return (
    <>
      <PageHeader title="Settings" />
      <PageBody>
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-space-lg items-start">
          <Card title="Your account">
            <dl className="flex flex-col gap-space-sm mb-space-lg">
              <div>
                <dt className="font-label-sm text-on-surface-variant uppercase tracking-wider">Name</dt>
                <dd className="font-body-md text-on-surface">{session.fullName}</dd>
              </div>
              <div>
                <dt className="font-label-sm text-on-surface-variant uppercase tracking-wider">Email</dt>
                <dd className="font-body-md text-on-surface">{me?.email ?? "…"}</dd>
              </div>
              <div>
                <dt className="font-label-sm text-on-surface-variant uppercase tracking-wider">Role</dt>
                <dd className="font-body-md text-on-surface">
                  {session.role === "superadmin" ? "Superadmin" : "Clinician"} at {session.hospitalName}
                </dd>
              </div>
            </dl>
            <PasswordForm />
          </Card>

          <Card
            title="Clinicians"
            subtitle={canManage ? "Add, deactivate or change the role of clinicians at this hospital." : "Only a superadmin can manage accounts."}
          >
            {error && <ErrorBanner message={error} onRetry={reload} />}
            {!data && !error && <Loading />}
            {data && (
              <div className="overflow-x-auto -mx-space-md">
                <table className="w-full text-left min-w-[640px]">
                  <thead>
                    <tr className="text-on-surface-variant font-label-sm uppercase tracking-wider border-b border-outline-variant/30">
                      <th scope="col" className="py-2 px-space-md">Clinician</th>
                      <th scope="col" className="py-2 px-space-md">Role</th>
                      <th scope="col" className="py-2 px-space-md">Status</th>
                      <th scope="col" className="py-2 px-space-md">Added</th>
                      <th scope="col" className="py-2 px-space-md"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {data.map((c) => (
                      <ClinicianRow
                        key={c.admin_user_id}
                        clinician={c}
                        isYou={c.admin_user_id === session.adminUserId}
                        canManage={canManage}
                        onChanged={reload}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {canManage && <AddClinicianForm onAdded={reload} />}
          </Card>
        </div>
      </PageBody>
    </>
  );
}
