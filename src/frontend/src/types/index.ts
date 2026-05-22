export interface ResearchInput {
  lance_name: string;
  lance_description: string;
  start_date: string;
  end_date: string;
  query_domains: string[];
}

export interface VanguardStreamValues {
  research_intent?: string;
  selected_lance?: Record<string, string>;
  allowed_domains?: string[];
  start_date?: string;
  end_date?: string;
  research_brief?: string;
  research_tasks?: Array<Record<string, unknown>>;
  research_findings?: Array<Record<string, unknown>>;
  research_reviews?: Array<Record<string, unknown>>;
  report_bundle?: Record<string, unknown>;
  final_report?: string;
  report_status?: string;
  [key: string]: unknown;
}

export type RunStatus =
  | "idle"
  | "streaming"
  | "completed"
  | "error"
  | "cancelled";

export type StreamMessageType = "human" | "ai" | "tool" | "system" | string;

export interface StreamMessage {
  id?: string;
  type: StreamMessageType;
  content: string;
  name?: string;
  tool_calls?: Array<{
    name: string;
    args?: Record<string, unknown>;
  }>;
}
