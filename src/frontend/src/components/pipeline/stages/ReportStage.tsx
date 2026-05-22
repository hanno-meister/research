import type { VanguardStreamValues } from "../../../types";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

interface ReportStageProps {
  values: VanguardStreamValues | undefined;
}

export function ReportStage({ values }: ReportStageProps) {
  const report = values?.final_report;
  const reportStatus = typeof values?.report_status === "string" ? values.report_status : null;

  if (!report) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-bg-primary/50 p-6 text-text-secondary">
        <p className="text-sm">
          The final report will appear here after review is complete.
        </p>
      </div>
    );
  }

  return (
    <article className="rounded-2xl border border-border bg-bg-primary/90 p-5 shadow-sm lg:p-7">
      <div className="mb-5 flex items-start justify-between gap-4 border-b border-border pb-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-text-secondary">Final report</p>
          <h4 className="mt-1 text-lg font-semibold tracking-tight text-text-primary">
            Research synthesis
          </h4>
        </div>
        {reportStatus && (
          <span className="rounded-full border border-border bg-bg-secondary px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-text-secondary">
            {reportStatus}
          </span>
        )}
      </div>

      <div className="max-w-4xl text-sm leading-7 text-text-primary">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeSanitize]}
          components={{
            h1: ({ children }) => (
              <h1 className="mb-4 text-3xl font-semibold tracking-tight text-text-primary">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="mt-8 mb-3 text-xl font-semibold tracking-tight text-text-primary">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="mt-6 mb-2 text-base font-semibold text-text-primary">{children}</h3>
            ),
            p: ({ children }) => <p className="mb-4 text-text-primary">{children}</p>,
            ul: ({ children }) => <ul className="mb-4 list-disc space-y-2 pl-5">{children}</ul>,
            ol: ({ children }) => <ol className="mb-4 list-decimal space-y-2 pl-5">{children}</ol>,
            li: ({ children }) => <li className="text-text-primary">{children}</li>,
            blockquote: ({ children }) => (
              <blockquote className="mb-4 border-l-2 border-accent-cyan/40 pl-4 text-text-secondary">
                {children}
              </blockquote>
            ),
            a: ({ children, href }) => (
              <a
                href={href}
                className="text-accent-cyan underline decoration-accent-cyan/40 underline-offset-4"
              >
                {children}
              </a>
            ),
            hr: () => <hr className="my-6 border-border" />,
            code: ({ inline, children, className }: any) =>
              inline ? (
                <code className="rounded bg-bg-secondary px-1.5 py-0.5 text-[0.9em] text-text-primary">
                  {children}
                </code>
              ) : (
                <code className={`block overflow-x-auto rounded-xl bg-bg-secondary p-4 ${className ?? ""}`}>
                  {children}
                </code>
              ),
            pre: ({ children }) => (
              <pre className="mb-4 overflow-x-auto rounded-xl border border-border bg-bg-secondary p-0 text-sm text-text-primary">
                {children}
              </pre>
            ),
            table: ({ children }) => (
              <div className="mb-4 overflow-x-auto">
                <table className="w-full border-collapse text-left text-sm">{children}</table>
              </div>
            ),
            th: ({ children }) => (
              <th className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border-b border-border px-3 py-2 align-top text-text-primary">
                {children}
              </td>
            ),
        }}
        >
          {report}
        </ReactMarkdown>
      </div>
    </article>
  );
}
