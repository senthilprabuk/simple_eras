"use client";

import React, { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import Sidebar from "@/components/Sidebar";
import TopHeader from "@/components/TopHeader";
import KpiMetrics from "@/components/KpiMetrics";
import QueueControls from "@/components/QueueControls";
import RiskQueueTable from "@/components/RiskQueueTable";
import TriageStatusBanner from "@/components/TriageStatusBanner";
import PatientDetailDrawer from "@/components/PatientDetailDrawer";
import {
  ApiError,
  Health,
  KpiResponse,
  QueueResponse,
  QueueRow,
  Tier,
  acknowledgeAlert,
  fetchHealth,
  fetchKpis,
  fetchQueue,
  redirectToLogin,
} from "@/lib/api";
import { clearSession, getSessionSnapshot, loadSession, subscribeSession } from "@/lib/session";
import { matchesSearch, tierCounts } from "@/lib/triage";

const REFRESH_MS = 30_000;
const CLOCK_MS = 15_000;

interface Snapshot {
  queue: QueueResponse;
  kpis: KpiResponse;
  fetchedAt: number;
}

function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

function without(record: Record<string, string>, key: string): Record<string, string> {
  const copy = { ...record };
  delete copy[key];
  return copy;
}

export default function DashboardPage() {
  const session = useSyncExternalStore(subscribeSession, getSessionSnapshot, () => null);
  const now = useNow(CLOCK_MS);

  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [tierFilter, setTierFilter] = useState<Tier | "all">("all");
  const [selected, setSelected] = useState<QueueRow | null>(null);
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const [queue, kpis] = await Promise.all([fetchQueue(), fetchKpis()]);
      setSnapshot({ queue, kpis, fetchedAt: Date.now() });
      setLoadError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setLoadError(errorMessage(err, "Could not load the queue."));
    }
  }, []);

  useEffect(() => {
    if (!loadSession()) {
      redirectToLogin();
      return;
    }
    load();
    fetchHealth().then(setHealth).catch(() => setHealth(null));
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleAcknowledge = async (row: QueueRow) => {
    setPending((p) => ({ ...p, [row.alert_id]: true }));
    setRowErrors((e) => without(e, row.alert_id));
    try {
      await acknowledgeAlert(row.alert_id);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) {
        setRowErrors((e) => ({ ...e, [row.alert_id]: errorMessage(err, "Could not acknowledge.") }));
      }
    }
    // Reload either way: on a conflict the row shows who got there first.
    await load();
    setPending((p) => ({ ...p, [row.alert_id]: false }));
  };

  const handleResolved = async () => {
    setSelected(null);
    await load();
  };

  const handleSignOut = () => {
    clearSession();
    // Full load so no patient data survives in memory after sign-out.
    window.location.replace("/login");
  };

  if (!session) {
    return (
      <div className="min-h-screen bg-surface-bright flex items-center justify-center">
        <span className="font-body-md text-on-surface-variant">Loading…</span>
      </div>
    );
  }

  const items = snapshot?.queue.items ?? [];
  const counts = tierCounts(items);
  const visible = items.filter(
    (row) => (tierFilter === "all" || row.tier === tierFilter) && matchesSearch(row, searchQuery),
  );
  // Keep the drawer on the freshest copy of its row; if the row has left the
  // queue (resolved elsewhere), keep the last copy so a half-typed note is not lost.
  const selectedRow = selected ? items.find((r) => r.alert_id === selected.alert_id) ?? selected : null;

  return (
    <div className="min-h-screen bg-surface-bright text-on-surface">
      <Sidebar fullName={session.fullName} role={session.role} onSignOut={handleSignOut} />

      <div className="pl-[72px]">
        <TopHeader
          hospitalName={session.hospitalName}
          fullName={session.fullName}
          lastRefreshed={snapshot?.fetchedAt ?? null}
          now={now}
          refreshing={refreshing}
          onRefresh={handleRefresh}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />

        <main className="w-full pt-14 bg-surface-bright min-h-screen">
          <div className="max-w-7xl mx-auto px-space-xl py-space-lg flex flex-col gap-space-lg">
            {loadError && (
              <div
                role="alert"
                className="flex items-center justify-between gap-space-md px-space-md py-space-sm rounded-xl bg-error-container text-on-error-container border border-error/30"
              >
                <span className="font-body-md">
                  {loadError}
                  {snapshot && " The figures below are from the last successful update."}
                </span>
                <button
                  type="button"
                  onClick={handleRefresh}
                  className="font-label-md px-3 py-1 rounded bg-surface-container-lowest text-error cursor-pointer"
                >
                  Retry
                </button>
              </div>
            )}

            <KpiMetrics kpis={snapshot?.kpis ?? null} />

            <QueueControls
              counts={counts}
              total={snapshot?.queue.total ?? 0}
              loaded={items.length}
              tierFilter={tierFilter}
              onTierFilter={setTierFilter}
            />

            {snapshot === null ? (
              <p className="font-body-md text-on-surface-variant py-space-xl text-center">
                {loadError ? "The queue could not be loaded." : "Loading the queue…"}
              </p>
            ) : (
              <RiskQueueTable
                rows={visible}
                emptyMessage={
                  items.length === 0
                    ? "No unresolved alerts. Every monitored patient is currently within their expected recovery."
                    : "No alerts match this search or filter."
                }
                now={now}
                fetchedAt={snapshot.fetchedAt}
                pending={pending}
                rowErrors={rowErrors}
                onAcknowledge={handleAcknowledge}
                onOpen={setSelected}
              />
            )}

            <TriageStatusBanner
              kpis={snapshot?.kpis ?? null}
              health={health}
              hospitalName={session.hospitalName}
            />
          </div>
        </main>
      </div>

      {selectedRow && (
        <PatientDetailDrawer
          key={selectedRow.alert_id}
          row={selectedRow}
          onClose={() => setSelected(null)}
          onResolved={handleResolved}
        />
      )}
    </div>
  );
}
