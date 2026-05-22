import { Circle, Play, CheckCircle, AlertCircle, XCircle } from "lucide-react";
import type { RunStatus } from "../types";

interface RunStatusBadgeProps {
  status: RunStatus;
}

const STATUS_CONFIG: Record<
  RunStatus,
  {
    icon: typeof Circle;
    color: string;
    label: string;
    pulse?: boolean;
  }
> = {
  idle: { icon: Play, color: "text-text-secondary", label: "Standby" },
  streaming: {
    icon: Circle,
    color: "text-accent-cyan",
    label: "In Progress",
    pulse: true,
  },
  completed: {
    icon: CheckCircle,
    color: "text-accent-green",
    label: "Complete",
  },
  error: { icon: AlertCircle, color: "text-accent-red", label: "Error" },
  cancelled: {
    icon: XCircle,
    color: "text-accent-amber",
    label: "Cancelled",
  },
};

export function RunStatusBadge({ status }: RunStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <div className="flex items-center gap-1.5">
      <Icon
        className={`w-3 h-3 ${config.color} ${config.pulse ? "animate-pulse" : ""}`}
      />
      <span
        className={`text-[10px] font-bold uppercase tracking-widest ${config.color}`}
      >
        {config.label}
      </span>
    </div>
  );
}
