"use client";

import React, { useCallback, useState } from "react";
import { Card, ErrorBanner, Loading, Notice, PageBody, PageHeader, StatusPill } from "@/components/ui";
import { fetchRuleset, fetchRulesets, type RulesetDetail, type RulesetParameter } from "@/lib/clinicalApi";
import { formatDate } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";

const SECTIONS: { key: string; title: string }[] = [
  { key: "readings", title: "Readings" },
  { key: "checks", title: "Symptom checks" },
  { key: "progress", title: "Recovery progress" },
];

/** When a question is asked (light) and when its answer counts (solid), across the monitoring period. */
function WindowBar({ p, span }: { p: RulesetParameter; span: number }) {
  const pct = (day: number) => `${(Math.min(day, span) / span) * 100}%`;
  const width = (from: number, to: number) => `${((Math.min(to, span) - from) / span) * 100}%`;
  const differs = p.collect_from_day !== p.score_from_day || p.collect_to_day !== p.score_to_day;
  return (
    <div>
      <div className="relative h-2 rounded-full bg-surface-container-high" aria-hidden="true">
        <span className="absolute top-0 h-2 rounded-full bg-primary/25" style={{ left: pct(p.collect_from_day), width: width(p.collect_from_day, p.collect_to_day) }} />
        <span className="absolute top-0.5 h-1 rounded-full bg-primary" style={{ left: pct(p.score_from_day), width: width(p.score_from_day, p.score_to_day) }} />
      </div>
      <div className={`font-body-sm mt-1 ${differs ? "text-on-surface" : "text-on-surface-variant"}`}>
        Asked days {p.collect_from_day}–{p.collect_to_day}
        {differs ? ` · scored ${p.score_from_day}–${p.score_to_day}` : " · scored throughout"}
      </div>
    </div>
  );
}

function RulesetView({ ruleset }: { ruleset: RulesetDetail }) {
  return (
    <div className="flex flex-col gap-space-lg">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-space-md">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-headline-md text-on-surface">
                {ruleset.procedure_name} · v{ruleset.version}
              </h2>
              <StatusPill status={ruleset.status} />
            </div>
            <p className="font-body-md text-on-surface-variant">
              {ruleset.approved_by
                ? `Approved by ${ruleset.approved_by}${ruleset.approved_at ? ` on ${formatDate(ruleset.approved_at)}` : ""}`
                : "Not approved"}
              {" · "}
              {ruleset.parameter_count} parameters · used by {ruleset.episodes_using} patient
              {ruleset.episodes_using === 1 ? "" : "s"} here
            </p>
          </div>
          <dl className="grid grid-cols-3 gap-space-md text-center">
            {[
              ["Review at", `${ruleset.review_at} pts`],
              ["Critical at", `${ruleset.critical_at} pts`],
              ["Max per measure", `${ruleset.max_points_per_parameter} pts`],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="font-label-sm text-on-surface-variant uppercase tracking-wider">{label}</dt>
                <dd className="font-title-sm text-on-surface">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </Card>

      <div className="flex items-center gap-space-md font-body-sm text-on-surface-variant">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-2 rounded-full bg-primary/25" aria-hidden="true" /> Asked
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-1 rounded-full bg-primary" aria-hidden="true" /> Scored
        </span>
        <span>Across days 0–{ruleset.observation_days} after discharge</span>
      </div>

      {SECTIONS.map((section) => {
        const params = ruleset.parameters.filter((p) => p.section === section.key);
        if (params.length === 0) return null;
        return (
          <section
            key={section.key}
            aria-label={section.title}
            className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 overflow-hidden shadow-sm"
          >
            <h3 className="px-space-md py-space-sm font-title-sm text-on-surface border-b border-outline-variant/30">{section.title}</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left min-w-[900px]">
                <thead>
                  <tr className="text-on-surface-variant font-label-sm uppercase tracking-wider border-b border-outline-variant/30">
                    <th scope="col" className="py-2 px-space-md w-[34%]">Question</th>
                    <th scope="col" className="py-2 px-space-md w-[26%]">Window</th>
                    <th scope="col" className="py-2 px-space-md w-[8%]">Weight</th>
                    <th scope="col" className="py-2 px-space-md">Scoring</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/20">
                  {params.map((p) => (
                    <tr key={p.code} className="align-top">
                      <td className="py-3 px-space-md">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-title-sm text-on-surface">{p.name}</span>
                          {p.is_emergency && (
                            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-error text-on-error font-label-sm">
                              <span className="material-symbols-outlined text-[13px]" aria-hidden="true">e911_emergency</span>
                              Emergency
                            </span>
                          )}
                          {p.is_mandatory && <span className="font-label-sm text-primary">Required</span>}
                        </div>
                        {p.question_text && <p className="font-body-sm text-on-surface-variant">&ldquo;{p.question_text}&rdquo;</p>}
                      </td>
                      <td className="py-3 px-space-md">
                        <WindowBar p={p} span={ruleset.observation_days} />
                      </td>
                      <td className="py-3 px-space-md font-body-md text-on-surface tabular-nums">{p.weight}</td>
                      <td className="py-3 px-space-md font-body-sm text-on-surface">{p.scoring_summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}

export default function RulesetsPage() {
  const list = useApiData(fetchRulesets);
  const [chosen, setChosen] = useState<number | null>(null);
  const selectedId = chosen ?? list.data?.find((r) => r.status === "approved")?.ruleset_id ?? list.data?.[0]?.ruleset_id ?? null;
  const loadDetail = useCallback(
    () => (selectedId === null ? Promise.resolve(null) : fetchRuleset(selectedId)),
    [selectedId],
  );
  const detail = useApiData(loadDetail);

  return (
    <>
      <PageHeader title="Rulesets" />
      <PageBody>
        <Notice>
          Rulesets are versioned. An approved ruleset is never edited in place, so every past alert stays explainable;
          a change means a new version and clinical approval.
        </Notice>

        {list.error && <ErrorBanner message={list.error} onRetry={list.reload} />}
        {!list.data && !list.error && <Loading label="Loading rulesets…" />}
        {list.data && list.data.length === 0 && (
          <p className="font-body-md text-on-surface-variant">This hospital does not offer any procedure with a ruleset.</p>
        )}

        {list.data && list.data.length > 1 && (
          <div role="tablist" aria-label="Rulesets" className="flex flex-wrap gap-space-sm">
            {list.data.map((r) => (
              <button
                key={r.ruleset_id}
                role="tab"
                aria-selected={r.ruleset_id === selectedId}
                onClick={() => setChosen(r.ruleset_id)}
                className={`px-3 py-1.5 rounded-lg border font-label-md cursor-pointer ${
                  r.ruleset_id === selectedId ? "border-primary bg-primary/10 text-primary" : "border-outline-variant/40 text-on-surface-variant"
                }`}
              >
                {r.procedure_code} v{r.version} · {r.status}
              </button>
            ))}
          </div>
        )}

        {detail.error && <ErrorBanner message={detail.error} onRetry={detail.reload} />}
        {detail.data && <RulesetView ruleset={detail.data} />}
      </PageBody>
    </>
  );
}
