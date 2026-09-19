"use client";

import React from "react";
import { useSession } from "@/components/SessionContext";

/** Fixed top bar matching the dashboard's, for every screen other than the dashboard. */
export function PageHeader({ title, actions }: { title: string; actions?: React.ReactNode }) {
  const session = useSession();
  return (
    <header className="fixed top-0 left-[72px] right-0 h-14 bg-surface-container-lowest border-b border-outline-variant/30 z-40 px-gutter flex items-center justify-between gap-space-md">
      <div className="flex items-center gap-space-sm min-w-0">
        <h1 className="font-headline-md text-on-surface tracking-tight">{title}</h1>
        <span className="h-4 w-px bg-outline-variant/40" aria-hidden="true" />
        <span className="flex items-center gap-1 font-label-md text-on-surface truncate">
          <span className="material-symbols-outlined text-[18px] text-primary" aria-hidden="true">domain</span>
          {session.hospitalName}
        </span>
      </div>
      <div className="flex items-center gap-space-md">
        {actions}
        <span className="font-label-md text-on-surface hidden md:inline">{session.fullName}</span>
      </div>
    </header>
  );
}

export function PageBody({ children }: { children: React.ReactNode }) {
  return (
    <main className="w-full pt-14 bg-surface-bright min-h-screen">
      <div className="max-w-7xl mx-auto px-space-xl py-space-lg flex flex-col gap-space-lg">{children}</div>
    </main>
  );
}

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`bg-surface-container-lowest border border-outline-variant/30 rounded-xl shadow-xs ${className}`}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-space-sm px-space-md pt-space-md">
          <div>
            {title && <h2 className="font-title-sm text-on-surface">{title}</h2>}
            {subtitle && <p className="font-body-sm text-on-surface-variant">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="p-space-md">{children}</div>
    </section>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-space-md px-space-md py-space-sm rounded-xl bg-error-container text-on-error-container border border-error/30"
    >
      <span className="font-body-md">{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="font-label-md px-3 py-1 rounded bg-surface-container-lowest text-error cursor-pointer"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function Notice({ icon = "info", children }: { icon?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-space-sm px-space-md py-space-sm rounded-xl bg-surface-container-low border border-outline-variant/40 text-on-surface">
      <span className="material-symbols-outlined text-[20px] text-primary" aria-hidden="true">{icon}</span>
      <p className="font-body-md">{children}</p>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="font-body-md text-on-surface-variant py-space-lg text-center">{label}</p>;
}

/** Headline figure. Proportional digits: tabular spacing looks loose at this size. */
export function StatTile({ label, value, detail, icon }: { label: string; value: string; detail?: string; icon: string }) {
  return (
    <div className="bg-surface-container-lowest p-space-md rounded-xl border border-outline-variant/30 shadow-xs">
      <div className="flex items-center justify-between mb-space-xs">
        <span className="font-label-sm text-on-surface-variant uppercase tracking-wider">{label}</span>
        <span className="material-symbols-outlined text-[18px] text-primary" aria-hidden="true">{icon}</span>
      </div>
      <span className="block text-[1.75rem] leading-8 font-semibold tracking-tight text-on-surface my-1">{value}</span>
      {detail && <p className="font-body-sm text-on-surface-variant">{detail}</p>}
    </div>
  );
}

/** A row of mutually exclusive filter buttons. */
export function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex items-center bg-surface-container-lowest border border-outline-variant/30 rounded p-0.5 font-label-sm text-on-surface-variant"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={`px-2.5 py-1 rounded cursor-pointer transition-colors ${
              active ? "bg-surface-container-low font-semibold text-primary" : "hover:text-on-surface"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="relative flex items-center">
      <span className="sr-only">{placeholder}</span>
      <span className="material-symbols-outlined absolute left-2.5 text-outline text-[18px]" aria-hidden="true">search</span>
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-64 pl-8 pr-3 py-1.5 bg-surface-container-lowest border border-outline-variant/40 rounded font-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary"
      />
    </label>
  );
}

const STATUS_STYLE: Record<string, string> = {
  active: "bg-primary/10 text-primary border-primary/30",
  approved: "bg-primary/10 text-primary border-primary/30",
  open: "bg-error-container text-on-error-container border-error/30",
  acknowledged: "bg-tertiary-fixed/60 text-on-tertiary-fixed border-tertiary-fixed-dim",
  resolved: "bg-surface-container-low text-on-surface-variant border-outline-variant/40",
  expired: "bg-surface-bright text-outline border-outline-variant/40",
  completed: "bg-surface-container-low text-on-surface-variant border-outline-variant/40",
  withdrawn: "bg-surface-bright text-outline border-outline-variant/40",
  draft: "bg-surface-bright text-on-surface-variant border-outline-variant/40",
  retired: "bg-surface-bright text-outline border-outline-variant/40",
  inactive: "bg-surface-bright text-outline border-outline-variant/40",
};

export function StatusPill({ status, label }: { status: string; label?: string }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border font-label-sm capitalize ${STATUS_STYLE[status] ?? STATUS_STYLE.draft}`}
    >
      {label ?? status}
    </span>
  );
}

export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <span className="font-body-sm text-error">{message}</span>;
}

export const inputClass =
  "w-full px-3 py-2 rounded-lg border border-outline-variant/60 bg-surface-bright font-body-md text-on-surface focus:outline-none focus:border-primary disabled:opacity-60";

export const primaryButtonClass =
  "inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-on-primary font-label-md cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed";

export const secondaryButtonClass =
  "inline-flex items-center justify-center gap-1.5 px-3 py-1.5 border border-primary text-primary font-label-md rounded hover:bg-surface-container-low cursor-pointer disabled:opacity-50";
