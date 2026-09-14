"use client";

import React, { useState } from "react";
import Sidebar from "@/components/Sidebar";
import TopHeader from "@/components/TopHeader";
import KpiMetrics from "@/components/KpiMetrics";
import QueueControls from "@/components/QueueControls";
import RiskQueueTable from "@/components/RiskQueueTable";
import TriageStatusBanner from "@/components/TriageStatusBanner";
import PatientDetailDrawer from "@/components/PatientDetailDrawer";
import { INITIAL_PATIENTS, PatientQueueItem } from "@/data/mockPatients";

export default function DashboardPage() {
  const [patients, setPatients] = useState<PatientQueueItem[]>(INITIAL_PATIENTS);
  const [currentPod, setCurrentPod] = useState<string>("all");
  const [selectedPatient, setSelectedPatient] = useState<PatientQueueItem | null>(null);

  // Compute counts
  const counts = {
    emergency: patients.filter((p) => p.tier === "emergency").length,
    critical: patients.filter((p) => p.tier === "critical").length,
    review: patients.filter((p) => p.tier === "review").length,
    missed: patients.filter((p) => p.tier === "missed").length,
  };

  const handleResolveAlert = (patientId: string, outcome: string, note: string) => {
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
        {/* Fixed Header */}
        <TopHeader />

        {/* Scrollable Dashboard View */}
        <main className="w-full pt-14 bg-surface-bright min-h-screen">
          <div className="max-w-7xl mx-auto px-space-xl py-space-lg">
            <div className="flex flex-col w-full gap-space-lg">
              {/* Top 4 KPI Metrics */}
              <KpiMetrics />

              {/* Clinical Queue Section Header & Controls */}
              <QueueControls
                currentPod={currentPod}
                onSelectPod={setCurrentPod}
                counts={counts}
              />

              {/* Main Prioritized Clinical Queue Table */}
              <RiskQueueTable
                patients={patients}
                onSelectPatient={(p) => setSelectedPatient(p)}
              />

              {/* Automated ERAS Triage Routine Status Banner */}
              <TriageStatusBanner />
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
