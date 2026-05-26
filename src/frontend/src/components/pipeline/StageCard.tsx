import type { ReactNode } from "react";

export type StageStatus = "pending" | "running" | "complete" | "error";

interface StageCardProps {
  title: string;
  description: string;
  status: StageStatus;
  className?: string;
  children?: ReactNode;
}

const STATUS_LABELS: Record<StageStatus, string> = {
  pending: "Pending",
  running: "Running",
  complete: "Complete",
  error: "Error",
};

const STATUS_CLASSES: Record<StageStatus, string> = {
  pending: "border-border bg-bg-tertiary text-text-secondary",
  running: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
  complete: "border-accent-green/40 bg-accent-green/10 text-accent-green",
  error: "border-accent-red/40 bg-accent-red/10 text-accent-red",
};

export function StageCard({
  title,
  description,
  status,
  className = "",
  children,
}: StageCardProps) {
  return (
    <section
      className={`relative h-full overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-bg-secondary via-bg-secondary to-bg-tertiary p-5 shadow-[0_1px_0_rgba(255,255,255,0.03),0_18px_40px_rgba(0,0,0,0.18)] ${className}`}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />

      <header className="relative flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold tracking-tight text-text-primary">
            {title}
          </h3>
          <p className="text-xs leading-5 text-text-secondary">{description}</p>
        </div>

        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${STATUS_CLASSES[status]}`}
        >
          {status === "running" && (
            <span className="h-2 w-2 animate-spin rounded-full border border-current border-t-transparent" />
          )}
          {STATUS_LABELS[status]}
        </span>
      </header>

      {children && <div className="relative mt-4 text-sm text-text-primary">{children}</div>}
    </section>
  );
}
