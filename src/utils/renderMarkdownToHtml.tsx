import { renderToStaticMarkup } from "react-dom/server";
import { MarkdownReport } from "../components/MarkdownReport";
import { sanitizeHtml } from "./sanitizeHtml";

export const renderMarkdownToHtml = (markdown: string): string => {
  const normalized = markdown.trim();
  if (!normalized) return "";

  const rendered = renderToStaticMarkup(<MarkdownReport markdown={normalized} />);
  return sanitizeHtml(rendered);
};
