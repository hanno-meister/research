import type { VanguardStreamValues } from "../../../types";
import { useState } from "react";

interface ReviewStageProps {
  values: VanguardStreamValues | undefined;
}

export function ReviewStage({ values }: ReviewStageProps) {
  const [expanded, setExpanded] = useState(false);
  const reviews = Array.isArray(values?.research_reviews) ? values.research_reviews : [];

  const reviewCount = reviews.length;
  const currentReview = reviews.at(-1);
  const followUpTasks = getObjectArray(currentReview?.follow_up_tasks);
  const followUpCount = followUpTasks.length;
  const sufficient = currentReview?.sufficient === true;
  const assessment = getString(currentReview?.coverage_assessment);
  const sourceQuality = getString(currentReview?.source_quality_assessment);
  const contradictions = getStringArray(currentReview?.contradiction_notes).slice(0, 3);
  const weakFindings = getStringArray(currentReview?.weak_or_unsupported_findings).slice(0, 3);
  const requiredTopics = getStringArray(currentReview?.required_report_topics).slice(0, 5);
  const coverageGaps = getStringArray(currentReview?.coverage_gaps).slice(0, 4);
  const evidenceRequested = getObjectArray(currentReview?.evidence_requested).slice(0, 5);
  const followUps = followUpTasks.slice(0, 3);
  const warningText = !sufficient
    ? "Insufficiency warning: review still needs work."
    : followUpCount > 0
      ? "Follow-up tasks remain before the report is final."
      : "Review is sufficient.";

  if (reviewCount === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-bg-primary/50 p-4 text-text-secondary">
        Waiting for evidence review…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-xl border border-border bg-bg-primary/60 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-wide text-text-secondary">Latest review round</p>
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="rounded-full border border-border bg-bg-secondary px-3 py-1 text-[11px] font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            {expanded ? "Hide details" : "View details"}
          </button>
        </div>
        <p className="text-sm leading-6 text-text-primary">{warningText}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <StatusTile
            label="Sufficiency"
            value={sufficient ? "Ready" : "Needs work"}
            tone={sufficient ? "complete" : "running"}
          />
          <StatusTile
            label="Follow-ups"
            value={followUpCount === 0 ? "None" : String(followUpCount)}
            tone={followUpCount === 0 ? "complete" : "running"}
          />
        </div>
      </div>

      {expanded && currentReview && (
        <div className="space-y-4">
          <article className="rounded-xl border border-border bg-bg-primary/80 p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs uppercase tracking-wide text-text-secondary">
                Quality gate
              </p>
              <span className="rounded-full border border-border px-2 py-1 text-[11px] text-text-secondary">
                Round {getNumber(currentReview.round) ?? reviewCount} of {reviewCount}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-text-primary">
              {assessment ?? getString(currentReview.summary) ?? "Review summary unavailable."}
            </p>
          </article>

          {sourceQuality && (
            <article className="rounded-xl border border-accent-cyan/20 bg-accent-cyan/5 p-4">
              <p className="text-xs uppercase tracking-wide text-accent-cyan">
                Source quality
              </p>
              <p className="mt-2 text-sm leading-6 text-text-primary">{sourceQuality}</p>
            </article>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <ListPanel
              title="Coverage gaps"
              tone="amber"
              items={coverageGaps}
              empty="No coverage gaps flagged."
            />
            <ListPanel
              title="Weak claims"
              tone="amber"
              items={[...contradictions, ...weakFindings].slice(0, 5)}
              empty="No weak claims flagged."
            />
          </div>

          {requiredTopics.length > 0 && (
            <ListPanel
              title="Report must cover"
              tone="cyan"
              items={requiredTopics}
              empty="No required report topics listed."
            />
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <ObjectListPanel
              title="Evidence to inspect"
              tone="green"
              items={evidenceRequested}
              primaryKey="source_id"
              secondaryKey="reason"
              empty="No evidence reads requested."
            />
            <ObjectListPanel
              title="Repair tasks"
              tone="amber"
              items={followUps}
              primaryKey="objective"
              secondaryKey="rationale"
              empty="No repair tasks requested."
            />
          </div>
        </div>
      )}
    </div>
  );
}

function ListPanel({
  title,
  items,
  empty,
  tone,
}: {
  title: string;
  items: string[];
  empty: string;
  tone: "amber" | "cyan" | "green";
}) {
  return (
    <section className={`rounded-xl border p-4 ${getPanelTone(tone)}`}>
      <p className={`text-xs uppercase tracking-wide ${getTitleTone(tone)}`}>{title}</p>
      {items.length > 0 ? (
        <ul className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${getDotTone(tone)}`} />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-text-secondary">{empty}</p>
      )}
    </section>
  );
}

function ObjectListPanel({
  title,
  items,
  empty,
  tone,
  primaryKey,
  secondaryKey,
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  empty: string;
  tone: "amber" | "cyan" | "green";
  primaryKey: string;
  secondaryKey: string;
}) {
  return (
    <section className={`rounded-xl border p-4 ${getPanelTone(tone)}`}>
      <p className={`text-xs uppercase tracking-wide ${getTitleTone(tone)}`}>{title}</p>
      {items.length > 0 ? (
        <div className="mt-3 space-y-3">
          {items.map((item, index) => {
            const primary = getString(item[primaryKey]) ?? `Item ${index + 1}`;
            const secondary = getString(item[secondaryKey]);
            const key =
              getString(item.source_id) ?? getString(item.path) ?? `${primary}-${index}`;
            return (
              <article key={key} className="rounded-lg border border-border bg-bg-primary/70 p-3">
                <p className="text-sm font-medium text-text-primary">{primary}</p>
                {secondary && (
                  <p className="mt-1 text-xs leading-5 text-text-secondary">{secondary}</p>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <p className="mt-2 text-sm text-text-secondary">{empty}</p>
      )}
    </section>
  );
}

function StatusTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "pending" | "running" | "complete";
}) {
  const toneClasses: Record<typeof tone, string> = {
    pending: "border-border bg-bg-primary/70 text-text-secondary",
    running: "border-accent-amber/20 bg-accent-amber/10 text-accent-amber",
    complete: "border-accent-green/20 bg-accent-green/10 text-accent-green",
  };

  return (
    <div className={`rounded-xl border p-3 ${toneClasses[tone]}`}>
      <div className="text-xs uppercase tracking-wide opacity-80">{label}</div>
      <div className="mt-1 text-base font-medium text-text-primary">{value}</div>
    </div>
  );
}

function getString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function getNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function getStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim()))
    : [];
}

function getObjectArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function getPanelTone(tone: "amber" | "cyan" | "green") {
  const tones = {
    amber: "border-accent-amber/20 bg-accent-amber/5",
    cyan: "border-accent-cyan/20 bg-accent-cyan/5",
    green: "border-accent-green/20 bg-accent-green/5",
  };
  return tones[tone];
}

function getTitleTone(tone: "amber" | "cyan" | "green") {
  const tones = {
    amber: "text-accent-amber",
    cyan: "text-accent-cyan",
    green: "text-accent-green",
  };
  return tones[tone];
}

function getDotTone(tone: "amber" | "cyan" | "green") {
  const tones = {
    amber: "bg-accent-amber/70",
    cyan: "bg-accent-cyan/70",
    green: "bg-accent-green/70",
  };
  return tones[tone];
}
