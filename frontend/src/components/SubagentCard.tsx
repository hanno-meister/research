import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle2,
  AlertCircle,
  XCircle,
} from "lucide-react";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { useResearchStore } from "../store/researchStore";
import type { SubagentInfo } from "../types";

interface SubagentCardProps {
  agent: SubagentInfo;
}

function formatAgentType(value: string) {
  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function SubagentCard({ agent }: SubagentCardProps) {
  const { runStatus } = useResearchStore();
  const isCancelled = runStatus === "cancelled";

  const isActive =
    !isCancelled &&
    (agent.status === "running" || agent.status === "pending" || !agent.status);
  // An agent was mid-flight when the run was cancelled
  const wasInterrupted =
    isCancelled &&
    (agent.status === "running" || agent.status === "pending" || !agent.status);

  const [manuallyExpanded, setManuallyExpanded] = useState(false);
  const [promptExpanded, setPromptExpanded] = useState(false);

  const resolvedToolCall = agent.toolCall ?? agent.toolCalls?.[0];
  const agentType = formatAgentType(
    resolvedToolCall?.args?.subagent_type ?? agent.name ?? "Sub-Agent",
  );
  const subtitle = resolvedToolCall?.args?.description?.trim();
  const title = agentType;
  const isLongTitle = !!subtitle;
  const expanded = isActive || manuallyExpanded;
  const contentId = `agent-content-${agent.id}`;

  let displayContent: string | undefined;
  if (agent.status === "complete") {
    displayContent = agent.result;
    if (!displayContent && agent.messages?.length) {
      const lastThinkMsg = [...agent.messages]
        .reverse()
        .find((m) => m.type === "tool" && m.name === "think_tool");
      if (lastThinkMsg) displayContent = lastThinkMsg.content;
    }
  } else if (agent.messages && agent.messages.length > 0) {
    const lastAI = [...agent.messages]
      .reverse()
      .find((m) => m.type === "ai" && m.content);
    const lastThink = [...agent.messages]
      .reverse()
      .find((m) => m.type === "tool" && m.name === "think_tool");
    displayContent = lastAI?.content ?? lastThink?.content;
  }
  const finalContent =
    displayContent || (isActive ? "Starting..." : undefined);

  // Status badge display values
  const statusBadge = wasInterrupted
    ? { label: "Cancelled", cls: "bg-accent-amber/10 text-accent-amber" }
    : isActive
      ? { label: "Processing", cls: "bg-accent-cyan/10 text-accent-cyan" }
      : agent.status === "error"
        ? { label: "Error", cls: "bg-accent-red/10 text-accent-red" }
        : { label: "Finished", cls: "bg-accent-green/10 text-accent-green" };

  return (
    <div
      className={`bg-bg-secondary/50 border rounded-xl overflow-hidden transition-all ${
        wasInterrupted
          ? "border-accent-amber/30 hover:border-accent-amber/50"
          : "border-border hover:border-accent-cyan/30"
      }`}
    >
      <button
        onClick={() => setManuallyExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={contentId}
        className="w-full px-4 py-3 flex items-center justify-between"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="relative">
            {wasInterrupted ? (
              <XCircle className="w-4 h-4 text-accent-amber" />
            ) : isActive ? (
              <Loader2 className="w-4 h-4 text-accent-cyan animate-spin" />
            ) : agent.status === "error" ? (
              <AlertCircle className="w-4 h-4 text-accent-red" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-accent-green" />
            )}
            {isActive && (
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-accent-cyan rounded-full animate-ping" />
            )}
          </div>
          <div className="flex min-w-0 flex-col items-start">
            <span
              className={`text-sm font-semibold text-text-primary text-left ${
                promptExpanded ? "" : "line-clamp-2"
              }`}
            >
              {title}
            </span>
            <div className="mt-1 flex items-center gap-2 text-[10px] text-text-secondary/70">
              <span className="truncate">{agent.id}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full ${statusBadge.cls}`}
          >
            {statusBadge.label}
          </span>
          {expanded ? (
            <ChevronUp size={14} className="text-text-secondary" />
          ) : (
            <ChevronDown size={14} className="text-text-secondary" />
          )}
        </div>
      </button>

      {isLongTitle && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setPromptExpanded(!promptExpanded);
          }}
          className="w-full px-4 pb-1 text-left text-[10px] text-accent-cyan/70 hover:text-accent-cyan transition-colors"
        >
          {promptExpanded ? "Show less ↑" : "Show prompt ↓"}
        </button>
      )}

      {expanded && finalContent && (
        <div id={contentId} className="px-4 pb-4">
          {subtitle && promptExpanded && (
            <div className="mb-3 p-3 bg-bg-primary/60 rounded-lg border border-border text-xs text-text-secondary/80 leading-relaxed whitespace-pre-wrap">
              <span className="block text-[10px] uppercase tracking-wider text-text-secondary/40 mb-1">
                Full Task Prompt
              </span>
              {subtitle}
            </div>
          )}
          <div className="p-3 bg-bg-primary rounded-lg border border-border text-xs text-text-secondary leading-relaxed">
            <MarkdownRenderer content={finalContent} />
            {isActive && (
              <span className="inline-block w-1.5 h-3.5 ml-1 bg-accent-cyan/50 animate-pulse align-middle" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
