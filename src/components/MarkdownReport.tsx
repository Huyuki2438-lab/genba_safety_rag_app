import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";

type MarkdownReportProps = {
  markdown: string;
  className?: string;
};

type HeaderCellProps = ComponentProps<"th">;
type DataCellProps = ComponentProps<"td">;

const joinClassNames = (...classes: Array<string | undefined>): string => {
  return classes.filter(Boolean).join(" ");
};

export function MarkdownReport({ markdown, className }: MarkdownReportProps) {
  return (
    <div className={joinClassNames("analysis-markdown", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          table: ({ children }) => (
            <div className="markdown-table-wrap">
              <table>{children}</table>
            </div>
          ),
          th: ({ className: cellClassName, ...props }: HeaderCellProps) => (
            <th {...props} className={joinClassNames("markdown-table-head", cellClassName)} />
          ),
          td: ({ className: cellClassName, ...props }: DataCellProps) => (
            <td {...props} className={joinClassNames("markdown-table-cell", cellClassName)} />
          ),
          a: ({ className: anchorClassName, ...props }) => (
            <a
              {...props}
              className={joinClassNames("markdown-link", anchorClassName)}
              target="_blank"
              rel="noreferrer"
            />
          )
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
