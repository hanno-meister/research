import { CheckCircle2, Circle, Clock, Loader2, XCircle } from "lucide-react";
import { useResearchStore } from "../store/researchStore";

interface TodoPanelProps {
  todos: Array<{
    id?: string;
    content?: string;
    task?: string;
    title?: string;
    status?: string;
  }>;
}

function normalizeStatus(raw: string): string {
  return raw.replace(/_/g, "-");
}

export function TodoPanel({ todos }: TodoPanelProps) {
  const { runStatus } = useResearchStore();
  const isCancelled = runStatus === "cancelled";

  const completed = todos.filter(
    (t) => normalizeStatus(t.status ?? "") === "completed",
  ).length;
  const progress = todos.length > 0 ? (completed / todos.length) * 100 : 0;

  return (
    <div className="space-y-6">
      <div className="bg-bg-secondary p-4 rounded-xl border border-border space-y-3">
        <div className="flex justify-between items-end">
          <span className="text-sm font-medium text-text-secondary">
            Mission Progress
          </span>
          <span className="text-2xl font-bold text-accent-cyan">
            {Math.round(progress)}%
          </span>
        </div>
        <div className="h-2 bg-bg-primary rounded-full overflow-hidden border border-border">
          <div
            className="h-full bg-accent-cyan shadow-[0_0_12px_rgba(6,182,212,0.4)] transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-text-secondary font-mono">
          <span>{completed} COMPLETED</span>
          <span>{todos.length} TOTAL</span>
        </div>
      </div>

      <div className="space-y-2">
        {todos.map((todo, idx) => {
          const label = todo.content ?? todo.task ?? todo.title ?? "Unnamed task";
          const rawStatus = normalizeStatus(todo.status ?? "pending");
          // If the run was cancelled, tasks that were in-progress are treated as cancelled
          const status =
            isCancelled && rawStatus === "in-progress"
              ? "cancelled"
              : rawStatus;

          return (
            <div
              key={todo.id ?? idx}
              className={`flex items-start gap-4 p-4 rounded-xl border transition-all ${
                status === "completed"
                  ? "bg-accent-green/5 border-accent-green/10 opacity-70"
                  : status === "in-progress"
                    ? "bg-accent-cyan/5 border-accent-cyan/20 ring-1 ring-accent-cyan/20"
                    : status === "cancelled"
                      ? "bg-accent-amber/5 border-accent-amber/20"
                      : "bg-bg-secondary border-border"
              }`}
            >
              <div className="mt-0.5">
                {status === "completed" ? (
                  <CheckCircle2 className="w-5 h-5 text-accent-green" />
                ) : status === "in-progress" ? (
                  <Loader2 className="w-5 h-5 text-accent-cyan animate-spin" />
                ) : status === "cancelled" ? (
                  <XCircle className="w-5 h-5 text-accent-amber" />
                ) : (
                  <Circle className="w-5 h-5 text-text-secondary/30" />
                )}
              </div>
              <div className="flex-1">
                <p
                  className={`text-sm ${status === "completed" ? "line-through text-text-secondary/50" : status === "cancelled" ? "text-text-secondary/60" : "text-text-primary"}`}
                >
                  {label}
                </p>
                <span
                  className={`inline-block mt-2 text-[10px] px-2 py-0.5 rounded uppercase tracking-tighter font-bold ${
                    status === "completed"
                      ? "bg-accent-green/10 text-accent-green"
                      : status === "in-progress"
                        ? "bg-accent-cyan/10 text-accent-cyan"
                        : status === "cancelled"
                          ? "bg-accent-amber/10 text-accent-amber"
                          : "bg-text-secondary/10 text-text-secondary"
                  }`}
                >
                  {status}
                </span>
              </div>
            </div>
          );
        })}

        {todos.length === 0 && (
          <div className="text-center py-12 text-text-secondary/50">
            <Clock className="w-12 h-12 mx-auto mb-4 opacity-20" />
            <p className="text-sm">Waiting for research plan...</p>
          </div>
        )}
      </div>
    </div>
  );
}
