import { useState, type FormEvent } from "react";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { Download, Copy, FileText, Check, MessageSquarePlus } from "lucide-react";
import type { ResearchInput } from "../types";
import { createReportDocxBlob } from "../utils/reportExport";

interface FinalReportPanelProps {
  report?: string | null;
  isLoading: boolean;
  onSubmitFeedback: (feedback: string) => Promise<boolean>;
  lastInput?: ResearchInput | null;
}

function buildReportTitle(lastInput?: ResearchInput | null): string {
  if (!lastInput) return "";
  const { lance_name, start_date, end_date } = lastInput;
  if (start_date && end_date) {
    return `# ${lance_name} - Trend Scout ${start_date} - ${end_date}`;
  }
  if (start_date) {
    return `# ${lance_name} - Trend Scout from ${start_date}`;
  }
  if (end_date) {
    return `# ${lance_name} - Trend Scout until ${end_date}`;
  }
  return `# ${lance_name} - Trend Scout`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function FinalReportPanel({
  report,
  isLoading,
  onSubmitFeedback,
  lastInput,
}: FinalReportPanelProps) {
  const [copied, setCopied] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const finalReport = report?.trim() ? report : undefined;
  const largeModel = (import.meta.env.VITE_LARGE_MODEL as string | undefined) || "—";
  const smallModel = (import.meta.env.VITE_SMALL_MODEL as string | undefined) || "—";
  const dateRange = `${lastInput?.start_date || "—"} → ${lastInput?.end_date || "—"}`;
  const queryDomains = Array.isArray(lastInput?.query_domains)
    ? lastInput.query_domains
    : [];
  const domainsInScope =
    queryDomains.length ? queryDomains.join(", ") : "—";

  const handleCopy = () => {
    if (!finalReport) return;
    navigator.clipboard.writeText(finalReport);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    if (!finalReport) return;
    setExportError(null);
    const title = buildReportTitle(lastInput);
    const content = title ? `${title}\n\n${finalReport}` : finalReport;
    downloadBlob(new Blob([content], { type: "text/markdown" }), "research-report.md");
  };

  const handleDownloadDocx = async () => {
    if (!finalReport) return;
    try {
      setExportError(null);
      const title = buildReportTitle(lastInput);
      const content = title ? `${title}\n\n${finalReport}` : finalReport;
      const blob = await createReportDocxBlob(content);
      downloadBlob(blob, "research-report.docx");
    } catch {
      setExportError("Unable to export the report as a Word document.");
    }
  };

  const handleFeedbackSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedFeedback = feedback.trim();
    if (!trimmedFeedback) return;

    const submitted = await onSubmitFeedback(trimmedFeedback);
    if (!submitted) return;

    setFeedback("");
    setFeedbackSubmitted(true);
    setTimeout(() => setFeedbackSubmitted(false), 2500);
  };

  if (!finalReport) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text-secondary/50 space-y-4 py-20">
        <FileText className="w-16 h-16 opacity-10" />
        <p className="max-w-[240px] text-center text-sm">
          The final research report will appear here once the mission is
          complete.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-20">
      <div className="flex items-center justify-between border-b border-border pb-4 sticky top-0 bg-bg-primary z-10">
        <h2 className="text-xl font-bold tracking-tight">
          Final Research Analysis
        </h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCopy}
            className="p-2 hover:bg-bg-secondary rounded-lg transition-colors text-text-secondary"
            title="Copy Markdown"
          >
            {copied ? (
              <Check size={18} className="text-accent-green" />
            ) : (
              <Copy size={18} />
            )}
          </button>
          <button
            type="button"
            onClick={handleDownloadMarkdown}
            className="flex items-center gap-2 px-3 py-2 hover:bg-bg-secondary rounded-lg transition-colors text-text-secondary text-xs border border-border"
            title="Download Markdown"
          >
            <Download size={16} />
            Markdown
          </button>
          <button
            type="button"
            onClick={() => void handleDownloadDocx()}
            className="flex items-center gap-2 px-3 py-2 hover:bg-bg-secondary rounded-lg transition-colors text-text-secondary text-xs border border-border"
            title="Download DOCX"
          >
            <FileText size={16} />
            Word
          </button>
        </div>
      </div>

      {lastInput && (
        <section className="rounded-xl border border-border bg-bg-secondary p-5">
          <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-text-secondary">
            Report Parameters
          </h3>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                Lance name
              </dt>
              <dd className="mt-1 text-sm text-text-primary">
                {lastInput.lance_name || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                Model used
              </dt>
              <dd className="mt-1 text-sm text-text-primary space-y-0.5">
                <span className="block">
                  <span className="text-text-secondary/60">Large:</span> {largeModel}
                </span>
                <span className="block">
                  <span className="text-text-secondary/60">Small:</span> {smallModel}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                Domains in scope
              </dt>
              <dd className="mt-1 text-sm text-text-primary">{domainsInScope}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                Date range
              </dt>
              <dd className="mt-1 text-sm text-text-primary">{dateRange}</dd>
            </div>
          </dl>
        </section>
      )}

      <article className="text-text-secondary leading-relaxed">
        <MarkdownRenderer content={finalReport} />
      </article>

      <section className="rounded-xl border border-border bg-bg-secondary/60 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <MessageSquarePlus className="w-4 h-4 text-accent-cyan" />
          <h3 className="text-sm font-semibold text-text-primary">
            Share feedback on this report
          </h3>
        </div>

        <form className="space-y-3" onSubmit={handleFeedbackSubmit}>
          <textarea
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder="Share comments about report quality, gaps, or issues you noticed."
            className="min-h-28 w-full rounded-lg border border-border bg-bg-primary px-4 py-3 text-sm text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:ring-2 focus:ring-accent-cyan/40"
          />

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-text-secondary/70">
              Feedback capture is visible but not connected to a backend yet.
            </span>
            <button
              type="submit"
              disabled={isLoading || feedback.trim().length === 0}
              className="rounded-lg bg-accent-cyan px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-accent-cyan/80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? "Submitting..." : "Feedback Coming Soon"}
            </button>
          </div>
        </form>

        {feedbackSubmitted && (
          <p className="text-xs text-accent-green">
            Feedback captured locally.
          </p>
        )}
        {exportError && (
          <p className="text-xs text-accent-red">{exportError}</p>
        )}
      </section>
    </div>
  );
}
