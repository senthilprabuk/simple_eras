"use client";

import React, { useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import TrendChart from "@/components/charts/TrendChart";
import { Card, ErrorBanner, Loading, PageBody, PageHeader, StatusPill } from "@/components/ui";
import WhoToCall from "@/components/WhoToCall";
import { fetchEpisodeSummary, type EpisodeSummary } from "@/lib/api";
import { fetchPatientTimeline, type ObservationCell, type ObservationRow, type Trend } from "@/lib/clinicalApi";
import {
  CONSENT_LABELS,
  PRIVACY_LAW_NAMES,
  formatDate,
  formatDateTime,
  formatNumber,
  formatSexAge,
  formatShortDate,
  formatTimeWindow,
} from "@/lib/format";
import { useApiData } from "@/lib/useApiData";

const TREND_TITLES: Record<string, string> = {
  temp_c: "Temperature",
  pain: "Pain score",
  steps: "Steps walked",
};

const OBSERVATION_LABELS: Record<string, string> = {
  breathless: "Breathless",
  calf_pain: "Calf pain",
  drainage: "Wound leak",
  chills: "Chills",
};

function formatterFor(trend: Trend): (v: number) => string {
  if (trend.code === "steps") return (v) => formatNumber(Math.round(v));
  if (trend.unit === "C") return (v) => `${v.toFixed(trend.decimals)} °C`;
  if (trend.code === "pain") return (v) => `${v.toFixed(0)}/10`;
  return (v) => `${v.toFixed(trend.decimals)}${trend.unit ? ` ${trend.unit}` : ""}`;
}

function TrendCard({ trend }: { trend: Trend }) {
  const format = formatterFor(trend);
  const readings = trend.points.filter((p) => p.value !== null);
  const latest = readings[readings.length - 1];
  const title = TREND_TITLES[trend.code] ?? trend.name;
  const subtitle = [
    latest ? `Latest ${format(latest.value as number)} on POD ${latest.day}` : "No readings yet",
    trend.baseline !== null ? `discharge ${format(trend.baseline)}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <Card title={title} subtitle={subtitle}>
      <TrendChart
        data={trend.points.map((p) => ({
          key: String(p.day),
          label: `POD ${p.day} · ${formatShortDate(p.date)}`,
          shortLabel: `POD ${p.day}`,
          value: p.value,
          threshold: p.threshold,
        }))}
        format={format}
        thresholdDirection={trend.threshold_direction}
        ariaLabel={`${title} by post-operative day, ${readings.length} readings over ${trend.points.length} days${
          latest ? `, latest ${format(latest.value as number)}` : ""
        }.`}
        tableCaption={`${title} by day`}
        valueHeader={title}
      />
      <p className="font-body-sm text-on-surface-variant mt-space-sm">
        <span className="font-semibold">Scoring:</span> {trend.scoring_rule}. Gaps are days without a reading.
      </p>
    </Card>
  );
}

function ObservationValue({ cell, emergency }: { cell: ObservationCell; emergency: boolean }) {
  if (!cell.asked) return <span className="font-body-sm text-outline">Not asked</span>;
  if (cell.value === null) return <span className="font-body-sm text-outline italic">No answer</span>;
  if (!cell.value) return <span className="font-body-sm text-on-surface-variant">No</span>;
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-error-container text-on-error-container font-label-sm">
      <span className="material-symbols-outlined text-[14px]" aria-hidden="true">
        {emergency ? "e911_emergency" : "warning"}
      </span>
      Yes
    </span>
  );
}

function ObservationsCard({
  columns,
  rows,
}: {
  columns: { code: string; name: string; question_text: string | null; is_emergency: boolean }[];
  rows: ObservationRow[];
}) {
  const newestFirst = [...rows].reverse();
  const flagged = rows.filter((r) => columns.some((c) => r.values[c.code]?.value === true)).length;
  const checkedIn = rows.filter((r) => r.checked_in).length;

  return (
    <Card
      title="Critical observations"
      subtitle={`Red flags on ${flagged} of ${checkedIn} check-ins · newest first`}
    >
      <div className="max-h-[1080px] overflow-auto -mx-space-md">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-surface-container-lowest z-10">
            <tr className="border-b border-outline-variant/30 text-on-surface-variant font-label-sm uppercase tracking-wider">
              <th scope="col" className="px-space-md py-2">Day</th>
              {columns.map((c) => (
                <th key={c.code} scope="col" className="px-2 py-2" title={c.question_text ?? c.name}>
                  {OBSERVATION_LABELS[c.code] ?? c.name}
                  <span className="sr-only">: {c.question_text ?? c.name}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/20">
            {newestFirst.map((row) => (
              <tr key={row.day} className={row.checked_in ? "" : "bg-surface-bright/60"}>
                <th scope="row" className="px-space-md py-2 font-normal whitespace-nowrap">
                  <span className="block font-label-md text-on-surface">POD {row.day}</span>
                  <span className="block font-body-sm text-on-surface-variant">{formatShortDate(row.date)}</span>
                </th>
                {row.checked_in ? (
                  columns.map((c) => (
                    <td key={c.code} className="px-2 py-2">
                      <ObservationValue cell={row.values[c.code]} emergency={c.is_emergency} />
                    </td>
                  ))
                ) : (
                  <td colSpan={columns.length} className="px-2 py-2 font-body-sm text-outline italic">
                    No check-in received
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="font-body-sm text-on-surface-variant mt-space-sm">
        &ldquo;Not asked&rdquo; means the ruleset stops asking that question at this stage of recovery. A{" "}
        <span className="material-symbols-outlined text-[13px] align-middle" aria-hidden="true">e911_emergency</span>{" "}
        yes is an emergency symptom.
      </p>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-on-surface-variant">{label}</dt>
      <dd className="text-on-surface">{children}</dd>
    </>
  );
}

function PatientDetails({ summary }: { summary: EpisodeSummary }) {
  const body = summary.body;
  const notRecorded = <span className="text-on-surface-variant">Not recorded</span>;
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-space-lg items-start">
      <Card title="If the patient cannot be reached">
        <WhoToCall summary={summary} />
      </Card>

      <Card title="Body measurements" subtitle="Recorded at enrollment">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-space-md gap-y-1 font-body-md">
          <Row label="Height">{body.height_cm !== null ? `${body.height_cm} cm` : notRecorded}</Row>
          <Row label="Weight">{body.weight_kg !== null ? `${body.weight_kg} kg` : notRecorded}</Row>
          <Row label="BMI">
            {body.bmi === null ? (
              notRecorded
            ) : (
              <span className={body.bmi > 35 ? "text-error font-semibold" : undefined}>
                {body.bmi}
                {body.bmi > 35 ? " · above 35, higher risk of clots and wound problems" : ""}
              </span>
            )}
          </Row>
          <Row label="Blood pressure">
            {body.bp_systolic !== null && body.bp_diastolic !== null ? `${body.bp_systolic}/${body.bp_diastolic} mmHg` : notRecorded}
          </Row>
        </dl>
      </Card>

      <Card title="Monitoring and consent">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-space-md gap-y-1 font-body-md">
          <Row label="Check-in time">{formatTimeWindow(summary.checkin_window_start, summary.checkin_window_end)}</Row>
        </dl>
        {summary.consents.length === 0 ? (
          <p className="font-body-sm text-on-surface-variant mt-space-sm">No itemised consent recorded for this enrollment.</p>
        ) : (
          <ul className="flex flex-col gap-1 mt-space-sm">
            {summary.consents.map((c) => (
              <li key={c.code} className="flex items-start gap-1.5 font-body-md text-on-surface">
                <span
                  className={`material-symbols-outlined text-[18px] ${c.granted ? "text-primary" : "text-on-surface-variant"}`}
                  aria-hidden="true"
                >
                  {c.granted ? "check_circle" : "block"}
                </span>
                <span>
                  {CONSENT_LABELS[c.code] ?? c.code}: {c.granted ? "given" : "declined"}
                </span>
              </li>
            ))}
            <li className="font-body-sm text-on-surface-variant">
              Recorded {formatDateTime(summary.consents[0].recorded_at)} under{" "}
              {PRIVACY_LAW_NAMES[summary.consents[0].privacy_law] ?? summary.consents[0].privacy_law}
            </li>
          </ul>
        )}
      </Card>
    </div>
  );
}

export default function PatientRecordPage() {
  const { episodeId } = useParams<{ episodeId: string }>();
  const loadSummary = useCallback(() => fetchEpisodeSummary(episodeId), [episodeId]);
  const loadTimeline = useCallback(() => fetchPatientTimeline(episodeId), [episodeId]);
  const summary = useApiData(loadSummary);
  const timeline = useApiData(loadTimeline);

  const s = summary.data;
  const t = timeline.data;

  return (
    <>
      <PageHeader title="Patient record" />
      <PageBody>
        <Link href="/patients" className="font-label-md text-primary hover:underline w-fit flex items-center gap-1">
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">arrow_back</span>
          All patients
        </Link>

        {(summary.error || timeline.error) && (
          <ErrorBanner
            message={summary.error ?? timeline.error ?? ""}
            onRetry={() => {
              summary.reload();
              timeline.reload();
            }}
          />
        )}

        {s && (
          <section className="bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-space-md shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-space-md">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-headline-lg text-on-surface">{s.patient_name}</h2>
                <span className="font-label-sm px-2 py-0.5 rounded bg-surface-container-low text-primary font-semibold">
                  POD {s.post_op_day}
                </span>
                <StatusPill status={s.status} />
              </div>
              <p className="font-body-md text-on-surface-variant">
                MRN {s.mrn ?? "not recorded"}
                {formatSexAge(s.gender, s.age_years) ? ` · ${formatSexAge(s.gender, s.age_years)}` : ""} · {s.procedure_name} ·
                discharged {formatDate(s.discharge_date)} · ruleset {s.ruleset_version}
              </p>
              <p className="font-body-sm text-on-surface-variant">
                {s.latest_check_in
                  ? `Latest check-in: POD ${s.latest_check_in.day_after_discharge}, ${formatDateTime(s.latest_check_in.submitted_at)}`
                  : "No check-in received yet"}
              </p>
            </div>
            <div className="flex flex-wrap gap-space-sm">
              <a
                href={`tel:${s.phone_e164}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-primary text-primary font-label-md rounded hover:bg-surface-container-low"
              >
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">call</span>
                Call {s.phone_e164}
              </a>
              <Link
                href={`/alerts?episode=${episodeId}&patient=${encodeURIComponent(s.patient_name)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-outline-variant text-on-surface font-label-md rounded hover:bg-surface-container-low"
              >
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">crisis_alert</span>
                Alert history
              </Link>
            </div>
          </section>
        )}

        {s && <PatientDetails summary={s} />}

        {!t && !timeline.error && <Loading label="Loading the patient's record…" />}

        {t && (
          <div
            className={`grid grid-cols-1 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] gap-space-lg items-start transition-opacity ${
              timeline.loading ? "opacity-60" : ""
            }`}
          >
            <div className="flex flex-col gap-space-lg" aria-label="Trends">
              {t.trends.map((trend) => (
                <TrendCard key={trend.code} trend={trend} />
              ))}
            </div>
            <ObservationsCard columns={t.observation_columns} rows={t.observations} />
          </div>
        )}
      </PageBody>
    </>
  );
}
