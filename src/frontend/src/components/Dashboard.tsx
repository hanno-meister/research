import { LayoutDashboard, PlusCircle, Square } from "lucide-react";
import { MockPipelineView } from "../mocks/pipeline/MockPipelineView";
import { useResearchStore } from "../store/researchStore";
import type { VanguardStreamValues } from "../types";
import { PipelineView } from "./pipeline/PipelineView";

interface DashboardProps {
  stream: {
    values: VanguardStreamValues | undefined;
    isLoading: boolean;
    stopResearch: () => Promise<void>;
  };
}

const USE_DEV_UI_MOCKS =
  import.meta.env.DEV && import.meta.env.VITE_DEV_UI_MOCKS === "true";

export function Dashboard({ stream }: DashboardProps) {
  const { lastInput, reset, runStatus } = useResearchStore();

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-bg-secondary px-6">
        <div className="flex items-center gap-4">
          <div className="rounded-lg bg-accent-cyan/10 p-1.5">
            <LayoutDashboard className="h-5 w-5 text-accent-cyan" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">
              {lastInput?.lance_name ?? "Research Mission"}
            </h2>
            <p className="text-xs capitalize text-text-secondary">
              {runStatus}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {stream.isLoading && (
            <button
              type="button"
              onClick={stream.stopResearch}
              className="flex cursor-pointer items-center gap-2 rounded-md border border-accent-red/20 bg-accent-red/10 px-3 py-1.5 text-xs font-medium text-accent-red transition-colors hover:bg-accent-red/20"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
              Stop Run
            </button>
          )}
          <button
            type="button"
            onClick={reset}
            className="cursor-pointer rounded-lg p-2 text-text-secondary transition-colors hover:bg-bg-tertiary"
            title="New Research"
            aria-label="New Research"
          >
            <PlusCircle className="h-5 w-5" />
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto bg-bg-primary p-6">
        <div className="h-full w-full">
          {USE_DEV_UI_MOCKS ? (
            <MockPipelineView />
          ) : (
            <PipelineView values={stream.values} isLoading={stream.isLoading} />
          )}
        </div>
      </main>
    </div>
  );
}
