import { create } from "zustand";
import type { ResearchInput, RunStatus } from "../types";

interface ResearchState {
  runStatus: RunStatus;
  showForm: boolean;
  lastInput: ResearchInput | null;
  error: string | null;
  sessionKey: number;
  finalReport: string | null;

  setRunStatus: (status: RunStatus) => void;
  setShowForm: (show: boolean) => void;
  setLastInput: (input: ResearchInput) => void;
  setError: (error: string | null) => void;
  setFinalReport: (report: string | null) => void;
  startRun: (input: ResearchInput) => void;
  completeRun: (report: string | null) => void;
  cancelRun: () => void;
  failRun: (message: string) => void;
  reset: () => void;
}

export const useResearchStore = create<ResearchState>((set, get) => ({
  runStatus: "idle",
  showForm: true,
  lastInput: null,
  error: null,
  sessionKey: 0,
  finalReport: null,

  setRunStatus: (status) => set({ runStatus: status }),
  setShowForm: (show) => set({ showForm: show }),
  setLastInput: (input) => set({ lastInput: input }),
  setError: (error) => set({ error }),
  setFinalReport: (report) =>
    set({ finalReport: report?.trim() ? report : null }),

  startRun: (input) =>
    set({
      runStatus: "streaming",
      lastInput: input,
      error: null,
      showForm: false,
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
      showForm: true,
      lastInput: null,
      error: null,
      finalReport: null,
      sessionKey: get().sessionKey + 1,
    }),
}));
