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
import {
  changePassword,
  createClinician,
  fetchClinicians,
  updateClinician,
  fetchWhatsAppAccount,
  saveWhatsAppAccount,
  disconnectWhatsAppAccount,
  sendTestWhatsAppMessage,
  type Clinician,
  type Role,
  type WhatsAppAccount,
} from "@/lib/clinicalApi";
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

        <WhatsAppAccountSection />
      </PageBody>
    </>
  );
}

function WhatsAppAccountSection() {
  const session = useSession();
  const canManage = session.role === "superadmin" || session.role === "admin";
  const { data: account, error, reload } = useApiData(fetchWhatsAppAccount);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    displayPhoneNumber: "",
    displayName: "",
    phoneNumberId: "",
    wabaId: "",
    accessToken: "",
    verifyToken: "eras_stmarys_verify_2026",
    metaAppId: "",
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Test send state
  const [showTest, setShowTest] = useState(false);
  const [testPhone, setTestPhone] = useState("");
  const [testSending, setTestSending] = useState(false);
  const [testStatus, setTestStatus] = useState<{ ok: boolean; message: string } | null>(null);

  const startEdit = () => {
    if (account) {
      setForm({
        displayPhoneNumber: account.display_phone_number,
        displayName: account.display_name,
        phoneNumberId: account.phone_number_id,
        wabaId: account.waba_id,
        accessToken: "",
        verifyToken: account.verify_token,
        metaAppId: account.meta_app_id ?? "",
      });
    } else {
      setForm({
        displayPhoneNumber: "+91 98765 43210",
        displayName: "St. Mary's Orthopedic Helpline",
        phoneNumberId: "",
        wabaId: "",
        accessToken: "",
        verifyToken: "eras_stmarys_verify_2026",
        metaAppId: "",
      });
    }
    setSaveError(null);
    setEditing(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.phoneNumberId.trim() || !form.wabaId.trim() || (!account && !form.accessToken.trim())) {
      setSaveError("Phone Number ID, WABA ID, and Access Token are required.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await saveWhatsAppAccount({
        display_phone_number: form.displayPhoneNumber.trim() || undefined,
        display_name: form.displayName.trim() || undefined,
        phone_number_id: form.phoneNumberId.trim(),
        waba_id: form.wabaId.trim(),
        access_token: form.accessToken.trim() || undefined,
        verify_token: form.verifyToken.trim(),
        meta_app_id: form.metaAppId.trim() || undefined,
      });
      setEditing(false);
      reload();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Failed to connect WhatsApp account");
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect this WhatsApp number? Automated reminders will be paused.")) return;
    try {
      await disconnectWhatsAppAccount();
      reload();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to disconnect WhatsApp number");
    }
  };

  const handleCopyWebhook = () => {
    if (!account) return;
    navigator.clipboard.writeText(account.webhook_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testPhone.trim()) return;
    setTestSending(true);
    setTestStatus(null);
    try {
      const res = await sendTestWhatsAppMessage(testPhone.trim());
      setTestStatus({
        ok: res.status === "sent",
        message: res.status === "sent" ? "Test message dispatched successfully!" : (res.error || "Queued"),
      });
    } catch (err) {
      setTestStatus({
        ok: false,
        message: err instanceof ApiError ? err.message : "Failed to send test message",
      });
    } finally {
      setTestSending(false);
    }
  };

  return (
    <Card
      title="WhatsApp Business Number & QR Code"
      subtitle="Connect the official hospital WhatsApp number to send daily recovery check-ins and receive patient updates."
    >
      {error && <ErrorBanner message={error} onRetry={reload} />}

      {!account && !editing && (
        <div className="flex flex-col md:flex-row items-center justify-between gap-space-lg p-space-lg rounded-xl bg-surface-container-low border border-outline-variant/30">
          <div className="flex flex-col gap-1">
            <h3 className="font-title-md font-semibold text-on-surface">No WhatsApp Business Number Connected</h3>
            <p className="font-body-md text-on-surface-variant">
              Connect your hospital&apos;s Meta WhatsApp Business Account to start dispatching automated daily check-ins.
            </p>
          </div>
          {canManage && (
            <button type="button" onClick={startEdit} className={primaryButtonClass}>
              Connect WhatsApp Number
            </button>
          )}
        </div>
      )}

      {account && !editing && (
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-space-xl p-space-lg rounded-xl bg-surface-container-low border border-outline-variant/40">
          {/* Left Details */}
          <div className="flex-1 flex flex-col gap-space-sm">
            <div className="flex items-center gap-2">
              <StatusPill
                status={account.health_status === "healthy" ? "active" : "inactive"}
                label={account.health_status === "healthy" ? "Active" : "Action Needed"}
              />
              <span className="font-label-lg font-bold text-on-surface">{account.display_name}</span>
            </div>

            <div className="my-1">
              <span className="font-label-sm uppercase tracking-wider text-on-surface-variant block font-semibold">Active WhatsApp Business Number</span>
              <span className="font-headline-sm text-primary font-mono font-bold tracking-tight">
                {account.display_phone_number}
              </span>
            </div>

            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-space-md gap-y-1 font-body-sm text-on-surface-variant">
              <dt className="font-semibold">Phone Number ID:</dt>
              <dd className="font-mono text-on-surface">{account.phone_number_id}</dd>
              <dt className="font-semibold">WABA ID:</dt>
              <dd className="font-mono text-on-surface">{account.waba_id}</dd>
              <dt className="font-semibold">Access Token:</dt>
              <dd className="font-mono text-on-surface">{account.access_token_masked}</dd>
            </dl>

            {/* Meta Webhook URL helper */}
            <div className="mt-space-sm p-space-sm rounded-lg bg-surface-bright border border-outline-variant/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
              <div className="min-w-0">
                <span className="font-label-sm text-on-surface-variant block uppercase tracking-wider">Meta Webhook URL</span>
                <code className="font-mono text-xs text-primary truncate block">{account.webhook_url}</code>
              </div>
              <button
                type="button"
                onClick={handleCopyWebhook}
                className="px-2.5 py-1 text-xs font-semibold rounded border border-outline-variant/50 bg-surface-container-lowest hover:border-primary text-primary transition-colors cursor-pointer shrink-0"
              >
                {copied ? "Copied!" : "Copy URL"}
              </button>
            </div>

            {/* Action buttons */}
            {canManage && (
              <div className="flex items-center gap-space-sm mt-space-sm">
                <button
                  type="button"
                  onClick={() => setShowTest(!showTest)}
                  className={secondaryButtonClass}
                >
                  {showTest ? "Close Test Form" : "Send Test WhatsApp Message"}
                </button>
                <button
                  type="button"
                  onClick={startEdit}
                  className="font-label-md text-primary hover:underline px-2 py-1"
                >
                  Edit Credentials
                </button>
                <button
                  type="button"
                  onClick={handleDisconnect}
                  className="font-label-md text-error hover:underline px-2 py-1 ml-auto"
                >
                  Disconnect Number
                </button>
              </div>
            )}

            {/* Test Send Form */}
            {showTest && (
              <form onSubmit={handleSendTest} className="mt-space-md p-space-md rounded-xl bg-surface-container-lowest border border-outline-variant/40 flex flex-col gap-space-sm">
                <h4 className="font-title-sm font-semibold text-on-surface">Send Test WhatsApp Message</h4>
                <p className="font-body-sm text-on-surface-variant">
                  Verify message dispatch from this hospital number directly to any patient or doctor phone.
                </p>
                <div className="flex gap-space-sm">
                  <input
                    type="tel"
                    placeholder="+91 98765 43210"
                    value={testPhone}
                    onChange={(e) => setTestPhone(e.target.value)}
                    className={`${inputClass} max-w-xs font-mono`}
                    required
                  />
                  <button type="submit" disabled={testSending || !testPhone.trim()} className={primaryButtonClass}>
                    {testSending ? "Sending…" : "Send Test"}
                  </button>
                </div>
                {testStatus && (
                  <p role="status" className={`font-body-sm rounded-lg px-3 py-2 ${testStatus.ok ? "bg-primary/10 text-primary" : "bg-error-container text-on-error-container"}`}>
                    {testStatus.message}
                  </p>
                )}
              </form>
            )}
          </div>

          {/* Right Scannable QR Code */}
          <div className="flex flex-col items-center gap-2 p-4 rounded-xl bg-white shadow-xs border border-outline-variant/30 shrink-0 self-center lg:self-auto">
            {account.qr_code_url ? (
              <img
                src={account.qr_code_url}
                alt="Hospital WhatsApp Click-to-Chat QR Code"
                className="w-40 h-40 object-contain rounded-md"
              />
            ) : (
              <div className="w-40 h-40 bg-surface-container-high flex items-center justify-center text-xs text-on-surface-variant">
                QR Unavailable
              </div>
            )}
            <div className="text-center">
              <span className="font-label-md font-bold text-slate-800 block">Scan to Chat</span>
              <span className="font-body-xs text-slate-500 block max-w-[170px]">
                Scan to open hospital chat on patient WhatsApp
              </span>
            </div>
            <a
              href={account.click_to_chat_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline font-semibold mt-1"
            >
              Open WhatsApp Link →
            </a>
          </div>
        </div>
      )}

      {editing && (
        <form onSubmit={handleSave} className="flex flex-col gap-space-md max-w-lg p-space-md rounded-xl bg-surface-container-low border border-outline-variant/40">
          <h3 className="font-title-md font-bold text-on-surface">
            {account ? "Update WhatsApp Business Credentials" : "Connect WhatsApp Business Account"}
          </h3>
          <p className="font-body-sm text-on-surface-variant">
            Enter your credentials from the Meta WhatsApp Cloud API portal. These will be verified automatically.
          </p>

          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">WhatsApp Business Phone Number</span>
            <input
              type="tel"
              placeholder="e.g. +91 98765 43210"
              value={form.displayPhoneNumber}
              onChange={(e) => setForm({ ...form, displayPhoneNumber: e.target.value })}
              className={`${inputClass} font-mono font-bold`}
              required
            />
            <span className="font-body-xs text-on-surface-variant">
              The official phone number displayed to patients and embedded into the Click-to-Chat QR code.
            </span>
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">Hospital Helpline / Clinic Name</span>
            <input
              type="text"
              placeholder="e.g. St. Mary's Orthopedic Helpline"
              value={form.displayName}
              onChange={(e) => setForm({ ...form, displayName: e.target.value })}
              className={inputClass}
              required
            />
            <span className="font-body-xs text-on-surface-variant">
              Displayed in patient chat pre-fill greetings and header banners.
            </span>
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">Phone Number ID</span>
            <input
              type="text"
              placeholder="e.g. 104239857123456"
              value={form.phoneNumberId}
              onChange={(e) => setForm({ ...form, phoneNumberId: e.target.value })}
              className={`${inputClass} font-mono`}
              required
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">WhatsApp Business Account ID (WABA ID)</span>
            <input
              type="text"
              placeholder="e.g. 108374829103948"
              value={form.wabaId}
              onChange={(e) => setForm({ ...form, wabaId: e.target.value })}
              className={`${inputClass} font-mono`}
              required
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">
              Permanent Access Token {account && <span className="font-normal text-on-surface-variant">(leave blank to keep stored token)</span>}
            </span>
            <input
              type="password"
              placeholder={account ? "••••••••" : "Meta System User Access Token"}
              value={form.accessToken}
              onChange={(e) => setForm({ ...form, accessToken: e.target.value })}
              className={`${inputClass} font-mono`}
              required={!account}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">Webhook Verify Token</span>
            <input
              type="text"
              placeholder="e.g. eras_stmarys_verify_2026"
              value={form.verifyToken}
              onChange={(e) => setForm({ ...form, verifyToken: e.target.value })}
              className={inputClass}
              required
            />
          </label>

          {saveError && <p role="alert" className="font-body-sm text-error">{saveError}</p>}

          <div className="flex items-center gap-space-sm mt-space-sm">
            <button type="submit" disabled={saving} className={primaryButtonClass}>
              {saving ? "Verifying with Meta…" : "Save & Verify"}
            </button>
            <button type="button" onClick={() => setEditing(false)} className={secondaryButtonClass}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </Card>
  );
}
