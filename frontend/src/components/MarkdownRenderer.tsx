import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { memo } from "react";

interface MarkdownRendererProps {
  content: string;
}

function sanitizeHref(href?: string): string | undefined {
  if (!href) return undefined;
  try {
    const url = new URL(href, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(url.protocol)
      ? url.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

const components: Components = {
  a: ({ children, href, ...props }) => {
    const safeHref = sanitizeHref(href);
    const text = String(children ?? "");
    const isCitation = /^\[\d+\]$/.test(text);
    if (isCitation) {
      return (
        <a
          {...props}
          href={safeHref}
          className="inline-flex items-center justify-center w-5 h-5 text-[10px] bg-accent-cyan/10 text-accent-cyan rounded-sm border border-accent-cyan/20 mx-0.5 hover:bg-accent-cyan/20 no-underline font-bold"
          target="_blank"
          rel="noopener noreferrer"
        >
          {children}
        </a>
      );
    }
    return (
      <a
        {...props}
        href={safeHref}
        className="text-accent-cyan hover:underline"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    );
  },
  h1: ({ children, ...props }) => (
    <h1 {...props} className="text-2xl font-bold mt-6 mb-4 text-text-primary">
      {children}
    </h1>
  ),
  h2: ({ children, ...props }) => (
    <h2 {...props} className="text-xl font-bold mt-5 mb-3 text-text-primary">
      {children}
    </h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 {...props} className="text-lg font-bold mt-4 mb-2 text-text-primary">
      {children}
    </h3>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return (
        <code
          {...props}
          className="block bg-bg-primary p-4 rounded-lg border border-border my-4 overflow-x-auto text-accent-cyan text-sm"
        >
          {children}
        </code>
      );
    }
    return (
      <code
        {...props}
        className="bg-bg-tertiary px-1.5 py-0.5 rounded text-accent-cyan text-[0.9em]"
      >
        {children}
      </code>
    );
  },
  ul: ({ children, ...props }) => (
    <ul {...props} className="list-disc pl-5 space-y-1 my-4">
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol {...props} className="list-decimal pl-5 space-y-1 my-4">
      {children}
    </ol>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote
      {...props}
      className="border-l-4 border-accent-cyan/50 bg-accent-cyan/5 px-4 py-2 italic my-4 rounded-r-lg"
    >
      {children}
    </blockquote>
  ),
  table: ({ children, ...props }) => (
    <div className="overflow-x-auto my-4">
      <table
        {...props}
        className="w-full border-collapse border border-border text-sm"
      >
        {children}
      </table>
    </div>
  ),
  th: ({ children, ...props }) => (
    <th
      {...props}
      className="border border-border bg-bg-tertiary px-3 py-2 text-left font-semibold text-text-primary"
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td
      {...props}
      className="border border-border px-3 py-2 text-text-secondary"
    >
      {children}
    </td>
  ),
};

function MarkdownRendererInner({ content }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      skipHtml
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}

export const MarkdownRenderer = memo(MarkdownRendererInner);
