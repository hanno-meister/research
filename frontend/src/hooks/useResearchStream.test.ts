import { describe, expect, it } from "vitest";
import {
  normalizeStreamMessage,
  extractFinalReport,
} from "./useResearchStream";

describe("normalizeStreamMessage", () => {
  it("preserves non-think tool messages", () => {
    const message = normalizeStreamMessage({
      id: "1",
      content: "result",
      name: "search_tool",
      getType: () => "tool",
    });

    expect(message).toMatchObject({
      id: "1",
      type: "tool",
      name: "search_tool",
      content: "result",
    });
  });

  it("preserves think tool messages", () => {
    const message = normalizeStreamMessage({
      id: "2",
      content: "thinking...",
      name: "think_tool",
      getType: () => "tool",
    });

    expect(message).toMatchObject({
      id: "2",
      type: "tool",
      name: "think_tool",
      content: "thinking...",
    });
  });

  it("preserves empty AI messages with tool calls", () => {
    const message = normalizeStreamMessage({
      id: "3",
      content: "",
      tool_calls: [{ name: "search", args: { query: "x" } }],
      getType: () => "ai",
    });

    expect(message.type).toBe("ai");
    expect(message.content).toBe("");
    expect(message.tool_calls?.[0]?.name).toBe("search");
  });

  it("preserves AI messages with write_file tool calls", () => {
    const message = normalizeStreamMessage({
      id: "4",
      content: "",
      tool_calls: [{ name: "write_file", args: { path: "/test.md" } }],
      getType: () => "ai",
    });

    expect(message.type).toBe("ai");
    expect(message.tool_calls?.[0]?.name).toBe("write_file");
  });

  it("normalizes array content with text parts", () => {
    const message = normalizeStreamMessage({
      id: "5",
      content: [{ text: "hello" }, { text: " world" }],
      getType: () => "ai",
    });

    expect(message.content).toBe("hello world");
  });

  it("normalizes object content to JSON string", () => {
    const message = normalizeStreamMessage({
      id: "6",
      content: { key: "value" },
      getType: () => "ai",
    });

    expect(message.content).toBe('{"key":"value"}');
  });

  it("normalizes null content to empty string", () => {
    const message = normalizeStreamMessage({
      id: "7",
      content: null,
      getType: () => "ai",
    });

    expect(message.content).toBe("");
  });

  it("normalizes toolCalls property", () => {
    const message = normalizeStreamMessage({
      id: "8",
      content: "",
      toolCalls: [{ name: "read_file" }],
      getType: () => "ai",
    });

    expect(message.tool_calls?.[0]?.name).toBe("read_file");
  });

  it("filters out invalid tool calls", () => {
    const message = normalizeStreamMessage({
      id: "9",
      content: "",
      tool_calls: [
        { name: "valid" },
        { invalid: true },
        null,
        "string",
      ],
      getType: () => "ai",
    });

    expect(message.tool_calls).toHaveLength(1);
    expect(message.tool_calls?.[0]?.name).toBe("valid");
  });
});

describe("extractFinalReport", () => {
  it("extracts from root final_report", () => {
    expect(extractFinalReport({ final_report: "Report content" })).toBe(
      "Report content",
    );
  });

  it("extracts from nested values.final_report", () => {
    expect(
      extractFinalReport({ values: { final_report: "Nested report" } }),
    ).toBe("Nested report");
  });

  it("prefers root over nested", () => {
    expect(
      extractFinalReport({
        final_report: "Root",
        values: { final_report: "Nested" },
      }),
    ).toBe("Root");
  });

  it("returns null for empty string", () => {
    expect(extractFinalReport({ final_report: "  " })).toBeNull();
  });

  it("returns null for non-string", () => {
    expect(extractFinalReport({ final_report: 123 })).toBeNull();
  });

  it("returns null for null input", () => {
    expect(extractFinalReport(null)).toBeNull();
  });

  it("returns null for primitive input", () => {
    expect(extractFinalReport("string")).toBeNull();
  });
});
