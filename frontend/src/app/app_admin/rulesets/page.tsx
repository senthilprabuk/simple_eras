"use client";

import React, { useState } from "react";
import {
  Card,
  ErrorBanner,
  FieldError,
  Loading,
  Notice,
  PageBody,
  StatusPill,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  bindingDraft,
  newBindingDraft,
  parseBinding,
  suggestVersion,
  type BindingDraft,
} from "@/lib/appAdmin";
import {
  approveDraft,
  discardDraft,
  fetchRuleset,
  fetchRulesets,
  removeBinding,
  saveBinding,
  startDraft,
  updateDraft,
  type AvailableParameter,
  type DisplaySection,
  type RulesetBinding,
  type RulesetDetail,
  type RulesetVersion,
} from "@/lib/appAdminApi";
import { DIRECTION_LABELS, type RuleDirection } from "@/lib/clinicalApi";
import { formatDate } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";

const message = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

const ghostButtonClass = "px-4 py-2 rounded-lg font-label-md text-on-surface-variant hover:bg-surface-bright cursor-pointer";

const RULE_HELP: Record<string, { example: string; explain: string }> = {
  numeric: {
    example: '{"bands": [[0, 37.5, 0], [37.5, 38.5, 1], [38.5, 99, 3]]}',
    explain:
      'Each band is [from, to, points]: "to" is exclusive and points run 0–3. The bands must agree with the direction above — the band worth 0 points sits at the safe end. Add "relative_to_baseline": true to score the rise from the discharge reading, or use "bands_by_day": {"0-3": [...], "4-84": [...]} when the bands change with recovery. Add "trends": [{"name": "pain_rising", "detector": "delta_vs_rolling_mean", "weight": 2, "window_days": 3, "min_observations": 3, "bands": [...]}] to watch how the reading moves as well as where it sits; the other detectors are reemergence, monotonic_rise and drop_from_personal_best.',
  },
  boolean: {
    example: '{"binary_score": 3, "emergency": true}',
    explain: 'Points for a "yes", 0–3; 3 on its own makes the check-in critical. "emergency": true skips scoring and raises an emergency.',
  },
  ordinal: {
    example: '{"milestone": {"14": "chair", "42": "car"}, "score": 2}',
    explain: "The level expected by each day after discharge; points when the patient is behind.",
  },
};

function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-label-md text-on-surface">{label}</span>
      {children}
      {hint && !error && <span className="font-body-sm text-on-surface-variant">{hint}</span>}
      <FieldError message={error} />
    </label>
  );
}

function days(from: number, to: number): string {
  return from === to ? `day ${from}` : `${from}–${to}`;
}

