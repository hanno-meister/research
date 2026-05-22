import { describe, expect, it, beforeEach } from "vitest";
import { useResearchStore } from "./researchStore";

describe("researchStore", () => {
  beforeEach(() => {
    useResearchStore.setState(useResearchStore.getInitialState?.() ?? {});
    useResearchStore.getState().reset();
  });

  it("starts a run with correct state", () => {
    const state = useResearchStore.getState();
    state.startRun({
      lance_name: "Test",
      lance_description: "Desc",
      start_date: "2024-01-01",
      end_date: "2024-12-31",
      query_domains: ["example.com"],
    });

    const after = useResearchStore.getState();
    expect(after.runStatus).toBe("streaming");
    expect(after.lastInput).not.toBeNull();
    expect(after.showForm).toBe(false);
    expect(after.error).toBeNull();
    expect(after.finalReport).toBeNull();
  });

  it("completes a run and stores report", () => {
    const state = useResearchStore.getState();
    state.startRun({
      lance_name: "Test",
      lance_description: "Desc",
      start_date: "",
      end_date: "",
      query_domains: [],
    });
    state.completeRun("Final report content");

    const after = useResearchStore.getState();
    expect(after.runStatus).toBe("completed");
    expect(after.finalReport).toBe("Final report content");
  });

  it("does not complete a cancelled run", () => {
    const state = useResearchStore.getState();
    state.startRun({
      lance_name: "Test",
      lance_description: "Desc",
      start_date: "",
      end_date: "",
      query_domains: [],
    });
    state.cancelRun();
    state.completeRun("Should be ignored");

    const after = useResearchStore.getState();
    expect(after.runStatus).toBe("cancelled");
    expect(after.finalReport).toBeNull();
  });

  it("fails a run and sets error", () => {
    const state = useResearchStore.getState();
    state.startRun({
      lance_name: "Test",
      lance_description: "Desc",
      start_date: "",
      end_date: "",
      query_domains: [],
    });
    state.failRun("Something went wrong");

    const after = useResearchStore.getState();
    expect(after.runStatus).toBe("error");
    expect(after.error).toBe("Something went wrong");
    expect(after.showForm).toBe(true);
  });

  it("does not fail a cancelled run", () => {
    const state = useResearchStore.getState();
    state.startRun({
      lance_name: "Test",
      lance_description: "Desc",
      start_date: "",
      end_date: "",
      query_domains: [],
    });
    state.cancelRun();
    state.failRun("Should be ignored");

    const after = useResearchStore.getState();
    expect(after.runStatus).toBe("cancelled");
    expect(after.error).toBeNull();
  });

  it("resets to idle state", () => {
    const state = useResearchStore.getState();
    state.startRun({
      lance_name: "Test",
      lance_description: "Desc",
      start_date: "",
      end_date: "",
      query_domains: [],
    });
    state.completeRun("report");
    const beforeReset = useResearchStore.getState();
    const prevSessionKey = beforeReset.sessionKey;

    state.reset();

    const after = useResearchStore.getState();
    expect(after.runStatus).toBe("idle");
    expect(after.finalReport).toBeNull();
    expect(after.sessionKey).toBe(prevSessionKey + 1);
  });

  it("trims empty reports to null", () => {
    const state = useResearchStore.getState();
    state.setFinalReport("  ");
    expect(useResearchStore.getState().finalReport).toBeNull();

    state.setFinalReport("report");
    expect(useResearchStore.getState().finalReport).toBe("report");
  });
});
