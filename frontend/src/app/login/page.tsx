"use client";

import React, { useEffect, useState } from "react";
import { ApiError, HospitalChoice, hospitalChoices, signIn } from "@/lib/api";
import { allowedPath, homePath, loadSession, type Session } from "@/lib/session";

/**
 * Only same-site paths, so a crafted link cannot bounce a clinician to another
 * origin, and only paths in the signed-in user's own area.
 */
function nextPath(session: Session): string {
  const next = new URLSearchParams(window.location.search).get("next");
  const sameSite = next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login");
  return sameSite && allowedPath(session, next) ? next : homePath(session);
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [choices, setChoices] = useState<HospitalChoice[] | null>(null);
  const [hospitalId, setHospitalId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const session = loadSession();
    if (session) window.location.replace(nextPath(session));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await signIn(email, password, hospitalId ?? undefined);
      window.location.replace(nextPath(session));
    } catch (err) {
      const offered = hospitalChoices(err);
      if (offered) {
        setChoices(offered);
        setHospitalId(null);
        setError("This account exists at more than one hospital. Choose which one to sign in to.");
      } else {
        setError(err instanceof ApiError ? err.message : "Sign-in failed. Try again.");
      }
      setBusy(false);
    }
  };

  const needsChoice = choices !== null && hospitalId === null;

  return (
    <main className="min-h-screen bg-surface-bright flex items-center justify-center px-space-md py-space-xl">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-space-sm mb-space-lg">
          <span className="w-10 h-10 rounded-xl bg-primary-container/20 border border-primary/30 flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px] text-primary">healing</span>
          </span>
          <div>
            <h1 className="font-headline-md text-on-surface">ERAS Remote Monitoring</h1>
            <p className="font-body-sm text-on-surface-variant">Sign in</p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-surface-container-lowest border border-outline-variant/40 rounded-xl p-space-lg flex flex-col gap-space-md shadow-sm"
        >
          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">Email</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setChoices(null);
                setHospitalId(null);
              }}
              className="px-3 py-2 rounded-lg border border-outline-variant/60 bg-surface-bright font-body-md text-on-surface focus:outline-none focus:border-primary"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">Password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="px-3 py-2 rounded-lg border border-outline-variant/60 bg-surface-bright font-body-md text-on-surface focus:outline-none focus:border-primary"
            />
          </label>

          {choices && (
            <fieldset className="flex flex-col gap-1.5">
              <legend className="font-label-md text-on-surface mb-1">Hospital</legend>
              {choices.map((h) => (
                <label
                  key={h.hospital_id}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg border border-outline-variant/50 cursor-pointer has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                >
                  <input
                    type="radio"
                    name="hospital"
                    checked={hospitalId === h.hospital_id}
                    onChange={() => setHospitalId(h.hospital_id)}
                  />
                  <span className="font-body-md text-on-surface">{h.hospital_name}</span>
                </label>
              ))}
            </fieldset>
          )}

          {error && (
            <p role="alert" className="font-body-sm text-on-error-container bg-error-container rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || needsChoice}
            className="h-11 rounded-lg bg-primary text-on-primary font-title-sm flex items-center justify-center gap-2 disabled:opacity-60 cursor-pointer"
          >
            {busy && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="font-body-sm text-on-surface-variant mt-space-md text-center">
          Signing in on a shared workstation? You are signed out when this tab closes.
        </p>
      </div>
    </main>
  );
}
