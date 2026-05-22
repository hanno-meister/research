import { useResearchStore } from "../store/researchStore";
import { MessageList } from "./MessageList";
import { TodoPanel } from "./TodoPanel";
import { FinalReportPanel } from "./FinalReportPanel";
import { RunStatusBadge } from "./RunStatus";
import {
  Square,
  LayoutDashboard,
  ClipboardList,
  FileText,
  Settings2,
  PlusCircle,
} from "lucide-react";
import type { RightPanelTab, StreamMessage, SubagentInfo, VanguardStreamValues } from "../types";

interface StreamData {
  messages: StreamMessage[];
  subagents: Map<string, unknown>;
  values: VanguardStreamValues | undefined;
  isLoading: boolean;
  isSubmittingFeedback: boolean;
  getSubagentsByMessage: (id: string) => SubagentInfo[];
  stopResearch: () => Promise<void>;
  submitFeedback: (feedback: string) => Promise<boolean>;
}

interface DashboardProps {
  stream: StreamData;
}

const TABS: Array<{
  id: RightPanelTab;
  label: string;
  icon: typeof ClipboardList;
}> = [
  { id: "tasks", label: "Tasks", icon: ClipboardList },
  { id: "request", label: "Request", icon: Settings2 },
  { id: "report", label: "Report", icon: FileText },
];

export function Dashboard({ stream }: DashboardProps) {
  const { activeTab, setActiveTab, runStatus, lastInput, reset, finalReport } =
    useResearchStore();

  const researchTasks = Array.isArray(stream.values?.research_tasks)
    ? stream.values.research_tasks
    : [];
  const hasFinalReport = Boolean(stream.values?.final_report);
  const todos = researchTasks.length
    ? researchTasks.map((task, index) => ({
        id: String(task.id ?? task.task_id ?? index),
        title: String(task.title ?? task.research_topic ?? task.task ?? `Research task ${index + 1}`),
        content: String(task.description ?? task.question ?? task.objective ?? "Derived from the v3 research plan."),
        status: hasFinalReport ? "completed" : index === 0 ? "in_progress" : "pending",
      }))
    : [
        {
          id: "placeholder-plan",
          title: "Planning research tasks…",
          content: "The v3 graph exposes planned tasks after the planning node completes.",
          status: stream.isLoading ? "in_progress" : "pending",
        },
        {
          id: "placeholder-subagents",
          title: "Subagent stream placeholder",
          content: "No per-subagent stream is available for the v3 graph yet.",
          status: "pending",
        },
      ];

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <header className="h-16 border-b border-border bg-bg-secondary flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-4">
          <div className="p-1.5 bg-accent-cyan/10 rounded-lg">
            <LayoutDashboard className="w-5 h-5 text-accent-cyan" />
          </div>
          <div>
            <h2 className="font-semibold text-sm tracking-tight">
              {lastInput?.lance_name ?? "Research Mission"}
            </h2>
            <RunStatusBadge status={runStatus} />
          </div>
        </div>

        <div className="flex items-center gap-3">
          {stream.isLoading && (
            <button
              type="button"
              onClick={stream.stopResearch}
              className="flex items-center gap-2 px-3 py-1.5 bg-accent-red/10 text-accent-red hover:bg-accent-red/20 rounded-md transition-colors text-xs font-medium border border-accent-red/20 cursor-pointer"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
              Stop Run
            </button>
          )}
          <button
            type="button"
            onClick={reset}
            className="p-2 hover:bg-bg-tertiary rounded-lg transition-colors text-text-secondary cursor-pointer"
            title="New Research"
            aria-label="New Research"
          >
            <PlusCircle className="w-5 h-5" />
          </button>
        </div>
      </header>

      <main className="flex flex-1 overflow-hidden">
        <div className="w-1/2 flex flex-col border-r border-border bg-bg-primary">
          <MessageList
            messages={stream.messages}
            values={stream.values}
            getSubagentsByMessage={stream.getSubagentsByMessage}
          />
        </div>

        <div className="w-1/2 flex flex-col bg-bg-primary">
          <div className="flex border-b border-border bg-bg-secondary px-2">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-6 py-4 text-xs font-medium transition-all relative cursor-pointer ${
                  activeTab === tab.id
                    ? "text-accent-cyan"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
                {activeTab === tab.id && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent-cyan shadow-[0_0_8px_rgba(6,182,212,0.5)]" />
                )}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {activeTab === "tasks" && <TodoPanel todos={todos} />}
            {activeTab === "request" && (
              <div className="space-y-4">
                <h3 className="text-lg font-medium">Mission Parameters</h3>
                <pre className="p-4 bg-bg-secondary rounded-lg border border-border text-xs overflow-auto text-accent-cyan/80">
                  {JSON.stringify(lastInput, null, 2)}
                </pre>
              </div>
            )}
            {activeTab === "report" && (
              <FinalReportPanel
                lastInput={lastInput}
                report={finalReport}
                isLoading={stream.isLoading || stream.isSubmittingFeedback}
                onSubmitFeedback={stream.submitFeedback}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
