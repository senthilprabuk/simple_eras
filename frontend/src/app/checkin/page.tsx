"use client";

import React, { Suspense, useState, useEffect, useMemo, useSyncExternalStore } from "react";
import {
  EpisodeOption,
  EpisodeContext,
  CheckInForm,
  CheckInReceipt,
  FormParameter,
  FormSection,
  Answers,
  AnswerValue,
  fetchEpisodes,
  fetchCheckInForm,
  fetchCheckInFormByToken,
  CheckInRequestError,
  submitCheckIn,
  isAnswered,
  formatAnswer,
  unansweredIn,
  urgentAnswers,
} from "@/lib/checkinApi";
import { CHECKIN_LANGUAGES, CheckInText, EMERGENCY_SERVICES, checkInText } from "@/lib/checkinText";
import {
  QuestionCard,
  NumberStepper,
  PainScale,
  ChoiceList,
  YesNoQuestion,
} from "@/components/patient/CheckInControls";

/**
 * Simulated submissions are pinned to one fixture so they always land on the same
 * record. FX-01 is the uneventful-recovery baseline, so demo data does not muddle
 * a fixture whose seeded history is meant to demonstrate a specific escalation.
 */
const SIMULATED_PATIENT_MRN = "FX-01";

/** Post-op days offered as "new patient" previews, since the seeded episodes are all day 25. */
const NEW_PATIENT_DAYS = [
  { day: 1, note: "just discharged" },
  { day: 7, note: "first week" },
  { day: 12, note: "before milestones start" },
];

interface SimOption {
  key: string;
  group: string;
  label: string;
  episodeId: string;
  day?: number;
}

const HOME = -1;

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `checkin-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * The token from the patient's WhatsApp link. It travels after "#", which browsers never
 * send to a server, so no server or proxy log records it. Links sent before that carry
 * ?token=; the page moves it behind "#", so a reload keeps working without sending it.
 */
function readLinkToken(): string | null {
  return (
    new URLSearchParams(window.location.hash.slice(1)).get("token") ??
    new URLSearchParams(window.location.search).get("token")
  );
}

// Opening a link on an already-open check-in page changes only the "#" part, which
// does not reload the page.
function subscribeToAddress(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** undefined until the browser has read the address; the server never sees one. */
function useLinkToken(): string | null | undefined {
  const token = useSyncExternalStore(subscribeToAddress, readLinkToken, () => undefined);
  useEffect(() => {
    const fromQuery = new URLSearchParams(window.location.search).get("token");
    if (fromQuery && !window.location.hash) {
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}#token=${encodeURIComponent(fromQuery)}`
      );
    }
  }, []);
  return token;
}

