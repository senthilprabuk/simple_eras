"use client";

import React, { useCallback, useState } from "react";
import BarList from "@/components/charts/BarList";
import StackedColumnChart from "@/components/charts/StackedColumnChart";
import TrendChart from "@/components/charts/TrendChart";
import { Card, ErrorBanner, Loading, PageBody, PageHeader, Segmented, StatTile } from "@/components/ui";
import { fetchReport } from "@/lib/clinicalApi";
import { OUTCOME_LABELS, formatPct, formatShortDate } from "@/lib/format";
import { formatDuration } from "@/lib/triage";
import { useApiData } from "@/lib/useApiData";

// An ordinal red ramp for severity, plus a neutral for missed check-ins.
// Validated with the dataviz palette checker: one hue, monotone lightness,
// light end >= 2.3:1 on white; missed vs review separate under CVD (ΔE 13).
const TIER_SERIES = [
  { key: "emergency", label: "Emergency", color: "#93000a" },
  { key: "critical", label: "Critical", color: "#de3730" },
  { key: "review", label: "Review", color: "#ff897d" },
  { key: "missed", label: "Missed check-in", color: "#6f787e" },
];

const pct = (v: number) => `${Math.round(v)}%`;

export default function ReportsPage() {
  const [days, setDays] = useState(30);
  const load = useCallback(() => fetchReport(days), [days]);
  const { data, error, loading, reload } = useApiData(load);

  return (
    <>
      <PageHeader title="Reports" />
      <PageBody>
        <div className="flex flex-wrap items-center gap-space-sm">
          <Segmented
            label="Period"
            value={days}
            onChange={setDays}
            options={[
              { value: 30, label: "30 days" },
              { value: 60, label: "60 days" },
              { value: 90, label: "90 days" },
              { value: 180, label: "180 days" },
            ]}
          />
          {data && (
            <span className="font-body-sm text-on-surface-variant">
              Weeks start on Monday in the hospital&apos;s timezone · SLA {formatDuration(data.ack_window_secs)}
            </span>
          )}
        </div>

        {error && <ErrorBanner message={error} onRetry={reload} />}
        {!data && !error && <Loading label="Loading report…" />}

        {data && (
          <div className={`flex flex-col gap-space-lg transition-opacity ${loading ? "opacity-60" : ""}`}>
            <section aria-label="Summary" className="grid grid-cols-2 lg:grid-cols-5 gap-gutter">
              <StatTile label="Alerts raised" value={String(data.summary.alerts_raised)} icon="notification_important" />
              <StatTile
                label="Acknowledged in time"
                value={formatPct(data.summary.ack_compliance_pct)}
                detail={data.summary.ack_compliance_pct === null ? "No alerts came due" : `Within ${formatDuration(data.ack_window_secs)}`}
                icon="timer"
              />
              <StatTile
                label="Median time to acknowledge"
                value={data.summary.median_ack_secs === null ? "—" : formatDuration(data.summary.median_ack_secs)}
                icon="avg_pace"
              />
              <StatTile label="Check-in adherence" value={formatPct(data.summary.adherence_pct)} detail="Days with a check-in" icon="fact_check" />
              <StatTile label="Escalated" value={String(data.summary.escalated)} detail="Unacknowledged past the SLA" icon="campaign" />
            </section>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg items-start">
              <Card title="Alerts raised per week" subtitle="By tier, most severe at the base">
                <StackedColumnChart
                  series={TIER_SERIES}
                  rows={data.alerts_by_week.map((w) => ({ key: w.week_start, label: formatShortDate(w.week_start), values: w.counts }))}
                  ariaLabel={`Alerts raised per week over the last ${days} days, stacked by tier`}
                  tableCaption="Alerts raised per week by tier"
                />
              </Card>

              <Card title="Acknowledged within the SLA" subtitle="Share of alerts that came due each week; gaps are weeks with none">
                <TrendChart
                  data={data.ack_by_week.map((w) => ({
                    key: w.week_start,
                    label: `Week of ${formatShortDate(w.week_start)} · ${w.met} of ${w.decided}`,
                    shortLabel: formatShortDate(w.week_start),
                    value: w.pct,
                  }))}
                  domain={[0, 100]}
                  format={pct}
                  emptyLabel="No alerts came due in this period"
                  ariaLabel={`Weekly share of alerts acknowledged within the SLA, overall ${formatPct(data.summary.ack_compliance_pct)}`}
                  tableCaption="Acknowledged within the SLA by week"
                  valueHeader="Acknowledged in time"
                />
              </Card>

              <Card title="Daily check-in adherence" subtitle="Patients who checked in, of those expected to that day">
                <TrendChart
                  data={data.adherence_by_day.map((d) => ({
                    key: d.date,
                    label: `${formatShortDate(d.date)} · ${d.submitted} of ${d.expected}`,
                    shortLabel: formatShortDate(d.date),
                    value: d.pct,
                  }))}
                  domain={[0, 100]}
                  format={pct}
                  emptyLabel="No patients were being monitored"
                  ariaLabel={`Daily check-in adherence, overall ${formatPct(data.summary.adherence_pct)}`}
                  tableCaption="Daily check-in adherence"
                  valueHeader="Adherence"
                />
              </Card>

              <Card title="Outcomes of resolved alerts" subtitle={`Alerts resolved in the last ${days} days`}>
                <BarList
                  unit="resolved alerts by outcome"
                  items={Object.entries(data.outcomes).map(([key, value]) => ({ label: OUTCOME_LABELS[key] ?? key, value }))}
                />
              </Card>
            </div>
          </div>
        )}
      </PageBody>
    </>
  );
}
