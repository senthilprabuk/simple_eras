"use client";

import React, { useState, useEffect, useMemo } from "react";
import Sidebar from "@/components/Sidebar";
import TopHeader from "@/components/TopHeader";
import KpiMetrics from "@/components/KpiMetrics";
import QueueControls from "@/components/QueueControls";
import RiskQueueTable from "@/components/RiskQueueTable";
import TriageStatusBanner from "@/components/TriageStatusBanner";
import PatientDetailDrawer from "@/components/PatientDetailDrawer";
import { INITIAL_PATIENTS, PatientQueueItem } from "@/data/mockPatients";
import {
  fetchQueue,
  fetchKpis,
  acknowledgeAlert,
  mapQueueRowToPatientItem,
  KpiResponse,
} from "@/lib/api";

export default function DashboardPage() {
  const [patients, setPatients] = useState<PatientQueueItem[]>(INITIAL_PATIENTS);
  const [kpis, setKpis] = useState<KpiResponse | null>(null);
  const [isLive, setIsLive] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [currentTier, setCurrentTier] = useState<string>("all");
  const [currentPod, setCurrentPod] = useState<string>("all");
  const [selectedPatient, setSelectedPatient] = useState<PatientQueueItem | null>(null);

  // Load live data from FastAPI Backend on mount or refresh
  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const [queueRes, kpiRes] = await Promise.all([
        fetchQueue(),
        fetchKpis(),
      ]);

      if (queueRes?.items && queueRes.items.length > 0) {
        const mappedItems = queueRes.items.map(mapQueueRowToPatientItem);
        setPatients(mappedItems);
        setIsLive(true);
      }
      if (kpiRes) {
        setKpis(kpiRes);
      }
    } catch (err) {
      console.warn("Backend API unavailable, falling back to local demo state:", err);
      setIsLive(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  // Compute counts based on all active patients
  const counts = {
    emergency: patients.filter((p) => p.tier === "emergency").length,
    critical: patients.filter((p) => p.tier === "critical").length,
    review: patients.filter((p) => p.tier === "review").length,
    missed: patients.filter((p) => p.tier === "missed").length,
  };

  // Filtered patients for the table based on search, tier, and pod
  const filteredPatients = useMemo(() => {
    return patients.filter((patient) => {
      // 1. Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = patient.name.toLowerCase().includes(q);
        const matchesMrn = (patient.mrn || "").toLowerCase().includes(q);
        if (!matchesName && !matchesMrn) return false;
      }
      // 2. Tier Filter
      if (currentTier !== "all" && patient.tier !== currentTier) {
        return false;
      }
      // 3. Pod Filter
      if (currentPod === "poda" && patient.post_op_day % 2 === 0) {
        return false;
      }
      if (currentPod === "podb" && patient.post_op_day % 2 !== 0) {
        return false;
      }
      return true;
    });
  }, [patients, searchQuery, currentTier, currentPod]);

  const handleAcknowledgeAlert = async (alertId: string, patientId: string) => {
    try {
      if (isLive) {
        await acknowledgeAlert(alertId, "Acknowledged by Nurse Sarah Jenkins from workstation");
        // Refresh KPIs from backend
        fetchKpis().then(setKpis).catch(() => {});
      }
      setPatients((prev) =>
        prev.map((item) => {
          if (item.id === patientId) {
            return {
              ...item,
              acknowledged: true,
              acknowledged_text: "Ack by Nurse Sarah Jenkins (Just now)",
              action_type: "none",
            };
          }
          return item;
        })
      );
    } catch (err) {
      console.error("Failed to acknowledge alert:", err);
    }
  };

  const handleResolveAlert = async (patientId: string, outcome: string, note: string) => {
    const targetPatient = patients.find((p) => p.id === patientId);
    if (targetPatient?.alert_id && isLive) {
      try {
        await acknowledgeAlert(
          targetPatient.alert_id,
          note || `Resolved with outcome: ${outcome}`
        );
        fetchKpis().then(setKpis).catch(() => {});
      } catch (err) {
        console.error("Failed to resolve alert on backend:", err);
      }
    }

    setPatients((prev) =>
      prev.map((item) => {
        if (item.id === patientId) {
          return {
            ...item,
            acknowledged: true,
            acknowledged_text: `Resolved (${outcome.replace(/_/g, " ")})`,
            action_type: "none",
          };
        }
        return item;
      })
    );
  };

  return (
    <div className="min-h-screen bg-surface-bright text-on-surface">
      {/* Left Icon Rail Navigation */}
      <Sidebar />

      {/* Main Container with 72px left offset */}
      <div className="pl-[72px]">
        {/* Fixed Header with Search */}
        <TopHeader searchQuery={searchQuery} onSearchChange={setSearchQuery} />

        {/* Scrollable Dashboard View */}
        <main className="w-full pt-14 bg-surface-bright min-h-screen">
          <div className="max-w-7xl mx-auto px-space-xl py-space-lg">
            <div className="flex flex-col w-full gap-space-lg">
              {/* Connection Status Pill */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-label-sm text-[11px] font-medium ${
                    isLive 
                      ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20" 
                      : "bg-amber-500/10 text-amber-600 border border-amber-500/20"
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
                    {isLive ? "LIVE NEON POSTGRESQL (CBE-01)" : "OFFLINE DEMO MODE"}
                  </span>
                  {loading && (
                    <span className="font-label-sm text-[11px] text-on-surface-variant flex items-center gap-1">
                      <span className="material-symbols-outlined text-[13px] animate-spin">sync</span>
                      Syncing queue...
                    </span>
                  )}
                </div>

                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    className="text-label-sm text-primary hover:underline cursor-pointer flex items-center gap-1"
                  >
                    <span>Clear search ("{searchQuery}")</span>
                    <span className="material-symbols-outlined text-[14px]">close</span>
                  </button>
                )}
              </div>

              {/* Top 4 KPI Metrics */}
              <KpiMetrics kpis={kpis} />

              {/* Clinical Queue Section Header & Controls */}
              <QueueControls
                currentPod={currentPod}
                onSelectPod={setCurrentPod}
                currentTier={currentTier}
                onSelectTier={setCurrentTier}
                counts={counts}
              />

              {/* Main Prioritized Clinical Queue Table */}
              <RiskQueueTable
                patients={filteredPatients}
                onSelectPatient={(p) => setSelectedPatient(p)}
                onAcknowledgeAlert={handleAcknowledgeAlert}
              />

              {/* Automated ERAS Triage Routine Status Banner */}
              <TriageStatusBanner
                onTriggerSweep={loadDashboardData}
                normalCount={6}
                totalEnrolled={kpis?.active_patients || 13}
              />
            </div>
          </div>
        </main>
      </div>

      {/* Patient Trajectory & Alert Resolution Drawer */}
      <PatientDetailDrawer
        patient={selectedPatient}
        onClose={() => setSelectedPatient(null)}
        onResolveAlert={handleResolveAlert}
      />
    </div>
  );
}