function BindingEditor({
  rulesetId,
  parameter,
  initial,
  observationDays,
  onSaved,
  onCancel,
}: {
  rulesetId: number;
  parameter: { parameter_code: string; parameter_name: string; parameter_type: string; option_codes?: string[] };
  initial: BindingDraft;
  observationDays: number;
  onSaved: (detail: RulesetDetail) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<BindingDraft>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof BindingDraft>(key: K, value: BindingDraft[K]) => setDraft({ ...draft, [key]: value });
  const help = RULE_HELP[parameter.parameter_type];

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);
    const parsed = parseBinding(draft, observationDays);
    if (parsed.errors) {
      setErrors(parsed.errors);
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      onSaved(await saveBinding(rulesetId, parameter.parameter_code, parsed.binding));
    } catch (err) {
      setServerError(message(err, "Could not save the measure."));
      setSaving(false);
    }
  };

  const dayInput = (key: "collect_from_day" | "collect_to_day" | "score_from_day" | "score_to_day", label: string) => (
    <Field label={label} error={errors[key]}>
      <input className={inputClass} type="number" min={0} max={observationDays} value={draft[key]} onChange={(e) => set(key, e.target.value)} />
    </Field>
  );

  return (
    <form onSubmit={save} noValidate className="flex flex-col gap-space-md p-space-md bg-surface-bright/60 border border-primary/30 rounded-xl">
      <h3 className="font-title-sm text-on-surface">
        {parameter.parameter_name} <span className="font-body-sm text-on-surface-variant">({parameter.parameter_code}, {parameter.parameter_type})</span>
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-space-md">
        <Field label="Section">
          <select className={inputClass} value={draft.display_section} onChange={(e) => set("display_section", e.target.value as DisplaySection)}>
            <option value="readings">Readings</option>
            <option value="checks">Checks</option>
            <option value="progress">Progress</option>
          </select>
        </Field>
        <Field label="Position" error={errors.display_order}>
          <input className={inputClass} type="number" min={1} max={99} value={draft.display_order} onChange={(e) => set("display_order", e.target.value)} />
        </Field>
        <Field label="Weight" hint="Multiplies the points" error={errors.weight}>
          <input className={inputClass} type="number" min={0} max={10} value={draft.weight} onChange={(e) => set("weight", e.target.value)} />
        </Field>
        <label className="flex items-center gap-2 cursor-pointer self-end pb-2">
          <input type="checkbox" checked={draft.is_mandatory} onChange={(e) => set("is_mandatory", e.target.checked)} />
          <span className="font-body-md text-on-surface">Must be answered</span>
        </label>
        {dayInput("collect_from_day", "Asked from day")}
        {dayInput("collect_to_day", "Asked until day")}
        {dayInput("score_from_day", "Scored from day")}
        {dayInput("score_to_day", "Scored until day")}
      </div>
      <Field label="Question for the patient" error={errors.question_text}>
        <input className={inputClass} value={draft.question_text} onChange={(e) => set("question_text", e.target.value)} />
      </Field>
      <Field label="What the nurse asks when this fires (optional)">
        <input className={inputClass} value={draft.nurse_script} onChange={(e) => set("nurse_script", e.target.value)} />
      </Field>
      {parameter.parameter_type === "numeric" && (
        <Field label="Which way it goes wrong" hint="A fever rises, oxygen falls. The engine watches the worrying side.">
          <select
            className={`${inputClass} max-w-sm`}
            value={draft.direction}
            onChange={(e) => set("direction", e.target.value as RuleDirection)}
          >
            {(Object.keys(DIRECTION_LABELS) as RuleDirection[]).map((value) => (
              <option key={value} value={value}>{DIRECTION_LABELS[value]}</option>
            ))}
          </select>
        </Field>
      )}
      <Field label="Scoring rule (JSON)" error={errors.scoring_config}>
        <textarea
          className={`${inputClass} font-mono text-[13px] leading-snug`}
          rows={Math.min(12, Math.max(4, draft.scoring_config.split("\n").length))}
          spellCheck={false}
          value={draft.scoring_config}
          onChange={(e) => set("scoring_config", e.target.value)}
        />
      </Field>
      {help && (
        <p className="font-body-sm text-on-surface-variant">
          {help.explain} Example: <code className="font-mono text-on-surface">{help.example}</code>
          {parameter.option_codes && parameter.option_codes.length > 0 && <> Levels: {parameter.option_codes.join(", ")}.</>}
        </p>
      )}
      {serverError && <ErrorBanner message={serverError} />}
      <div className="flex justify-end gap-space-sm">
        <button type="button" onClick={onCancel} className={ghostButtonClass}>Cancel</button>
        <button type="submit" disabled={saving} className={primaryButtonClass}>{saving ? "Saving…" : "Save measure"}</button>
      </div>
    </form>
  );
}

