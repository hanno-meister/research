import type { VanguardStreamValues } from "../../../types";

interface PlanStageProps {
  values: VanguardStreamValues | undefined;
}

export function PlanStage({ values }: PlanStageProps) {
  const tasks = Array.isArray(values?.research_tasks) ? values.research_tasks : [];

  if (tasks.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-bg-primary/50 p-4 text-text-secondary">
        Waiting for planned research tasks…
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="space-y-3">
        {tasks.map((task, index) => {
          const id = typeof task.id === "string" ? task.id : null;
          const objective = getTaskText(task, "objective");
          const rationale = getTaskText(task, "rationale");
          const title = objective ?? getTaskText(task, "title") ?? `Task ${index + 1}`;
          const description =
            rationale ??
            getTaskText(task, "description") ??
            getTaskText(task, "focus") ??
            getTaskText(task, "expected_output") ??
            "Research task details are pending.";
          const effort = getTaskText(task, "effort");
          const questionCount = getArrayLength(task.key_questions);
          const termCount = getArrayLength(task.target_terms);
          const boundaryCount = getArrayLength(task.boundaries);
          const dependencyCount = getArrayLength(task.depends_on);
          const metadata = [
            effort && `${effort} effort`,
            questionCount > 0 && `${questionCount} questions`,
            termCount > 0 && `${termCount} terms`,
            boundaryCount > 0 && `${boundaryCount} boundaries`,
            dependencyCount > 0 && `${dependencyCount} dependencies`,
          ].filter(Boolean);
          const status = typeof task.status === "string" ? task.status : null;
          const priority = typeof task.priority === "string" ? task.priority : null;
          const label = effort ?? priority ?? status;

          return (
            <article
              key={id ?? `${title}-${index}`}
              className="rounded-xl border border-border bg-bg-primary/80 p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-medium uppercase tracking-wide text-accent-cyan">
                      Task {index + 1}
                    </span>
                    {label && (
                      <span className="rounded-full border border-border bg-bg-tertiary px-2 py-0.5 text-[10px] uppercase tracking-wide text-text-secondary">
                        {label}
                      </span>
                    )}
                  </div>
                  <h4 className="text-sm font-medium leading-6 text-text-primary">
                    {title}
                  </h4>
                  <p className="text-sm leading-6 text-text-secondary">
                    {description}
                  </p>
                  {metadata.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {metadata.map((item) => (
                        <span
                          key={String(item)}
                          className="rounded-md border border-border bg-bg-secondary px-2 py-1 text-[11px] text-text-secondary"
                        >
                          {item}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function getTaskText(task: Record<string, unknown>, key: string): string | null {
  const value = task[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function getArrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}