function CheckInContent() {
  const linkToken = useLinkToken();
  const addressRead = linkToken !== undefined;
  const token = linkToken ?? null;
  const isTokenMode = Boolean(token);

  const [episodes, setEpisodes] = useState<EpisodeOption[]>([]);
  const [episodesError, setEpisodesError] = useState<string | null>(null);
  // The server has the simulator off, so without a link there is nothing to show but where to find one.
  const [simulatorOff, setSimulatorOff] = useState(false);
  const [chosenKey, setChosenKey] = useState<string>("");
  const [form, setForm] = useState<CheckInForm | null>(null);
  const [loadedKey, setLoadedKey] = useState<string>("");
  const [formError, setFormError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  // undefined: the patient's own language, which the server picks.
  const [chosenLanguage, setChosenLanguage] = useState<string | undefined>(undefined);
  // Questions the patient must answer before moving on, and the optional ones they skipped.
  const [flagged, setFlagged] = useState<Set<string>>(new Set());
  const [skipped, setSkipped] = useState<FormParameter[] | null>(null);

  const [stepIndex, setStepIndex] = useState<number>(HOME);
  const [answers, setAnswers] = useState<Answers>({});
  const [photo, setPhoto] = useState<File | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string>(newIdempotencyKey);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<CheckInReceipt | null>(null);

  const photoUrl = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(
    () => () => {
      if (photoUrl) URL.revokeObjectURL(photoUrl);
    },
    [photoUrl]
  );

  // When token is provided (patient clicked WhatsApp magic link), fetch directly by token
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetchCheckInFormByToken(token, chosenLanguage)
      .then((next) => {
        if (cancelled) return;
        setForm(next);
        setFormError(null);
        setLoadedKey(token);
        setAnswers({});
        setPhoto(null);
        setReceipt(null);
        setSubmitError(null);
        setIdempotencyKey(newIdempotencyKey());
        setStepIndex(HOME);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setFormError(err.message);
        setLoadedKey(token);
      });
    return () => {
      cancelled = true;
    };
  }, [token, reloadNonce, chosenLanguage]);

  const simOptions: SimOption[] = useMemo(() => {
    if (isTokenMode || episodes.length === 0) return [];
    const base = episodes.find((e) => e.mrn === SIMULATED_PATIENT_MRN) ?? episodes[0];
    return [
      ...NEW_PATIENT_DAYS.map((d) => ({
        key: `${base.episode_id}:${d.day}`,
        group: `New patient · simulated on ${base.mrn ?? base.patient_name}`,
        label: `Day ${d.day} · ${d.note}`,
        episodeId: base.episode_id,
        day: d.day,
      })),
      ...episodes.map((e) => ({
        key: `${e.episode_id}:live`,
        group: "Existing patient (live data)",
        label: `${e.patient_name} · Day ${e.post_op_day}`,
        episodeId: e.episode_id,
      })),
    ];
  }, [isTokenMode, episodes]);

  // When in simulator mode (no token), load episodes
  useEffect(() => {
    if (!addressRead || isTokenMode) return;
    let cancelled = false;
    fetchEpisodes()
      .then((list) => {
        if (cancelled) return;
        setEpisodes(list);
        if (list.length === 0) setEpisodesError("No active episodes found in the database.");
      })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err instanceof CheckInRequestError && err.status === 404) {
          setSimulatorOff(true);
          return;
        }
        // fetch throws TypeError when the server is unreachable; otherwise the server said why.
        setEpisodesError(err instanceof TypeError ? `Could not reach the backend: ${err.message}` : err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [addressRead, isTokenMode]);

  // Selection is derived for simulator mode
  const selected = useMemo(() => {
    if (isTokenMode || simOptions.length === 0) return undefined;
    return (
      simOptions.find((o) => o.key === chosenKey) ??
      simOptions.find((o) => o.day === undefined) ??
      simOptions[0]
    );
  }, [isTokenMode, simOptions, chosenKey]);

  useEffect(() => {
    if (isTokenMode || !selected) return;
    let cancelled = false;
    const key = selected.key;
    fetchCheckInForm(selected.episodeId, selected.day, chosenLanguage)
      .then((next) => {
        if (cancelled) return;
        setForm(next);
        setFormError(null);
        setLoadedKey(key);
        setAnswers({});
        setPhoto(null);
        setReceipt(null);
        setSubmitError(null);
        setIdempotencyKey(newIdempotencyKey());
        setStepIndex(HOME);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setFormError(`Could not load the check-in form: ${err.message}`);
        setLoadedKey(key);
      });
    return () => {
      cancelled = true;
    };
  }, [isTokenMode, selected, reloadNonce, chosenLanguage]);

  const ready = isTokenMode
    ? (token ? loadedKey === token : false)
    : (selected !== undefined && loadedKey === selected.key);
  const activeForm = ready && !formError ? form : null;
  const errorMessage = isTokenMode ? formError : (episodesError ?? (ready ? formError : null));
  const showSimulatorOff = simulatorOff && !isTokenMode;
  const loading = !errorMessage && !activeForm && !showSimulatorOff;
  const text = checkInText(activeForm?.language ?? chosenLanguage);

  const steps = useMemo(() => {
    if (!activeForm) return [];
    return [
      ...activeForm.sections.map((s) => ({
        kind: "section" as const,
        title: text.sections[s.key] ?? s.key,
        section: s,
      })),
      { kind: "photo" as const, title: text.photoStep, section: undefined },
      { kind: "review" as const, title: text.reviewStep, section: undefined },
    ];
  }, [activeForm, text]);

  const allParameters: FormParameter[] = useMemo(
    () => (activeForm ? activeForm.sections.flatMap((s) => s.parameters) : []),
    [activeForm]
  );

  const urgent = useMemo(
    () => (activeForm ? urgentAnswers(activeForm.sections, answers) : []),
    [activeForm, answers]
  );

  const answeredCount = allParameters.filter((p) => isAnswered(answers[p.code])).length;
  const DONE = steps.length;

  const setAnswer = (code: string, value: AnswerValue) =>
    setAnswers((prev) => ({ ...prev, [code]: value }));

  const goTo = (index: number) => {
    setFlagged(new Set());
    setSkipped(null);
    setStepIndex(index);
  };

  // A blank answer is unknown, never "no". Yes/no symptom questions must be answered;
  // a reading may be skipped, but only once the patient has seen what is missing.
  const goNext = () => {
    const step = steps[stepIndex];
    if (step.kind === "section" && step.section) {
      const { required, optional } = unansweredIn(step.section, answers);
      if (required.length > 0) {
        setSkipped(null);
        setFlagged(new Set(required.map((p) => p.code)));
        return;
      }
      if (optional.length > 0 && skipped === null) {
        setFlagged(new Set());
        setSkipped(optional);
        return;
      }
    }
    goTo(stepIndex + 1);
  };
  const stillFlagged = new Set([...flagged].filter((code) => !isAnswered(answers[code])));

  const handleSubmit = async () => {
    if (!activeForm) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await submitCheckIn({
        episodeId: activeForm.episode.episode_id,
        day: activeForm.effective_day,
        simulated: activeForm.simulated,
        idempotencyKey,
        token: token || undefined,
        parameters: allParameters,
        answers,
      });
      setReceipt(result);
      setStepIndex(DONE);
    } catch (err) {
      setSubmitError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-surface-container-high flex items-center justify-center sm:p-6">
      {addressRead && !isTokenMode && !simulatorOff && (
        <SimulatorControl
          options={simOptions}
          value={selected?.key ?? ""}
          onChange={setChosenKey}
          form={activeForm}
        />
      )}

      <div className="relative flex flex-col w-full h-screen bg-surface-bright overflow-hidden sm:h-[860px] sm:max-h-[calc(100vh-3rem)] sm:w-[400px] sm:rounded-[2.25rem] sm:border-[10px] sm:border-on-surface sm:shadow-2xl">
        <StatusBar />

        {loading && <CentredMessage icon="progress_activity" title={text.loading} spin />}

        {showSimulatorOff && (
          <CentredMessage icon="chat" title={text.openFromWhatsAppTitle} body={text.openFromWhatsAppBody} />
        )}

        {errorMessage && (
          <CentredMessage
            icon={isTokenMode ? "link_off" : "cloud_off"}
            title={isTokenMode ? text.linkErrorTitle : text.backendUnavailable}
            body={isTokenMode ? `${errorMessage} ${text.linkErrorAdvice}` : errorMessage}
          />
        )}

        {activeForm && (
          <>
            {stepIndex === HOME && (
              <HomeScreen
                form={activeForm}
                text={text}
                onStart={() => goTo(0)}
                onLanguage={setChosenLanguage}
                questionCount={allParameters.length}
                stepCount={steps.length}
              />
            )}

            {stepIndex >= 0 && stepIndex < DONE && (
              <>
                <AppBar
                  title={steps[stepIndex].title}
                  text={text}
                  stepIndex={stepIndex}
                  stepCount={steps.length}
                  onBack={() => goTo(stepIndex - 1)}
                />

                <main className="flex-1 overflow-y-auto px-space-md py-space-md flex flex-col gap-space-md">
                  {steps[stepIndex].kind === "section" && (
                    <SectionStep
                      section={steps[stepIndex].section as FormSection}
                      episode={activeForm.episode}
                      text={text}
                      flagged={stillFlagged}
                      answers={answers}
                      onAnswer={setAnswer}
                      urgent={urgent}
                    />
                  )}

                  {steps[stepIndex].kind === "photo" && (
                    <PhotoStep photo={photo} photoUrl={photoUrl} onPick={setPhoto} text={text} />
                  )}

                  {steps[stepIndex].kind === "review" && (
                    <ReviewStep
                      form={activeForm}
                      text={text}
                      answers={answers}
                      photoUrl={photoUrl}
                      urgent={urgent}
                      onJumpTo={goTo}
                      error={submitError}
                    />
                  )}
                </main>

                {skipped ? (
                  <SkipPrompt
                    text={text}
                    names={skipped.map((p) => p.name).join(", ")}
                    onAnswer={() => setSkipped(null)}
                    onSkip={() => goTo(stepIndex + 1)}
                  />
                ) : (
                  <BottomBar
                    label={stepIndex === DONE - 1 ? text.sendToCareTeam : text.continue}
                    sendingLabel={text.sending}
                    busy={submitting}
                    onClick={() => (stepIndex === DONE - 1 ? handleSubmit() : goNext())}
                    warning={stillFlagged.size > 0 ? text.answerRequired : undefined}
                    hint={stepIndex === DONE - 1 ? text.answeredOf(answeredCount, allParameters.length) : undefined}
                  />
                )}
              </>
            )}

            {stepIndex === DONE && receipt && (
              <DoneScreen
                receipt={receipt}
                text={text}
                episode={activeForm.episode}
                urgent={urgent.length > 0}
                onRestart={() => setReloadNonce((n) => n + 1)}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- simulator */

function SimulatorControl({
  options,
  value,
  onChange,
  form,
}: {
  options: SimOption[];
  value: string;
  onChange: (key: string) => void;
  form: CheckInForm | null;
}) {
  const groups = Array.from(new Set(options.map((o) => o.group)));

  return (
    <div className="fixed top-3 right-3 z-50 w-[220px] bg-surface-container-lowest/95 backdrop-blur border border-outline-variant/50 rounded-xl shadow-lg p-2">
      <label
        htmlFor="sim-select"
        className="flex items-center gap-1 font-label-sm uppercase tracking-wider text-on-surface-variant mb-1"
      >
        <span className="material-symbols-outlined text-[14px] text-primary">science</span>
        Simulate patient
      </label>
      <select
        id="sim-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full font-body-sm text-on-surface bg-surface-bright border border-outline-variant/60 rounded-lg px-2 py-1.5 focus:outline-none focus:border-primary cursor-pointer"
      >
        {groups.map((group) => (
          <optgroup key={group} label={group}>
            {options
              .filter((o) => o.group === group)
              .map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      {form && (
        <p className="font-body-sm text-on-surface-variant mt-1.5 leading-snug">
          Day {form.effective_day} · {form.sections.reduce((n, s) => n + s.parameters.length, 0)}{" "}
          questions
          {form.simulated && <span className="text-tertiary"> · simulated</span>}
        </p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- chrome */

function StatusBar() {
  return (
    <div className="hidden sm:flex items-center justify-between px-space-md pt-2 pb-1 bg-surface-bright text-on-surface shrink-0">
      <span className="font-label-md">9:41</span>
      <div className="flex items-center gap-1">
        <span className="material-symbols-outlined text-[15px]">signal_cellular_alt</span>
        <span className="material-symbols-outlined text-[15px]">wifi</span>
        <span className="material-symbols-outlined text-[15px]">battery_full_alt</span>
      </div>
    </div>
  );
}

function AppBar({
  title,
  text,
  stepIndex,
  stepCount,
  onBack,
}: {
  title: string;
  text: CheckInText;
  stepIndex: number;
  stepCount: number;
  onBack: () => void;
}) {
  return (
    <header className="shrink-0 bg-surface-bright border-b border-outline-variant/30">
      <div className="flex items-center gap-space-sm px-space-sm py-2">
        <button
          type="button"
          onClick={onBack}
          aria-label={text.goBack}
          className="h-11 w-11 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined text-[24px]">arrow_back</span>
        </button>
        <div className="flex-1">
          <h1 className="font-title-sm text-on-surface">{title}</h1>
          <p className="font-body-sm text-on-surface-variant">{text.stepOf(stepIndex + 1, stepCount)}</p>
        </div>
      </div>
      <div className="h-1 bg-surface-container-high">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${((stepIndex + 1) / stepCount) * 100}%` }}
        />
      </div>
    </header>
  );
}

function BottomBar({
  label,
  onClick,
  busy,
  hint,
  warning,
  sendingLabel,
}: {
  label: string;
  onClick: () => void;
  busy?: boolean;
  hint?: string;
  warning?: string;
  sendingLabel?: string;
}) {
  return (
    <div className="shrink-0 px-space-md pt-space-sm pb-space-md bg-surface-bright border-t border-outline-variant/30">
      {warning && (
        <p className="font-body-sm text-error text-center mb-space-sm" role="alert">{warning}</p>
      )}
      {hint && (
        <p className="font-body-sm text-on-surface-variant text-center mb-space-sm">{hint}</p>
      )}
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        className="w-full h-14 rounded-full bg-primary text-on-primary font-title-sm flex items-center justify-center gap-space-xs disabled:opacity-60 transition-colors cursor-pointer"
      >
        {busy && (
          <span className="material-symbols-outlined text-[20px] animate-spin">
            progress_activity
          </span>
        )}
        {busy ? sendingLabel ?? label : label}
      </button>
    </div>
  );
}

/** Readings left blank: the patient sees what is missing and chooses to go on without them. */
function SkipPrompt({
  text,
  names,
  onAnswer,
  onSkip,
}: {
  text: CheckInText;
  names: string;
  onAnswer: () => void;
  onSkip: () => void;
}) {
  return (
    <div className="shrink-0 px-space-md pt-space-sm pb-space-md bg-surface-bright border-t border-outline-variant/30">
      <p className="font-body-md text-on-surface mb-space-sm" role="alert">{text.skippedPrompt(names)}</p>
      <div className="grid grid-cols-2 gap-space-sm">
        <button
          type="button"
          onClick={onAnswer}
          className="h-12 rounded-full bg-primary text-on-primary font-title-sm cursor-pointer"
        >
          {text.answerThem}
        </button>
        <button
          type="button"
          onClick={onSkip}
          className="h-12 rounded-full border border-outline-variant text-on-surface font-title-sm cursor-pointer"
        >
          {text.continueWithout}
        </button>
      </div>
    </div>
  );
}

function CentredMessage({
  icon,
  title,
  body,
  spin,
}: {
  icon: string;
  title: string;
  body?: string;
  spin?: boolean;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-space-sm px-space-lg text-center">
      <span
        className={`material-symbols-outlined text-[36px] text-primary ${spin ? "animate-spin" : ""}`}
      >
        {icon}
      </span>
      <h2 className="font-title-sm text-on-surface">{title}</h2>
      {body && <p className="font-body-md text-on-surface-variant">{body}</p>}
    </div>
  );
}

/* --------------------------------------------------------------- screens */

function HomeScreen({
  form,
  text,
  onStart,
  onLanguage,
  questionCount,
  stepCount,
}: {
  form: CheckInForm;
  text: CheckInText;
  onStart: () => void;
  onLanguage: (language: string) => void;
  questionCount: number;
  stepCount: number;
}) {
  return (
    <>
      <main className="flex-1 overflow-y-auto px-space-md py-space-lg flex flex-col gap-space-lg">
        <div className="flex items-center justify-end gap-1" role="group" aria-label={text.language}>
          <span className="material-symbols-outlined text-[18px] text-on-surface-variant mr-1">translate</span>
          {CHECKIN_LANGUAGES.map((l) => (
            <button
              key={l.code}
              type="button"
              aria-pressed={form.language === l.code}
              onClick={() => onLanguage(l.code)}
              className={`px-2.5 py-1 rounded-full font-label-md border cursor-pointer ${
                form.language === l.code
                  ? "bg-primary text-on-primary border-transparent"
                  : "border-outline-variant/60 text-on-surface-variant"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        <div>
          <p className="font-body-lg text-on-surface-variant">{text.greeting}</p>
          <h1 className="font-display-lg text-on-surface">{form.episode.first_name}</h1>
        </div>

        <section className="bg-primary text-on-primary rounded-2xl p-space-lg">
          <div className="flex items-center gap-space-xs mb-space-xs">
            <span className="material-symbols-outlined text-[20px]">calendar_today</span>
            <span className="font-label-md uppercase tracking-wider">{text.dayAfterSurgery(form.effective_day)}</span>
          </div>
          <h2 className="font-headline-md mb-space-xs">
            {form.already_submitted_today ? text.alreadyCheckedIn : text.checkInReady}
          </h2>
          <p className="font-body-md opacity-90">
            {text.overview(questionCount, stepCount, form.episode.hospital_name)}
          </p>
        </section>

        <section className="flex flex-col gap-space-sm">
          {form.sections.map((s) => (
            <div key={s.key} className="flex items-center gap-space-sm">
              <span className="h-10 w-10 shrink-0 rounded-full bg-surface-container-low text-primary flex items-center justify-center font-title-sm">
                {s.parameters.length}
              </span>
              <div>
                <span className="font-body-lg text-on-surface block">{text.sections[s.key] ?? s.key}</span>
                <span className="font-body-sm text-on-surface-variant">
                  {s.parameters.map((p) => p.name).join(", ")}
                </span>
              </div>
            </div>
          ))}
        </section>

        {form.simulated && (
          <div className="flex items-start gap-space-xs bg-tertiary-fixed/50 border border-tertiary-fixed-dim/50 rounded-xl p-space-sm">
            <span className="material-symbols-outlined text-[18px] text-tertiary mt-0.5 shrink-0">
              science
            </span>
            <p className="font-body-sm text-on-tertiary-fixed">
              Simulated day {form.effective_day}. {form.episode.first_name} is actually on day{" "}
              {form.episode.actual_post_op_day}, so this submission is recorded as synthetic.
            </p>
          </div>
        )}
      </main>

      <BottomBar label={form.already_submitted_today ? text.checkInAgain : text.startCheckIn} onClick={onStart} />
    </>
  );
}

function SectionStep({
  section,
  episode,
  text,
  flagged,
  answers,
  onAnswer,
  urgent,
}: {
  section: FormSection;
  episode: EpisodeContext;
  text: CheckInText;
  flagged: Set<string>;
  answers: Answers;
  onAnswer: (code: string, value: AnswerValue) => void;
  urgent: FormParameter[];
}) {
  const intro = section.key === "checks" ? text.checksIntro : undefined;

  return (
    <>
      {intro && <p className="font-body-md text-on-surface-variant">{intro}</p>}

      {section.parameters.map((param) => {
        const value = answers[param.code] ?? null;
        const onChange = (v: AnswerValue) => onAnswer(param.code, v);

        if (param.type === "boolean") {
          return (
            <YesNoQuestion
              key={param.code}
              param={param}
              value={value}
              onChange={onChange}
              text={text}
              flagged={flagged.has(param.code)}
            />
          );
        }

        const isPainStyle =
          param.type === "numeric" &&
          !param.unit &&
          param.value_min === 0 &&
          param.value_max === 10;

        return (
          <QuestionCard key={param.code} param={param} text={text} flagged={flagged.has(param.code)}>
            {isPainStyle ? (
              <PainScale param={param} value={value} onChange={onChange} text={text} />
            ) : param.type === "ordinal" ? (
              <ChoiceList param={param} value={value} onChange={onChange} />
            ) : (
              <NumberStepper param={param} value={value} onChange={onChange} text={text} />
            )}
          </QuestionCard>
        );
      })}

      {urgent.length > 0 && <UrgentNotice flags={urgent} episode={episode} text={text} />}
    </>
  );
}

/**
 * The ward first when the hospital has set its number, with emergency services
 * beside it; emergency services alone until then, rather than a number nobody answers.
 */
function CallButtons({ episode, text, light }: { episode: EpisodeContext; text: CheckInText; light?: boolean }) {
  const phone = episode.hospital_emergency_phone;
  const primary = light
    ? "bg-surface-container-lowest text-error"
    : "bg-error text-on-error";
  const secondary = light
    ? "border border-on-error/70 text-on-error"
    : "border border-error text-error";
  return (
    <div className="flex flex-col gap-space-sm">
      {phone && (
        <a
          href={`tel:${phone}`}
          className={`w-full h-12 rounded-full font-title-sm flex items-center justify-center gap-space-xs ${primary}`}
        >
          <span className="material-symbols-outlined text-[20px]">call</span>
          {text.callWard}
        </a>
      )}
      <a
        href={`tel:${EMERGENCY_SERVICES}`}
        className={`w-full h-12 rounded-full font-title-sm flex items-center justify-center gap-space-xs ${
          phone ? secondary : primary
        }`}
      >
        <span className="material-symbols-outlined text-[20px]">emergency</span>
        {text.call112}
      </a>
    </div>
  );
}

function UrgentNotice({ flags, episode, text }: { flags: FormParameter[]; episode: EpisodeContext; text: CheckInText }) {
  const symptoms = flags
    .map((f) => (text.locale.startsWith("en") ? f.name.toLowerCase() : f.name))
    .join(text.and);
  return (
    <section className="bg-error text-on-error rounded-2xl p-space-md">
      <div className="flex items-center gap-space-xs mb-space-xs">
        <span className="material-symbols-outlined text-[22px]">emergency_home</span>
        <h2 className="font-title-sm">{text.urgentTitle}</h2>
      </div>
      <p className="font-body-md opacity-95 mb-space-md">
        {episode.hospital_emergency_phone
          ? text.urgentWithWard(symptoms, episode.hospital_name)
          : text.urgentNoWard(symptoms)}
      </p>
      <CallButtons episode={episode} text={text} light />
    </section>
  );
}

function PhotoStep({
  photo,
  photoUrl,
  onPick,
  text,
}: {
  photo: File | null;
  photoUrl: string | null;
  onPick: (f: File | null) => void;
  text: CheckInText;
}) {
  return (
    <>
      <p className="font-body-md text-on-surface-variant">{text.photoHint}</p>

      {photoUrl ? (
        <div className="rounded-2xl overflow-hidden border border-outline-variant/40 bg-surface-container-lowest">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={photoUrl} alt={text.photoAlt} className="w-full h-56 object-cover" />
          <div className="flex items-center justify-between p-space-sm">
            <span className="font-body-sm text-on-surface-variant truncate">{photo?.name}</span>
            <button
              type="button"
              onClick={() => onPick(null)}
              className="font-label-md text-error px-2 py-1 rounded cursor-pointer hover:bg-error-container/50"
            >
              {text.remove}
            </button>
          </div>
        </div>
      ) : (
        <label className="flex flex-col items-center justify-center gap-space-xs h-56 rounded-2xl border-2 border-dashed border-outline-variant bg-surface-container-lowest text-on-surface-variant cursor-pointer hover:border-primary hover:text-primary transition-colors">
          <span className="material-symbols-outlined text-[40px] text-primary">photo_camera</span>
          <span className="font-title-sm">{text.takePhoto}</span>
          <span className="font-body-sm">{text.orGallery}</span>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          />
        </label>
      )}

      <div className="flex items-start gap-space-xs bg-tertiary-fixed/50 border border-tertiary-fixed-dim/50 rounded-xl p-space-sm">
        <span className="material-symbols-outlined text-[18px] text-tertiary mt-0.5 shrink-0">
          info
        </span>
        <p className="font-body-sm text-on-tertiary-fixed">{text.photoNotSent}</p>
      </div>
    </>
  );
}

function ReviewStep({
  form,
  text,
  answers,
  photoUrl,
  urgent,
  onJumpTo,
  error,
}: {
  form: CheckInForm;
  text: CheckInText;
  answers: Answers;
  photoUrl: string | null;
  urgent: FormParameter[];
  onJumpTo: (step: number) => void;
  error: string | null;
}) {
  return (
    <>
      {urgent.length > 0 && <UrgentNotice flags={urgent} episode={form.episode} text={text} />}

      {error && (
        <section className="bg-error-container border border-error/40 rounded-2xl p-space-md">
          <div className="flex items-center gap-space-xs mb-space-xs">
            <span className="material-symbols-outlined text-[20px] text-error">error</span>
            <h2 className="font-title-sm text-on-error-container">{text.couldNotSend}</h2>
          </div>
          <p className="font-body-sm text-on-error-container break-words">{error}</p>
        </section>
      )}

      {form.sections.map((section, index) => (
        <section
          key={section.key}
          className="bg-surface-container-lowest rounded-2xl border border-outline-variant/40 overflow-hidden"
        >
          <div className="flex items-center justify-between px-space-md py-space-sm border-b border-outline-variant/30">
            <h2 className="font-title-sm text-on-surface">{text.sections[section.key] ?? section.key}</h2>
            <button
              type="button"
              onClick={() => onJumpTo(index)}
              className="font-label-md text-primary px-2 py-1 rounded cursor-pointer hover:bg-surface-container-low"
            >
              {text.edit}
            </button>
          </div>
          <dl className="divide-y divide-outline-variant/30">
            {section.parameters.map((param) => {
              const value = answers[param.code] ?? null;
              const missing = !isAnswered(value);
              const concerning = param.type === "boolean" && value === true;
              return (
                <div
                  key={param.code}
                  className="flex items-center justify-between gap-space-sm px-space-md py-2.5"
                >
                  <dt className="font-body-md text-on-surface-variant">{param.name}</dt>
                  <dd
                    className={`font-body-md text-right shrink-0 ${
                      missing ? "text-outline italic" : concerning ? "text-error" : "text-on-surface"
                    }`}
                  >
                    {formatAnswer(param, value, text)}
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      ))}

      <section className="bg-surface-container-lowest rounded-2xl border border-outline-variant/40 px-space-md py-space-sm">
        <h2 className="font-title-sm text-on-surface mb-space-xs">{text.woundPhoto}</h2>
        {photoUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={photoUrl}
            alt={text.photoAlt}
            className="w-full h-32 object-cover rounded-xl"
          />
        ) : (
          <span className="font-body-md text-outline italic">{text.noPhoto}</span>
        )}
      </section>
    </>
  );
}

function DoneScreen({
  receipt,
  text,
  episode,
  urgent,
  onRestart,
}: {
  receipt: CheckInReceipt;
  text: CheckInText;
  episode: EpisodeContext;
  urgent: boolean;
  onRestart: () => void;
}) {
  return (
    <main className="flex-1 overflow-y-auto px-space-md py-space-xl flex flex-col items-center text-center gap-space-md">
      <span className="h-20 w-20 rounded-full bg-primary text-on-primary flex items-center justify-center">
        <span className="material-symbols-outlined text-[44px]">check</span>
      </span>

      <div>
        <h1 className="font-headline-lg text-on-surface">
          {receipt.duplicate ? text.alreadySent : text.checkInSent}
        </h1>
        <p className="font-body-lg text-on-surface-variant mt-space-xs">
          {receipt.duplicate
            ? text.alreadySentBody
            : text.answersRecorded(receipt.values_recorded, receipt.day_after_discharge)}
        </p>
        {receipt.superseded_count > 0 && (
          <p className="font-body-md text-on-surface-variant mt-space-xs">{text.replacesEarlier}</p>
        )}
      </div>

      {urgent && (
        <div className="w-full bg-error-container border border-error/30 rounded-xl p-space-md text-left flex flex-col gap-space-sm">
          <p className="font-body-md text-on-error-container">{text.urgentDone}</p>
          <CallButtons episode={episode} text={text} />
        </div>
      )}

      {/* Only claim what the server reports: a failed or unsent reply says nothing. */}
      {(receipt.patient_message_status === "sent" || receipt.patient_message_status === "queued") && (
        <div className="w-full bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-4 text-left flex items-start gap-3">
          <span className="material-symbols-outlined text-emerald-600 text-2xl shrink-0 mt-0.5">
            mark_chat_read
          </span>
          <p className="font-body-xs text-emerald-800 leading-relaxed">
            {receipt.patient_message_status === "sent" ? text.whatsappSent : text.whatsappQueued}
          </p>
        </div>
      )}

      <dl className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-xl divide-y divide-outline-variant/30 text-left">
        {[
          [text.reference, receipt.check_in_id.slice(0, 8)],
          // Staff running the simulator need to see a synthetic check-in marked as one.
          ...(receipt.source === "patient" ? [] : [["Recorded as", receipt.source]]),
          [text.received, new Date(receipt.submitted_at).toLocaleString(text.locale)],
        ].map(([label, value]) => (
          <div key={label} className="flex items-center justify-between px-space-md py-2">
            <dt className="font-body-sm text-on-surface-variant">{label}</dt>
            <dd className="font-body-sm text-on-surface">{value}</dd>
          </div>
        ))}
      </dl>

      <button
        type="button"
        onClick={onRestart}
        className="mt-auto w-full h-12 rounded-full border border-outline-variant text-primary font-title-sm cursor-pointer hover:bg-surface-container-low transition-colors"
      >
        {text.startAgain}
      </button>
    </main>
  );
}

export default function PatientCheckInPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen w-full bg-surface-container-high flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <span className="material-symbols-outlined text-3xl text-primary animate-spin">
              progress_activity
            </span>
            <span className="text-sm text-on-surface-variant font-medium">
              Loading your recovery check-in…
            </span>
          </div>
        </div>
      }
    >
      <CheckInContent />
    </Suspense>
  );
}