function Measures({ detail, onChanged }: { detail: RulesetDetail; onChanged: (d: RulesetDetail) => void }) {
  const isDraft = detail.status === "draft";
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState<AvailableParameter | null>(null);
  const [pick, setPick] = useState("");
  const [error, setError] = useState<string | null>(null);

  const saved = (d: RulesetDetail) => {
    setEditing(null);
    setAdding(null);
    setPick("");
    onChanged(d);
  };

  const remove = async (binding: RulesetBinding) => {
    setError(null);
    try {
      onChanged(await removeBinding(detail.ruleset_id, binding.parameter_code));
    } catch (err) {
      setError(message(err, "Could not remove the measure."));
    }
  };

  const nextOrder = Math.max(0, ...detail.bindings.map((b) => b.display_order)) + 1;

  return (
    <div className="flex flex-col gap-space-md">
      {error && <ErrorBanner message={error} />}
      <div className="overflow-x-auto -mx-space-md">
        <table className="w-full text-left">
          <thead>
            <tr className="font-label-sm uppercase tracking-wider text-on-surface-variant border-b border-outline-variant/30">
              <th scope="col" className="px-space-md py-2">#</th>
              <th scope="col" className="px-space-md py-2">Measure</th>
              <th scope="col" className="px-space-md py-2">Asked</th>
              <th scope="col" className="px-space-md py-2">Scored</th>
              <th scope="col" className="px-space-md py-2 text-right">Weight</th>
              <th scope="col" className="px-space-md py-2">Rule</th>
              {isDraft && <th scope="col" className="px-space-md py-2"><span className="sr-only">Actions</span></th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/20">
            {detail.bindings.map((b) => (
              <React.Fragment key={b.parameter_code}>
                <tr className="font-body-md align-top">
                  <td className="px-space-md py-2.5 tabular-nums text-on-surface-variant">{b.display_order}</td>
                  <td className="px-space-md py-2.5">
                    <span className="font-label-md text-on-surface">{b.parameter_name}</span>
                    <span className="block font-body-sm text-on-surface-variant capitalize">{b.display_section}</span>
                  </td>
                  <td className="px-space-md py-2.5 whitespace-nowrap">{days(b.collect_from_day, b.collect_to_day)}</td>
                  <td className="px-space-md py-2.5 whitespace-nowrap">{days(b.score_from_day, b.score_to_day)}</td>
                  <td className="px-space-md py-2.5 text-right tabular-nums">{b.weight}</td>
                  <td className="px-space-md py-2.5 font-body-sm text-on-surface">
                    {b.scoring_config.emergency === true && (
                      <span className="material-symbols-outlined text-[15px] text-error align-middle mr-1" aria-hidden="true">e911_emergency</span>
                    )}
                    {b.scoring_summary}
                    {b.direction && (
                      <span className="block font-body-sm text-on-surface-variant">{DIRECTION_LABELS[b.direction]}</span>
                    )}
                  </td>
                  {isDraft && (
                    <td className="px-space-md py-2.5 whitespace-nowrap text-right">
                      <button type="button" onClick={() => { setAdding(null); setEditing(b.parameter_code); }} className="font-label-md text-primary hover:underline cursor-pointer">
                        Edit<span className="sr-only"> {b.parameter_name}</span>
                      </button>
                      <button type="button" onClick={() => remove(b)} className="ml-space-sm font-label-md text-on-surface-variant hover:text-error cursor-pointer">
                        Remove<span className="sr-only"> {b.parameter_name}</span>
                      </button>
                    </td>
                  )}
                </tr>
                {editing === b.parameter_code && (
                  <tr>
                    <td colSpan={7} className="px-space-md py-space-sm">
                      <BindingEditor
                        rulesetId={detail.ruleset_id}
                        parameter={b}
                        initial={bindingDraft(b)}
                        observationDays={detail.observation_days}
                        onSaved={saved}
                        onCancel={() => setEditing(null)}
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {isDraft && !adding && detail.available_parameters.length > 0 && (
        <div className="flex items-end gap-space-sm flex-wrap">
          <Field label="Add a measure">
            <select className={`${inputClass} min-w-64`} value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Choose…</option>
              {detail.available_parameters.map((p) => (
                <option key={p.parameter_code} value={p.parameter_code}>
                  {p.parameter_name} ({p.parameter_type})
                </option>
              ))}
            </select>
          </Field>
          <button
            type="button"
            disabled={!pick}
            className={secondaryButtonClass}
            onClick={() => {
              setEditing(null);
              setAdding(detail.available_parameters.find((p) => p.parameter_code === pick) ?? null);
            }}
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">add</span>
            Add
          </button>
        </div>
      )}
      {adding && (
        <BindingEditor
          rulesetId={detail.ruleset_id}
          parameter={adding}
          initial={newBindingDraft(adding, detail.observation_days, nextOrder)}
          observationDays={detail.observation_days}
          onSaved={saved}
          onCancel={() => setAdding(null)}
        />
      )}
    </div>
  );
}

function StartDraft({ detail, versions, onChanged }: { detail: RulesetDetail; versions: RulesetVersion[]; onChanged: (d: RulesetDetail) => void }) {
  const [version, setVersion] = useState(() => suggestVersion(versions.map((v) => v.version)));
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const start = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      onChanged(await startDraft(detail.ruleset_id, version.trim(), notes.trim() || null));
    } catch (err) {
      setError(message(err, "Could not start the draft."));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={start} className="flex flex-col gap-space-sm border-t border-outline-variant/20 pt-space-md">
      <p className="font-body-md text-on-surface-variant">
        A published version never changes. To change the rules, start a draft from this one; patients already enrolled stay on the version they joined under.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-[10rem_minmax(0,1fr)] gap-space-sm">
        <Field label="New version">
          <input className={inputClass} value={version} onChange={(e) => setVersion(e.target.value)} />
        </Field>
        <Field label="What will change (optional)">
          <input className={inputClass} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
      {error && <ErrorBanner message={error} />}
      <button type="submit" disabled={busy || !version.trim()} className={`${primaryButtonClass} w-fit`}>
        <span className="material-symbols-outlined text-[16px]" aria-hidden="true">edit_document</span>
        {busy ? "Starting…" : `Start draft ${version.trim()} from ${detail.version}`}
      </button>
    </form>
  );
}

function DraftControls({
  detail,
  versions,
  onChanged,
  onDiscarded,
}: {
  detail: RulesetDetail;
  versions: RulesetVersion[];
  onChanged: (d: RulesetDetail) => void;
  onDiscarded: () => void;
}) {
  const [cutoffs, setCutoffs] = useState({
    review_at: String(detail.review_at),
    critical_at: String(detail.critical_at),
    max_points: String(detail.max_points_per_parameter),
    notes: detail.notes ?? "",
  });
  const [approver, setApprover] = useState("");
  const [confirming, setConfirming] = useState<"approve" | "discard" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const current = versions.find((v) => v.status === "approved");

  const run = async (action: () => Promise<void>, fallback: string) => {
    setError(null);
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError(message(err, fallback));
    } finally {
      setBusy(false);
    }
  };

  const saveCutoffs = (e: React.FormEvent) => {
    e.preventDefault();
    const review = Number(cutoffs.review_at);
    const critical = Number(cutoffs.critical_at);
    const maxPoints = Number(cutoffs.max_points);
    if (![review, critical, maxPoints].every(Number.isInteger) || review < 1 || critical <= review || maxPoints < 1) {
      setError("Use whole numbers, with the critical cut-off above the review cut-off.");
      return;
    }
    run(async () => {
      onChanged(await updateDraft(detail.ruleset_id, {
        review_at: review, critical_at: critical, max_points_per_parameter: maxPoints, notes: cutoffs.notes.trim() || null,
      }));
    }, "Could not save the cut-offs.");
  };

  return (
    <div className="flex flex-col gap-space-md border-t border-outline-variant/20 pt-space-md">
      <form onSubmit={saveCutoffs} className="flex flex-col gap-space-sm">
        <div className="grid grid-cols-3 gap-space-sm">
          <Field label="Review at (points)">
            <input className={inputClass} type="number" min={1} value={cutoffs.review_at} onChange={(e) => setCutoffs({ ...cutoffs, review_at: e.target.value })} />
          </Field>
          <Field label="Critical at (points)">
            <input className={inputClass} type="number" min={2} value={cutoffs.critical_at} onChange={(e) => setCutoffs({ ...cutoffs, critical_at: e.target.value })} />
          </Field>
          <Field label="Cap per measure">
            <input className={inputClass} type="number" min={1} value={cutoffs.max_points} onChange={(e) => setCutoffs({ ...cutoffs, max_points: e.target.value })} />
          </Field>
        </div>
        <Field label="What changes in this version (optional)">
          <input className={inputClass} value={cutoffs.notes} onChange={(e) => setCutoffs({ ...cutoffs, notes: e.target.value })} />
        </Field>
        <button type="submit" disabled={busy} className={`${secondaryButtonClass} w-fit`}>Save cut-offs</button>
      </form>

      <div className="flex flex-col gap-space-sm border-t border-outline-variant/20 pt-space-md">
        <Field label="Clinical approver" hint="The clinician who signed off these rules">
          <input className={`${inputClass} max-w-sm`} value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="e.g. Dr. K. Mehta" />
        </Field>
        {confirming === "approve" ? (
          <div role="alert" className="flex flex-col gap-space-sm p-space-md rounded-xl border border-primary/40 bg-primary/5">
            <p className="font-body-md text-on-surface">
              New {detail.procedure_name.toLowerCase()} enrollments will be scored by {detail.version}.
              {current
                ? ` ${current.version} will be retired; the ${current.active_episodes} patient${current.active_episodes === 1 ? "" : "s"} on it stay on it.`
                : ""}
            </p>
            <div className="flex gap-space-sm">
              <button
                type="button"
                disabled={busy}
                className={primaryButtonClass}
                onClick={() => run(async () => onChanged(await approveDraft(detail.ruleset_id, approver.trim())), "Could not approve the draft.")}
              >
                {busy ? "Approving…" : `Approve ${detail.version}`}
              </button>
              <button type="button" onClick={() => setConfirming(null)} className={ghostButtonClass}>Cancel</button>
            </div>
          </div>
        ) : confirming === "discard" ? (
          <div role="alert" className="flex flex-col gap-space-sm p-space-md rounded-xl border border-error/40 bg-error-container/40">
            <p className="font-body-md text-on-surface">Discard draft {detail.version} and every change in it?</p>
            <div className="flex gap-space-sm">
              <button
                type="button"
                disabled={busy}
                className="px-4 py-2 rounded-lg bg-error text-on-error font-label-md cursor-pointer disabled:opacity-50"
                onClick={() => run(async () => { await discardDraft(detail.ruleset_id); onDiscarded(); }, "Could not discard the draft.")}
              >
                Discard draft
              </button>
              <button type="button" onClick={() => setConfirming(null)} className={ghostButtonClass}>Keep it</button>
            </div>
          </div>
        ) : (
          <div className="flex gap-space-sm flex-wrap">
            <button
              type="button"
              disabled={!approver.trim() || detail.bindings.length === 0}
              onClick={() => setConfirming("approve")}
              className={primaryButtonClass}
            >
              <span className="material-symbols-outlined text-[16px]" aria-hidden="true">verified</span>
              Approve and publish
            </button>
            <button type="button" onClick={() => setConfirming("discard")} className={ghostButtonClass}>Discard draft</button>
          </div>
        )}
      </div>
      {error && <ErrorBanner message={error} />}
    </div>
  );
}

function RulesetPanel({
  detail,
  versions,
  onChanged,
  onDiscarded,
}: {
  detail: RulesetDetail;
  versions: RulesetVersion[];
  onChanged: (d: RulesetDetail) => void;
  onDiscarded: () => void;
}) {
  const isDraft = detail.status === "draft";
  return (
    <div className="flex flex-col gap-space-lg">
      <Card
        title={`${detail.procedure_name} · version ${detail.version}`}
        subtitle={`${detail.observation_days}-day monitoring · created ${formatDate(detail.created_at)}`}
        actions={<StatusPill status={detail.status} />}
      >
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-space-md gap-y-1 font-body-md">
          <dt className="text-on-surface-variant">Cut-offs</dt>
          <dd className="text-on-surface">
            Review at {detail.review_at} points, critical at {detail.critical_at}; each measure capped at {detail.max_points_per_parameter}
          </dd>
          <dt className="text-on-surface-variant">Patients</dt>
          <dd className="text-on-surface">
            {detail.active_episodes} monitored under this version now{detail.total_episodes > detail.active_episodes ? `, ${detail.total_episodes} in all` : ""}
          </dd>
          {detail.composite_summary.length > 0 && (
            <>
              <dt className="text-on-surface-variant">Across measures</dt>
              <dd className="text-on-surface">{detail.composite_summary.join("; ")}</dd>
            </>
          )}
          {detail.approved_by && (
            <>
              <dt className="text-on-surface-variant">Approved</dt>
              <dd className="text-on-surface">
                by {detail.approved_by}
                {detail.approved_at ? ` on ${formatDate(detail.approved_at)}` : ""}
              </dd>
            </>
          )}
          {detail.notes && (
            <>
              <dt className="text-on-surface-variant">Notes</dt>
              <dd className="text-on-surface">{detail.notes}</dd>
            </>
          )}
        </dl>
        <div className="mt-space-md">
          {isDraft ? (
            <DraftControls key={detail.ruleset_id} detail={detail} versions={versions} onChanged={onChanged} onDiscarded={onDiscarded} />
          ) : (
            <StartDraft key={detail.ruleset_id} detail={detail} versions={versions} onChanged={onChanged} />
          )}
        </div>
      </Card>

      <Card
        title="Measures"
        subtitle={isDraft ? "Edit what is asked, when, and how each answer scores." : "What is asked, when, and how each answer scores."}
      >
        <Measures key={detail.ruleset_id} detail={detail} onChanged={onChanged} />
      </Card>
    </div>
  );
}

export default function RulesetsAdminPage() {
  const list = useApiData(fetchRulesets);
  const [detail, setDetail] = useState<RulesetDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const select = async (rulesetId: number) => {
    setLoadError(null);
    try {
      setDetail(await fetchRuleset(rulesetId));
    } catch (err) {
      setLoadError(message(err, "Could not open the ruleset."));
    }
  };

  const changed = (d: RulesetDetail) => {
    setDetail(d);
    list.reload();
  };

  const versionsOf = (procedureCode: string) => list.data?.find((p) => p.procedure_code === procedureCode)?.versions ?? [];

  return (
    <PageBody>
      <Notice icon="rule_settings">
        Rules are versioned. Only a draft can change; approving it publishes it for new enrollments and retires the version before it.
      </Notice>
      {(list.error || loadError) && <ErrorBanner message={list.error ?? loadError ?? ""} onRetry={list.reload} />}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)] gap-space-lg items-start">
        <div className="flex flex-col gap-space-lg">
          {!list.data && !list.error && <Loading />}
          {list.data?.map((procedure) => (
            <Card
              key={procedure.procedure_code}
              title={procedure.procedure_name}
              subtitle={`${procedure.observation_days}-day monitoring · offered by ${procedure.hospitals_offering} hospital${procedure.hospitals_offering === 1 ? "" : "s"}`}
            >
              {procedure.versions.length === 0 ? (
                <p className="font-body-md text-on-surface-variant">No ruleset yet.</p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {procedure.versions.map((v) => (
                    <li key={v.ruleset_id}>
                      <button
                        type="button"
                        onClick={() => select(v.ruleset_id)}
                        aria-current={detail?.ruleset_id === v.ruleset_id ? "true" : undefined}
                        className={`w-full text-left p-2.5 rounded-lg border cursor-pointer transition-colors ${
                          detail?.ruleset_id === v.ruleset_id
                            ? "border-primary bg-surface-container-low"
                            : "border-outline-variant/40 hover:border-outline-variant"
                        }`}
                      >
                        <span className="flex items-center justify-between gap-space-sm">
                          <span className="font-label-md text-on-surface">Version {v.version}</span>
                          <StatusPill status={v.status} />
                        </span>
                        <span className="block font-body-sm text-on-surface-variant">
                          {v.parameter_count} measures · {v.active_episodes} patient{v.active_episodes === 1 ? "" : "s"} now
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          ))}
        </div>

        {detail ? (
          <RulesetPanel
            detail={detail}
            versions={versionsOf(detail.procedure_code)}
            onChanged={changed}
            onDiscarded={() => {
              setDetail(null);
              list.reload();
            }}
          />
        ) : (
          <Card>
            <p className="font-body-md text-on-surface-variant">Choose a version to see its measures, or to start a new draft from it.</p>
          </Card>
        )}
      </div>
    </PageBody>
  );
}
