"use client";

import { signOut } from "@/lib/session";

/** The signed-in user's name at the right of the top bar, with Sign out beneath it. */
export default function AccountBlock({ fullName }: { fullName: string }) {
  return (
    <div className="flex flex-col items-end leading-tight shrink-0">
      <span className="font-label-md text-on-surface hidden md:inline">{fullName}</span>
      <button
        type="button"
        onClick={signOut}
        className="inline-flex items-center gap-0.5 font-label-sm text-on-surface-variant hover:text-error cursor-pointer"
      >
        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">logout</span>
        Sign out
      </button>
    </div>
  );
}
