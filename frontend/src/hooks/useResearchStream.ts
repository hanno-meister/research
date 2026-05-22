import { useStream } from "@langchain/react";
import { useState } from "react";
import { useResearchStore } from "../store/researchStore";
import type { ResearchInput, StreamMessage } from "../types";

const AGENT_URL =
  (import.meta.env.VITE_LANGGRAPH_API_URL as string | undefined) ??
  `${window.location.origin}/api`;
const ASSISTANT_ID =
  (import.meta.env.VITE_LANGGRAPH_ASSISTANT_ID as string | undefined) ??
  "agent";

// The Python backend uses deepagents (create_deep_agent), which supports
// filterSubagentMessages, subagents, and getSubagentsByMessage at runtime.
// Since we can't import `typeof agent` from a Python backend, we extend
// the base options/return types with the deep agent features.
interface DeepAgentStreamOptions {
  apiUrl: string;
  assistantId: string;
  onCreated?: (run: { run_id?: string; thread_id?: string }) => void;
  onFinish?: (state: unknown) => void;
  onStop?: () => void;
  onError?: (error: unknown) => void;
}

function extractReportBundleMarkdown(bundle: unknown): string | null {
  if (!bundle || typeof bundle !== "object" || Array.isArray(bundle)) return null;
  const record = bundle as Record<string, unknown>;
  for (const key of ["markdown", "report", "summary", "executive_summary"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

interface SubagentStream {
  id: string;
  name?: string;
  status: "pending" | "running" | "complete" | "error";
  messages: Array<{ id?: string; type: string; content: string; name?: string }>;
  result?: string;
  toolCall?: { args?: { subagent_type?: string; description?: string } };
  toolCalls?: Array<{
    args?: { subagent_type?: string; description?: string };
  }>;
}

type RawStreamMessage = {
  id?: string;
  content?: unknown;
  name?: unknown;
  tool_calls?: unknown;
  toolCalls?: unknown;
  getType: () => string;
};

function normalizeContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (content == null) return "";

  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (
          part &&
          typeof part === "object" &&
          "text" in part &&
          typeof part.text === "string"
        ) {
          return part.text;
        }
        return JSON.stringify(part);
      })
      .join("");
  }

  return JSON.stringify(content);
}

function normalizeToolCalls(value: unknown): StreamMessage["tool_calls"] {
  if (!Array.isArray(value)) return undefined;

  return value
    .filter(
      (toolCall): toolCall is { name: string; args?: Record<string, unknown> } =>
        !!toolCall &&
        typeof toolCall === "object" &&
        "name" in toolCall &&
        typeof toolCall.name === "string",
    )
    .map((toolCall) => ({
      name: toolCall.name,
      args:
        "args" in toolCall &&
        toolCall.args &&
        typeof toolCall.args === "object" &&
        !Array.isArray(toolCall.args)
          ? (toolCall.args as Record<string, unknown>)
          : undefined,
    }));
}

export function normalizeStreamMessage(msg: RawStreamMessage): StreamMessage {
  return {
    id: msg.id,
    type: msg.getType(),
    content: normalizeContent(msg.content),
    name: typeof msg.name === "string" ? msg.name : undefined,
    tool_calls: normalizeToolCalls(msg.tool_calls ?? msg.toolCalls),
  };
}

function buildResearchPrompt(input: ResearchInput) {
  const constraintLines: string[] = [];

  if (input.query_domains.length > 0) {
    constraintLines.push(
      `- Restrict research to these domains only: ${input.query_domains.join(", ")}`,
    );
  }

  if (input.start_date && input.end_date) {
    constraintLines.push(
      `- Only use sources published between ${input.start_date} and ${input.end_date}`,
    );
  } else if (input.start_date) {
    constraintLines.push(
      `- Only use sources published on or after ${input.start_date}`,
    );
  } else if (input.end_date) {
    constraintLines.push(
      `- Only use sources published on or before ${input.end_date}`,
    );
  }

  return [
    `Research Mission: ${input.lance_name}`,
    input.lance_description.trim() &&
      `Mission Brief: ${input.lance_description.trim()}`,
    constraintLines.length > 0 &&
      ["Research Constraints:", ...constraintLines].join("\n"),
  ]
    .filter(Boolean)
    .join("\n\n");
}

