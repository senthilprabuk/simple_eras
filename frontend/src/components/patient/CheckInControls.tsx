"use client";

import React, { useState } from "react";
import {
  FormParameter,
  AnswerValue,
  isAnswered,
  iconFor,
  anchorFor,
  stepFor,
} from "@/lib/checkinApi";

export function QuestionCard({
  param,
  children,
}: {
  param: FormParameter;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-surface-container-lowest rounded-2xl border border-outline-variant/40 p-space-md">
      <div className="flex items-start gap-space-sm mb-space-md">
        <span className="material-symbols-outlined text-[22px] text-primary mt-0.5 shrink-0">
          {iconFor(param)}
        </span>
        <h2 className="font-title-sm text-on-surface">{param.question_text}</h2>
      </div>
      {children}
    </section>
  );
}

export function NumberStepper({
  param,
  value,
  onChange,
}: {
  param: FormParameter;
  value: AnswerValue;
  onChange: (v: AnswerValue) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const step = stepFor(param);
  const decimals = param.decimals;
  const min = param.value_min ?? 0;
  const max = param.value_max ?? 100;
  const current = typeof value === "number" ? value : null;

  const clamp = (n: number) => Math.min(max, Math.max(min, n));
  const round = (n: number) => Number(n.toFixed(decimals));

  const nudge = (direction: 1 | -1) => {
    const base = current ?? anchorFor(param);
    const next = current === null ? base : base + direction * step;
    onChange(round(clamp(next)));
  };

  const commitDraft = () => {
    setEditing(false);
    const parsed = Number(draft);
    if (draft.trim() === "" || Number.isNaN(parsed)) return;
    onChange(round(clamp(parsed)));
  };

  return (
    <div className="flex items-center justify-between gap-space-sm">
      <StepButton icon="remove" label={`Decrease ${param.name}`} onClick={() => nudge(-1)} />

      <div className="flex-1 text-center">
        {editing ? (
          <input
            autoFocus
            type="number"
            inputMode="decimal"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitDraft}
            onKeyDown={(e) => e.key === "Enter" && commitDraft()}
            className="w-full text-center font-metric-tabular text-on-surface bg-surface-container-low rounded-xl py-1 border border-primary focus:outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              setDraft(current === null ? "" : String(current));
              setEditing(true);
            }}
            aria-label={`Type a value for ${param.name}`}
            className="w-full py-1 rounded-xl hover:bg-surface-container-low transition-colors cursor-pointer"
          >
            <span
              className={`font-metric-tabular ${
                current === null ? "text-outline" : "text-on-surface"
              }`}
            >
              {current === null ? "—" : current.toFixed(decimals)}
            </span>
            {param.unit && current !== null && (
              <span className="font-body-md text-on-surface-variant ml-1">{param.unit}</span>
            )}
            <span className="block font-body-sm text-outline">
              {current === null ? "Tap to enter" : "Tap to edit"}
            </span>
          </button>
        )}
      </div>

      <StepButton icon="add" label={`Increase ${param.name}`} onClick={() => nudge(1)} />
    </div>
  );
}

function StepButton({
  icon,
  label,
  onClick,
}: {
  icon: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="h-14 w-14 shrink-0 rounded-full bg-surface-container-low border border-outline-variant/50 text-primary flex items-center justify-center active:bg-surface-container-high transition-colors cursor-pointer"
    >
      <span className="material-symbols-outlined text-[26px]">{icon}</span>
    </button>
  );
}

function painDescriptor(score: number): string {
  if (score === 0) return "No pain";
  if (score <= 2) return "Mild";
  if (score <= 4) return "Uncomfortable";
  if (score <= 6) return "Moderate";
  if (score <= 8) return "Severe";
  return "Worst possible";
}

function painTone(score: number) {
  if (score <= 3) return { bg: "bg-primary", text: "text-on-primary", accent: "text-primary" };
  if (score <= 6) return { bg: "bg-tertiary", text: "text-on-tertiary", accent: "text-tertiary" };
  return { bg: "bg-error", text: "text-on-error", accent: "text-error" };
}

