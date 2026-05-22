import type { VanguardStreamValues } from "../../../types";
import { useState } from "react";

interface ResearchStageProps {
  values: VanguardStreamValues | undefined;
}

export function ResearchStage({ values }: ResearchStageProps) {
  const [expanded, setExpanded] = useState(false);
  const researchFindings = Array.isArray(values?.research_findings)
    ? values.research_findings
    : [];
  const researchTasks = Array.isArray(values?.research_tasks)
    ? values.research_tasks
    : [];
  const findings = researchFindings.length;
  const sources = Array.isArray(values?.research_sources)
    ? values.research_sources.length
    : 0;
  const plannedTaskIds = researchTasks
    .map((task) => getString(task.id))
    .filter((taskId): taskId is string => Boolean(taskId));
  const plannedTaskIdSet = new Set(plannedTaskIds);
  const coveredPlannedTaskIds = new Set(
    researchFindings
      .map((finding) => getString(finding.task_id))
      .filter(
        (taskId): taskId is string =>
          typeof taskId === "string" && plannedTaskIdSet.has(taskId),
      ),
  );
  const totalTaskCount = plannedTaskIds.length;

  const representativeFindings = firstFindingPerPlannedTask(
    researchFindings,
    plannedTaskIds,
  ).slice(0, 5);

  if (findings === 0 && sources === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-bg-primary/50 p-4 text-text-secondary">
        Waiting for research findings…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-xl border border-border bg-bg-primary/60 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-wide text-text-secondary">Research summary</p>
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="rounded-full border border-border bg-bg-secondary px-3 py-1 text-[11px] font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            {expanded ? "Hide details" : "View details"}
          </button>
        </div>
        <p className="text-sm leading-6 text-text-primary">
          {findings} finding{findings === 1 ? "" : "s"} across {sources} source{sources === 1 ? "" : "s"}; {totalTaskCount > 0 ? `${coveredPlannedTaskIds.size}/${totalTaskCount}` : coveredPlannedTaskIds.size} planned task{coveredPlannedTaskIds.size === 1 ? "" : "s"} covered.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="Findings" value={findings} />
          <Metric label="Sources" value={sources} />
          <Metric
            label="Tasks covered"
            value={totalTaskCount > 0 ? `${coveredPlannedTaskIds.size}/${totalTaskCount}` : coveredPlannedTaskIds.size}
          />
        </div>
      </div>

      {expanded && representativeFindings.length > 0 && (
        <section className="rounded-xl border border-accent-cyan/20 bg-accent-cyan/5 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-wide text-accent-cyan">
              Most relevant findings by planned task
            </p>
            <p className="text-xs text-text-secondary">
              Showing {representativeFindings.length} of {coveredPlannedTaskIds.size}
            </p>
          </div>
          <div className="mt-3 space-y-3">
            {representativeFindings.map((finding, index) => (
              <FindingPreview
                key={getFindingKey(finding, index)}
                finding={finding}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-border bg-bg-primary/80 p-3">
      <div className="text-lg font-semibold text-text-primary">{value}</div>
      <div className="text-xs text-text-secondary">{label}</div>
    </div>
  );
}

function FindingPreview({ finding }: { finding: Record<string, unknown> }) {
  const summary = getString(finding.summary) ?? getString(finding.note) ?? "Finding preview unavailable.";
  const taskId = getString(finding.task_id);
  const sourceIds = Array.isArray(finding.source_ids)
    ? finding.source_ids.filter((item): item is string => typeof item === "string")
    : [];

  return (
    <article className="rounded-lg border border-border bg-bg-primary/70 p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-secondary">
          {taskId ? taskId.replace("task-", "Task ") : "Finding"}
        </p>
        {sourceIds.length > 0 && (
          <span className="text-[11px] text-text-secondary">
            {sourceIds.length} sources
          </span>
        )}
      </div>
      <p className="mt-2 text-sm leading-6 text-text-primary">{summary}</p>
    </article>
  );
}

function firstFindingPerPlannedTask(
  findings: Array<Record<string, unknown>>,
  plannedTaskIds: string[],
) {
  const seen = new Set<string>();
  const representative: Array<Record<string, unknown>> = [];
  const plannedTaskIdSet = new Set(plannedTaskIds);

  for (const finding of findings) {
    const taskId = getString(finding.task_id);
    if (!taskId || !plannedTaskIdSet.has(taskId)) continue;
    if (seen.has(taskId)) continue;
    seen.add(taskId);
    representative.push(finding);
  }

  return representative;
}

function getString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function getFindingKey(finding: Record<string, unknown>, index: number): string {
  const taskId = getString(finding.task_id) ?? "finding";
  const summary = getString(finding.summary) ?? String(index);
  return `${taskId}-${summary.slice(0, 48)}`;
}