export function extractFinalReport(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;

  const root = value as Record<string, unknown>;
  const direct = root.final_report;
  const nested =
    root.values &&
    typeof root.values === "object" &&
    !Array.isArray(root.values)
      ? (root.values as Record<string, unknown>).final_report
      : undefined;

  const bundle =
    root.report_bundle ??
    (root.values && typeof root.values === "object" && !Array.isArray(root.values)
      ? (root.values as Record<string, unknown>).report_bundle
      : undefined);
  const report =
    typeof direct === "string"
      ? direct
      : typeof nested === "string"
        ? nested
        : extractReportBundleMarkdown(bundle);
  return typeof report === "string" && report.trim() ? report : null;
}

export function useResearchStream() {
  const {
    runStatus,
    startRun,
    completeRun,
    cancelRun,
    failRun,
    setError,
    feedbackRunId,
    setFeedbackRunId,
  } = useResearchStore();
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  const stream = useStream(
    {
      apiUrl: AGENT_URL,
      assistantId: ASSISTANT_ID,
      onCreated: (run) => {
        if (typeof run.run_id === "string" && run.run_id.length > 0) {
          setFeedbackRunId(run.run_id);
        }
      },
      onFinish: (state: unknown) => {
        completeRun(extractFinalReport(state));
      },
      onStop: () => {
        cancelRun();
      },
      onError: (error: unknown) => {
        if (useResearchStore.getState().runStatus === "cancelled") return;

        failRun(
          error instanceof Error ? error.message : "Research stream failed.",
        );
      },
    } as DeepAgentStreamOptions & Record<string, unknown>,
  );

  // Runtime: stream has .subagents (Map) and .getSubagentsByMessage(id)
  const streamAny = stream as typeof stream & {
    subagents: Map<string, SubagentStream>;
    getSubagentsByMessage: (id: string) => SubagentStream[];
  };

  const startResearch = async (input: ResearchInput) => {
    startRun(input);

    try {
      await stream.submit(
        {
          research_intent: buildResearchPrompt(input),
          selected_lance:
            input.selected_lance ??
            (input.lance_name
              ? {
                  name: input.lance_name,
                  description: input.lance_description,
                }
              : undefined),
          allowed_domains:
            input.query_domains.length > 0 ? input.query_domains : undefined,
          start_date: input.start_date || undefined,
          end_date: input.end_date || undefined,
        },
        {
          streamMode: ["values"],
          onDisconnect: "cancel",
        },
      );
    } catch (error) {
      failRun(
        error instanceof Error ? error.message : "Unable to start research.",
      );
    }
  };

  const submitFeedback = async (feedback: string) => {
    const trimmedFeedback = feedback.trim();
    if (!trimmedFeedback) return false;

    setIsSubmittingFeedback(true);
    setError("Feedback capture is visible but not connected yet.");
    setIsSubmittingFeedback(false);
    void trimmedFeedback;
    void feedbackRunId;
    return false;
  };

  const stopResearch = async () => {
    if (!stream.isLoading || runStatus !== "streaming") return;

    cancelRun();

    const clearQueuedRuns =
      typeof stream.queue?.clear === "function"
        ? stream.queue.clear()
        : Promise.resolve();
    const results = await Promise.allSettled([stream.stop(), clearQueuedRuns]);
    const stopError = results.find((result) => result.status === "rejected");

    if (stopError?.status === "rejected") {
      failRun(
        stopError.reason instanceof Error
          ? stopError.reason.message
          : "Unable to cancel research run.",
      );
    }
  };

  return {
    messages: stream.messages.map((msg) =>
      normalizeStreamMessage(msg as RawStreamMessage),
    ),
    subagents: streamAny.subagents ?? new Map(),
    values: stream.values,
    isLoading: stream.isLoading && runStatus === "streaming",
    isSubmittingFeedback,
    getSubagentsByMessage: (id: string) =>
      streamAny.getSubagentsByMessage?.(id) ?? [],
    startResearch,
    stopResearch,
    submitFeedback,
  };
}
