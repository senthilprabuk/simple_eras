"use client";

import React, { useRef, useState } from "react";
import { useSession } from "@/components/SessionContext";
import { Card, ErrorBanner, Loading, Notice, PageBody, PageHeader, primaryButtonClass } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { fetchTemplates, saveTemplate, type Language, type TemplateCatalogue, type TemplateKey } from "@/lib/clinicalApi";
import { LANGUAGE_NAMES, formatDateTime } from "@/lib/format";
import { TEMPLATE_MAX_LENGTH, renderTemplate, templateProblems } from "@/lib/templates";
import { useApiData } from "@/lib/useApiData";

const TITLES: Record<TemplateKey, string> = {
  enrollment_welcome: "Welcome",
  checkin_reminder: "Daily check-in reminder",
  missed_checkin: "Missed check-in",
  urgent_guidance: "Urgent symptom guidance",
  checkin_confirmation: "Check-in confirmation",
};

const LANGUAGES: Language[] = ["en", "ta", "hi"];

function Editor({
  catalogue,
  templateKey,
  language,
  canEdit,
  onSaved,
}: {
  catalogue: TemplateCatalogue;
  templateKey: TemplateKey;
  language: Language;
  canEdit: boolean;
  onSaved: () => void;
}) {
  const session = useSession();
  const entry = catalogue.templates.find((t) => t.template_key === templateKey && t.language_code === language)!;
  const [body, setBody] = useState(entry.body ?? "");
  const [active, setActive] = useState(entry.body === null ? true : entry.is_active);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  const allowed = Object.keys(catalogue.placeholders);
  const problems = templateProblems(body, allowed);
  const preview = renderTemplate(body, {
    patient_first_name: "Lakshmi",
    hospital_name: session.hospitalName,
    post_op_day: "4",
    checkin_link: "https://example.org/c/7f3a",
  });

  const insert = (name: string) => {
    const el = textarea.current;
    const token = `{${name}}`;
    const at = el?.selectionStart ?? body.length;
    const end = el?.selectionEnd ?? body.length;
    setBody(body.slice(0, at) + token + body.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + token.length, at + token.length);
    });
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const saved = await saveTemplate(templateKey, language, body, active);
      setSavedAt(saved.updated_at);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      title={`${TITLES[templateKey]} · ${LANGUAGE_NAMES[language]}`}
      subtitle={catalogue.purposes[templateKey]}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
        <div className="flex flex-col gap-space-sm">
          <label className="flex flex-col gap-1">
            <span className="font-label-md text-on-surface">Message</span>
            <textarea
              ref={textarea}
              rows={7}
              value={body}
              readOnly={!canEdit}
              maxLength={TEMPLATE_MAX_LENGTH + 50}
              onChange={(e) => setBody(e.target.value)}
              placeholder={entry.body === null ? `Not written in ${LANGUAGE_NAMES[language]} yet.` : undefined}
              className="w-full p-2.5 bg-surface-bright border border-outline-variant/60 rounded-lg font-body-md text-on-surface focus:outline-none focus:border-primary read-only:opacity-80"
            />
          </label>
          <div className="flex items-center justify-between font-body-sm text-on-surface-variant">
            <span>{body.length} / {TEMPLATE_MAX_LENGTH} characters</span>
            {entry.updated_at && (
              <span>
                Last changed {formatDateTime(savedAt ?? entry.updated_at)}
                {entry.updated_by_name ? ` by ${entry.updated_by_name}` : ""}
              </span>
            )}
          </div>

          {canEdit && (
            <div className="flex flex-wrap gap-1.5" aria-label="Insert a placeholder">
              {Object.entries(catalogue.placeholders).map(([name, description]) => (
                <button
                  key={name}
                  type="button"
                  title={description}
                  onClick={() => insert(name)}
                  className="px-2 py-0.5 rounded border border-outline-variant/50 bg-surface-bright font-label-sm text-primary hover:border-primary cursor-pointer"
                >
                  {`{${name}}`}
                </button>
              ))}
            </div>
          )}

          {body && problems.length > 0 && (
            <ul role="alert" className="font-body-sm text-error list-disc pl-5">
              {problems.map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}

          {canEdit ? (
            <div className="flex items-center justify-between gap-space-sm">
              <label className="flex items-center gap-2 font-body-md text-on-surface cursor-pointer">
                <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
                In use
              </label>
              <button type="button" className={primaryButtonClass} disabled={saving || problems.length > 0} onClick={save}>
                {saving ? "Saving…" : "Save wording"}
              </button>
            </div>
          ) : (
            <p className="font-body-sm text-on-surface-variant">Only a superadmin can change patient-facing wording.</p>
          )}
          {error && <ErrorBanner message={error} />}
        </div>

        <div>
          <span className="font-label-md text-on-surface">Preview</span>
          <div className="mt-1 p-space-md rounded-xl bg-surface-container-high min-h-40">
            {body.trim() ? (
              <p className="max-w-[85%] px-3 py-2 rounded-lg rounded-tl-none bg-surface-container-lowest shadow-xs font-body-md text-on-surface whitespace-pre-wrap">
                {preview}
              </p>
            ) : (
              <p className="font-body-sm text-on-surface-variant">Nothing to preview.</p>
            )}
          </div>
          <p className="font-body-sm text-on-surface-variant mt-1">Sample values; each patient sees their own.</p>
        </div>
      </div>
    </Card>
  );
}

