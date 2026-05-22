import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FinalReportPanel } from "./FinalReportPanel";

describe("FinalReportPanel", () => {
  it("renders empty state when no report is provided", () => {
    render(
      <FinalReportPanel
        report={null}
        isLoading={false}
        onSubmitFeedback={async () => true}
      />,
    );

    expect(
      screen.getByText(/The final research report will appear here/i),
    ).toBeInTheDocument();
  });

  it("renders empty state when report is empty string", () => {
    render(
      <FinalReportPanel
        report=""
        isLoading={false}
        onSubmitFeedback={async () => true}
      />,
    );

    expect(
      screen.getByText(/The final research report will appear here/i),
    ).toBeInTheDocument();
  });

  it("renders report when provided", () => {
    render(
      <FinalReportPanel
        report="# Final Report\n\nContent here"
        isLoading={false}
        onSubmitFeedback={async () => true}
      />,
    );

    expect(screen.getByText(/Final Research Analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/Content here/i)).toBeInTheDocument();
  });

  it("does not render heuristic report from messages", () => {
    render(
      <FinalReportPanel
        report={null}
        isLoading={false}
        onSubmitFeedback={async () => true}
      />,
    );

    expect(
      screen.queryByText(/Executive summary/i),
    ).not.toBeInTheDocument();
  });
});
