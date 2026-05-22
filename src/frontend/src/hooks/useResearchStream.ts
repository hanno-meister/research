import { useStream } from "@langchain/react";
import { useResearchStore } from "../store/researchStore";
import type { ResearchInput, VanguardStreamValues } from "../types";

const AGENT_URL =
  (import.meta.env.VITE_LANGGRAPH_API_URL as string | undefined) ??
  `${window.location.origin}/api`;

const ASSISTANT_ID =
  (import.meta.env.VITE_LANGGRAPH_ASSISTANT_ID as string | undefined) ??
  "agent";

type RawStreamMessage = {
  id?: string;
  content?: unknown;
  getType?: () => string;
};

function buildResearchIntent(input: ResearchInput): string {
  return [
    "Create a technical trend-scouting report.",
    `Research Mission: ${input.lance_name}`,
    input.lance_description.trim() &&
      `Mission Brief: ${input.lance_description.trim()}`,
  ]
    .filter(Boolean)
    .join("\n\n");
}

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

export function normalizeStreamMessage(message: RawStreamMessage) {
  return {
    id: message.id,
    type: message.getType?.() ?? "ai",
    content: normalizeContent(message.content),
  };
}

export function extractFinalReport(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;

  const root = value as Record<string, unknown>;
  const report =
    typeof root.final_report === "string"
      ? root.final_report
      : root.values &&
          typeof root.values === "object" &&
          !Array.isArray(root.values) &&
          typeof (root.values as Record<string, unknown>).final_report === "string"
        ? String((root.values as Record<string, unknown>).final_report)
        : null;

  return report && report.trim() ? report : null;
}

export function useResearchStream() {
  const { runStatus, startRun, completeRun, cancelRun, failRun } =
    useResearchStore();

  const stream = useStream<VanguardStreamValues>({
    apiUrl: AGENT_URL,
    assistantId: ASSISTANT_ID,
  });

  async function startResearch(input: ResearchInput) {
    startRun(input);

    try {
      await stream.submit(
        {
          research_intent: buildResearchIntent(input),
          selected_lance: {
            name: input.lance_name,
            description: input.lance_description,
          },
          allowed_domains:
            input.query_domains.length > 0 ? input.query_domains : undefined,
          start_date: input.start_date || undefined,
          end_date: input.end_date || undefined,
        },
        {
          streamMode: ["values", "messages"],
          onDisconnect: "cancel",
        },
      );

      completeRun(extractFinalReport(stream.values));
    } catch (error) {
      failRun(
        error instanceof Error ? error.message : "Unable to start research.",
      );
    }
  }

  async function stopResearch() {
    cancelRun();
    await stream.stop();
  }

  return {
    values: stream.values,
    messages: stream.messages.map((message) =>
      normalizeStreamMessage(message as RawStreamMessage),
    ),
    isLoading: stream.isLoading && runStatus === "streaming",
    startResearch,
    stopResearch,
  };
}
