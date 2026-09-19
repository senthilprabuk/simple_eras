"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import { TierBadge } from "@/components/RiskQueueTable";
import { ErrorBanner, Loading, PageBody, PageHeader, SearchInput, Segmented, StatusPill, primaryButtonClass } from "@/components/ui";
import { fetchPatients, type EpisodeStatus } from "@/lib/clinicalApi";
import { LANGUAGE_NAMES, formatDate, formatDateTime } from "@/lib/format";
import { useApiData, useDebounced } from "@/lib/useApiData";

type Sort = "priority" | "recent" | "name";

export default function PatientsPage() {
  const [status, setStatus] = useState<EpisodeStatus | "all">("active");
  const [sort, setSort] = useState<Sort>("priority");
  const [search, setSearch] = useState("");
  const query = useDebounced(search);

  const load = useCallback(() => fetchPatients({ status, search: query, sort }), [status, query, sort]);
  const { data, error, loading, reload } = useApiData(load);

  return (
    <>
      <PageHeader
        title="Patients"
        actions={
          <Link href="/enrollment" className={primaryButtonClass}>
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">person_add</span>
            Enroll patient
          </Link>
        }
      />
      <PageBody>
        <div className="flex flex-wrap items-center gap-space-sm">
          <Segmented
            label="Monitoring status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "active", label: "Active" },
              { value: "completed", label: "Completed" },
              { value: "withdrawn", label: "Withdrawn" },
              { value: "all", label: "All" },
            ]}
          />
          <SearchInput value={search} onChange={setSearch} placeholder="Search name or MRN…" />
          <Segmented
            label="Sort"
            value={sort}
            onChange={setSort}
            options={[
              { value: "priority", label: "Most urgent" },
              { value: "recent", label: "Recently enrolled" },
              { value: "name", label: "Name" },
            ]}
          />
          {data && (
            <span className="font-body-sm text-on-surface-variant ml-auto">
              {data.total} patient{data.total === 1 ? "" : "s"}
              {data.total > data.items.length && `, showing the first ${data.items.length}`}
            </span>
          )}
        </div>

        {error && <ErrorBanner message={error} onRetry={reload} />}
        {!data && !error && <Loading label="Loading patients…" />}

        {data && (
          <section
            aria-label="Patients"
            className={`bg-surface-container-lowest rounded-xl border border-outline-variant/30 overflow-hidden shadow-sm transition-opacity ${
              loading ? "opacity-60" : ""
            }`}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left min-w-[900px]">
                <thead>
                  <tr className="bg-surface-bright/70 border-b border-outline-variant/30 text-on-surface-variant font-label-sm uppercase tracking-wider">
                    <th scope="col" className="py-3 px-space-md">Patient</th>
                    <th scope="col" className="py-3 px-space-md">Recovery</th>
                    <th scope="col" className="py-3 px-space-md">Last check-in</th>
                    <th scope="col" className="py-3 px-space-md">Adherence</th>
                    <th scope="col" className="py-3 px-space-md">Open alerts</th>
                    <th scope="col" className="py-3 px-space-md">Enrolled</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {data.items.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-space-xl text-center font-body-md text-on-surface-variant">
                        {query ? "No patients match this search." : "No patients with this status."}
                      </td>
                    </tr>
                  )}
                  {data.items.map((p) => {
                    const low = p.adherence_pct !== null && p.adherence_pct < 70;
                    return (
                      <tr key={p.episode_id} className="hover:bg-surface-bright/60 transition-colors">
                        <td className="py-3 px-space-md">
                          <Link href={`/patients/${p.episode_id}`} className="font-title-sm text-on-surface hover:text-primary hover:underline">
                            {p.patient_name}
                          </Link>
                          <div className="font-body-sm text-on-surface-variant">
                            MRN {p.mrn ?? "not recorded"} · {LANGUAGE_NAMES[p.language_code] ?? p.language_code}
                          </div>
                        </td>
                        <td className="py-3 px-space-md">
                          <div className="font-body-md text-on-surface">
                            POD {p.post_op_day} · {p.procedure_code}
                          </div>
                          <div className="flex items-center gap-1.5 font-body-sm text-on-surface-variant">
                            {p.status !== "active" && <StatusPill status={p.status} />}
                            until {formatDate(p.monitoring_ends_on)}
                          </div>
                        </td>
                        <td className="py-3 px-space-md font-body-md text-on-surface">
                          {p.last_check_in_at ? (
                            <>
                              POD {p.last_check_in_day}
                              <div className="font-body-sm text-on-surface-variant">{formatDateTime(p.last_check_in_at)}</div>
                            </>
                          ) : (
                            <span className="text-outline italic">None yet</span>
                          )}
                        </td>
                        <td className="py-3 px-space-md">
                          <div className={`font-body-md ${low ? "text-tertiary font-semibold" : "text-on-surface"}`}>
                            {p.adherence_pct === null ? "—" : `${p.adherence_pct.toFixed(0)}%`}
                            {low && <span className="sr-only"> (low)</span>}
                          </div>
                          <div className="font-body-sm text-on-surface-variant">
                            {p.check_in_days} of {p.expected_check_in_days} days
                          </div>
                        </td>
                        <td className="py-3 px-space-md">
                          {p.top_open_tier ? (
                            <div className="flex items-center gap-2">
                              <TierBadge tier={p.top_open_tier} />
                              {p.open_alerts > 1 && <span className="font-body-sm text-on-surface-variant">+{p.open_alerts - 1}</span>}
                            </div>
                          ) : (
                            <span className="font-body-sm text-on-surface-variant">None</span>
                          )}
                        </td>
                        <td className="py-3 px-space-md font-body-sm text-on-surface-variant">
                          {formatDate(p.enrolled_at)}
                          {p.enrolled_by_name && <div>by {p.enrolled_by_name}</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </PageBody>
    </>
  );
}