export function PainScale({
  param,
  value,
  onChange,
}: {
  param: FormParameter;
  value: AnswerValue;
  onChange: (v: AnswerValue) => void;
}) {
  const selected = typeof value === "number" ? value : null;
  const min = param.value_min ?? 0;
  const max = param.value_max ?? 10;
  const scores = Array.from({ length: max - min + 1 }, (_, i) => min + i);

  return (
    <div>
      <div className="grid grid-cols-6 gap-1.5">
        {scores.map((score) => {
          const active = selected === score;
          const tone = painTone(score);
          return (
            <button
              key={score}
              type="button"
              aria-label={`${score} out of ${max}`}
              aria-pressed={active}
              onClick={() => onChange(score)}
              className={`h-12 rounded-xl font-title-sm border transition-colors cursor-pointer ${
                active
                  ? `${tone.bg} ${tone.text} border-transparent`
                  : "bg-surface-container-low border-outline-variant/40 text-on-surface-variant hover:border-outline-variant"
              }`}
            >
              {score}
            </button>
          );
        })}
      </div>
      <p
        className={`font-body-md mt-space-sm text-center ${
          selected === null ? "text-outline" : painTone(selected).accent
        }`}
      >
        {selected === null
          ? `${min} is no pain, ${max} is the worst you can imagine`
          : `${selected} / ${max} · ${painDescriptor(selected)}`}
      </p>
    </div>
  );
}

export function ChoiceList({
  param,
  value,
  onChange,
}: {
  param: FormParameter;
  value: AnswerValue;
  onChange: (v: AnswerValue) => void;
}) {
  return (
    <div className="flex flex-col gap-space-sm">
      {param.options.map((option) => {
        const active = value === option.code;
        return (
          <button
            key={option.code}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.code)}
            className={`flex items-center justify-between gap-space-sm px-space-md py-3.5 rounded-xl border text-left transition-colors cursor-pointer ${
              active
                ? "bg-primary/10 border-primary text-primary"
                : "bg-surface-container-low border-outline-variant/40 text-on-surface hover:border-outline-variant"
            }`}
          >
            <span className="font-body-lg">{option.label}</span>
            <span
              className={`material-symbols-outlined text-[22px] shrink-0 ${
                active ? "text-primary" : "text-outline-variant"
              }`}
            >
              {active ? "radio_button_checked" : "radio_button_unchecked"}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function YesNoQuestion({
  param,
  value,
  onChange,
}: {
  param: FormParameter;
  value: AnswerValue;
  onChange: (v: AnswerValue) => void;
}) {
  const answered = isAnswered(value);
  const isYes = value === true;

  return (
    <section
      className={`rounded-2xl border p-space-md transition-colors ${
        isYes
          ? "bg-error-container/40 border-error/40"
          : "bg-surface-container-lowest border-outline-variant/40"
      }`}
    >
      <div className="flex items-start gap-space-sm mb-space-sm">
        <span
          className={`material-symbols-outlined text-[22px] mt-0.5 shrink-0 ${
            isYes ? "text-error" : "text-primary"
          }`}
        >
          {iconFor(param)}
        </span>
        <h2 className="font-title-sm text-on-surface">{param.question_text}</h2>
      </div>

      <div className="grid grid-cols-2 gap-space-sm">
        <button
          type="button"
          aria-pressed={isYes}
          onClick={() => onChange(true)}
          className={`py-3.5 rounded-xl border font-title-sm transition-colors cursor-pointer ${
            isYes
              ? "bg-error text-on-error border-transparent"
              : "bg-surface-container-low border-outline-variant/40 text-on-surface-variant hover:border-outline-variant"
          }`}
        >
          Yes
        </button>
        <button
          type="button"
          aria-pressed={answered && !isYes}
          onClick={() => onChange(false)}
          className={`py-3.5 rounded-xl border font-title-sm transition-colors cursor-pointer ${
            answered && !isYes
              ? "bg-primary text-on-primary border-transparent"
              : "bg-surface-container-low border-outline-variant/40 text-on-surface-variant hover:border-outline-variant"
          }`}
        >
          No
        </button>
      </div>
    </section>
  );
}