export default function TemplatesPage() {
  const session = useSession();
  const { data, error, reload } = useApiData(fetchTemplates);
  const [selected, setSelected] = useState<{ key: TemplateKey; language: Language }>({ key: "checkin_reminder", language: "en" });
  const canEdit = session.role === "superadmin";

  const missing = data?.templates.filter((t) => t.body === null).length ?? 0;

  return (
    <>
      <PageHeader title="WhatsApp templates" />
      <PageBody>
        <Notice icon="chat">
          These are the automated messages patients receive on WhatsApp throughout their recovery. Wording is sent dynamically based on the patient&apos;s language and post-operative day.
        </Notice>

        {error && <ErrorBanner message={error} onRetry={reload} />}
        {!data && !error && <Loading label="Loading templates…" />}

        {data && (
          <>
            {missing > 0 && (
              <p className="font-body-md text-on-surface">
                <span className="font-semibold">{missing} translations missing.</span> Patients whose language has no
                wording cannot be sent that message.
              </p>
            )}

            <section
              aria-label="Templates by language"
              className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 overflow-hidden shadow-sm"
            >
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-surface-bright/70 border-b border-outline-variant/30 text-on-surface-variant font-label-sm uppercase tracking-wider">
                    <th scope="col" className="py-3 px-space-md">Message</th>
                    {LANGUAGES.map((l) => <th key={l} scope="col" className="py-3 px-space-md">{LANGUAGE_NAMES[l]}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {(Object.keys(TITLES) as TemplateKey[]).map((key) => (
                    <tr key={key}>
                      <th scope="row" className="py-3 px-space-md font-normal">
                        <div className="font-title-sm text-on-surface">{TITLES[key]}</div>
                        <div className="font-body-sm text-on-surface-variant">{data.purposes[key]}</div>
                      </th>
                      {LANGUAGES.map((language) => {
                        const entry = data.templates.find((t) => t.template_key === key && t.language_code === language)!;
                        const isSelected = selected.key === key && selected.language === language;
                        const state = entry.body === null ? "Not written" : entry.is_active ? "In use" : "Switched off";
                        return (
                          <td key={language} className="py-3 px-space-md">
                            <button
                              type="button"
                              aria-pressed={isSelected}
                              onClick={() => setSelected({ key, language })}
                              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded border font-label-md cursor-pointer ${
                                isSelected ? "border-primary bg-primary/10 text-primary" : "border-outline-variant/40 hover:border-outline-variant"
                              } ${entry.body === null ? "text-tertiary" : "text-on-surface"}`}
                            >
                              <span className="material-symbols-outlined text-[15px]" aria-hidden="true">
                                {entry.body === null ? "edit_note" : entry.is_active ? "check_circle" : "block"}
                              </span>
                              {state}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <Editor
              key={`${selected.key}-${selected.language}`}
              catalogue={data}
              templateKey={selected.key}
              language={selected.language}
              canEdit={canEdit}
              onSaved={reload}
            />
          </>
        )}
      </PageBody>
    </>
  );
}
