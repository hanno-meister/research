import { create } from "zustand";
import type { ResearchInput, RightPanelTab, RunStatus } from "../types";

interface ResearchState {
  runStatus: RunStatus;
  activeTab: RightPanelTab;
  showForm: boolean;
  lastInput: ResearchInput | null;
  error: string | null;
  sessionKey: number;
  feedbackRunId: string | null;
  finalReport: string | null;

  setRunStatus: (status: RunStatus) => void;
  setActiveTab: (tab: RightPanelTab) => void;
  setShowForm: (show: boolean) => void;
  setLastInput: (input: ResearchInput) => void;
  setError: (error: string | null) => void;
  setFeedbackRunId: (feedbackRunId: string | null) => void;
  setFinalReport: (report: string | null) => void;
  startRun: (input: ResearchInput) => void;
  completeRun: (report: string | null) => void;
  cancelRun: () => void;
  failRun: (message: string) => void;
  reset: () => void;
}

export const useResearchStore = create<ResearchState>((set, get) => ({
  runStatus: "idle",
  activeTab: "tasks",
  showForm: true,
  lastInput: null,
  error: null,
  sessionKey: 0,
  feedbackRunId: null,
  finalReport: null,

  setRunStatus: (status) => set({ runStatus: status }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setShowForm: (show) => set({ showForm: show }),
  setLastInput: (input) => set({ lastInput: input }),
  setError: (error) => set({ error }),
  setFeedbackRunId: (feedbackRunId) => set({ feedbackRunId }),
  setFinalReport: (report) =>
    set({ finalReport: report?.trim() ? report : null }),

  startRun: (input) =>
    set({
      runStatus: "streaming",
      lastInput: input,
      error: null,
      showForm: false,
      feedbackRunId: null,
      finalReport: null,
    }),

  completeRun: (report) =>
    set((state) => {
      if (state.runStatus === "cancelled") return {};
      return {
        runStatus: "completed",
        finalReport: report?.trim() ? report : null,
      };
    }),

  cancelRun: () =>
    set({
      runStatus: "cancelled",
    }),

  failRun: (message) =>
    set((state) => {
      if (state.runStatus === "cancelled") return {};
      return {
        runStatus: "error",
        error: message,
        showForm: true,
      };
    }),

  reset: () =>
    set({
      runStatus: "idle",
      activeTab: "tasks",
      showForm: true,
      lastInput: null,
      error: null,
      feedbackRunId: null,
      finalReport: null,
      sessionKey: get().sessionKey + 1,
    }),
}));
