import { MarkdownRenderer } from "./MarkdownRenderer";
import { SubagentCard } from "./SubagentCard";
import { User, Bot, Wrench } from "lucide-react";
import type { StreamMessage, SubagentInfo } from "../types";

interface MessageProps {
  message: StreamMessage;
  subagents: SubagentInfo[];
}

export function Message({ message, subagents }: MessageProps) {
  const isHuman = message.type === "human";
  const isTool = message.type === "tool";
  const isAI = message.type === "ai";

  return (
    <div className={`flex gap-4 ${isHuman ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
          isHuman
            ? "bg-accent-cyan"
            : isTool
              ? "bg-accent-amber/20 text-accent-amber"
              : "bg-bg-secondary border border-border text-accent-cyan"
        }`}
      >
        {isHuman ? (
          <User size={18} />
        ) : isTool ? (
          <Wrench size={18} />
        ) : (
          <Bot size={18} />
        )}
      </div>

      <div
        className={`flex flex-col max-w-[85%] space-y-3 ${isHuman ? "items-end" : "items-start"}`}
      >
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
            isHuman
              ? "bg-accent-cyan text-white rounded-tr-none"
              : isTool
                ? "bg-accent-amber/10 text-accent-amber/80 border border-accent-amber/20 rounded-tl-none font-mono text-xs"
                : "bg-bg-secondary border border-border text-text-primary rounded-tl-none shadow-lg"
          }`}
        >
          {isTool ? (
            <div className="space-y-2">
              <div className="font-bold flex items-center gap-2">
                <Wrench size={12} /> {message.name ?? "Tool Call"}
              </div>
              <pre className="whitespace-pre-wrap opacity-80">
                {message.content}
              </pre>
            </div>
          ) : isAI && !message.content.trim() && message.tool_calls?.length ? (
            <div className="space-y-1 text-xs text-text-secondary">
              {message.tool_calls.map((toolCall, index) => (
                <div key={`${toolCall.name}-${index}`}>
                  Calling `{toolCall.name}`
                </div>
              ))}
            </div>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>

        {isAI && subagents.length > 0 && (
          <div className="w-full grid grid-cols-1 gap-3 mt-2">
            {subagents.map((agent) => (
              <SubagentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
