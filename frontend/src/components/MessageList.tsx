import { useEffect, useRef } from "react";
import { Message } from "./Message";
import type { StreamMessage, SubagentInfo, VanguardStreamValues } from "../types";

interface MessageListProps {
  messages: StreamMessage[];
  values?: VanguardStreamValues;
  getSubagentsByMessage: (msgId: string) => SubagentInfo[];
}

export function MessageList({
  messages,
  values,
  getSubagentsByMessage,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const lastMessage = messages[messages.length - 1];

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 80) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lastMessage?.id, lastMessage?.content]);

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto p-6 space-y-8 scroll-smooth"
    >
      {messages.map((msg, idx) => (
        <Message
          key={msg.id ?? idx}
          message={msg}
          subagents={msg.id ? getSubagentsByMessage(msg.id) : []}
        />
      ))}

      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-text-secondary space-y-4">
          <div className="w-12 h-12 border-2 border-dashed border-border rounded-xl flex items-center justify-center">
            <div className="w-2 h-2 bg-accent-cyan rounded-full animate-pulse" />
          </div>
          <p className="text-sm">Initializing v3 research graph...</p>
          <div className="max-w-md rounded-xl border border-border bg-bg-secondary p-4 text-left text-xs text-text-secondary/80 space-y-2">
            <p className="font-semibold text-text-primary">Streaming state</p>
            <p>{values?.research_brief ? "Brief generated." : "Waiting for research brief…"}</p>
            <p>{Array.isArray(values?.research_tasks) ? `${values.research_tasks.length} planned tasks available.` : "Planning tasks…"}</p>
            <p>{values?.final_report ? "Final report ready." : "Report will appear after generation completes."}</p>
            <p className="text-text-secondary/60">Legacy subagent messages are not emitted by the v3 graph yet.</p>
          </div>
        </div>
      )}
    </div>
  );
}
