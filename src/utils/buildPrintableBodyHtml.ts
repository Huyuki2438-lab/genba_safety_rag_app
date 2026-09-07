type BuildPrintableBodyHtmlParams = {
  generatedAtText: string;
  imagePreviewUrl: string | null;
  reportHtml: string;
  reportTitle: string;
};

type SectionKey = "OVERALL" | "SUMMARY" | "RISKS" | "SOLUTIONS" | "ADDITIONAL";

type PdfReportSections = Record<SectionKey, string>;

const SECTION_KEYS: SectionKey[] = [
  "OVERALL",
  "SUMMARY",
  "RISKS",
  "SOLUTIONS",
  "ADDITIONAL"
];

const SECTION_MARKER_PATTERN = /^\s*\[SECTION:([^\]]+)\]\s*$/i;
const SECTION_LINE_PATTERN = /^\s*\[SECTION:[^\]]+\]\s*$/gim;

// PDF本文に制御タグが混入しないように、描画前に必ず除去する。
const stripSectionTags = (value: string): string => {
  return value.replace(SECTION_LINE_PATTERN, "").trim();
};

const escapeHtml = (value: string): string => {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

const isMeaningfulNode = (node: ChildNode): boolean => {
  if (node.nodeType === Node.TEXT_NODE) {
    return Boolean((node.textContent ?? "").trim());
  }
  return true;
};

const extractSectionMarker = (node: ChildNode): SectionKey | null => {
  const markerCandidate =
    node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE
      ? (node.textContent ?? "").trim()
      : "";

  if (!markerCandidate) return null;
  const markerMatch = markerCandidate.match(SECTION_MARKER_PATTERN);
  if (!markerMatch) return null;

  const rawMarker = markerMatch[1].toUpperCase();
  return SECTION_KEYS.includes(rawMarker as SectionKey) ? (rawMarker as SectionKey) : null;
};

const nodesToHtml = (doc: Document, nodes: ChildNode[]): string => {
  if (nodes.length === 0) return "";
  const wrapper = doc.createElement("div");
  nodes.forEach((node) => {
    wrapper.appendChild(node.cloneNode(true));
  });
  return stripSectionTags(wrapper.innerHTML);
};

const createEmptySections = (): PdfReportSections => ({
  OVERALL: "",
  SUMMARY: "",
  RISKS: "",
  SOLUTIONS: "",
  ADDITIONAL: ""
});

const collectSectionNodes = (markdownRoot: Element): Map<SectionKey, ChildNode[]> => {
  const sectionNodes = new Map<SectionKey, ChildNode[]>();
  let activeSection: SectionKey = "OVERALL";
  sectionNodes.set(activeSection, []);

  for (const node of Array.from(markdownRoot.childNodes)) {
    const sectionMarker = extractSectionMarker(node);
    if (sectionMarker) {
      activeSection = sectionMarker;
      if (!sectionNodes.has(activeSection)) {
        sectionNodes.set(activeSection, []);
      }
      continue;
    }

    if (!isMeaningfulNode(node)) {
      continue;
    }

    const nodes = sectionNodes.get(activeSection);
    if (!nodes) {
      sectionNodes.set(activeSection, [node.cloneNode(true) as ChildNode]);
      continue;
    }
    nodes.push(node.cloneNode(true) as ChildNode);
  }

  return sectionNodes;
};

const buildPdfSections = (reportHtml: string): PdfReportSections => {
  const fallback = createEmptySections();
  fallback.OVERALL = stripSectionTags(reportHtml);

  if (typeof window === "undefined") {
    return fallback;
  }

  const parser = new window.DOMParser();
  const doc = parser.parseFromString(`<div id="print-root">${reportHtml}</div>`, "text/html");
  const root = doc.getElementById("print-root");
  const markdownRoot = root?.querySelector(".analysis-markdown");

  if (!markdownRoot) {
    return fallback;
  }

  const sectionNodes = collectSectionNodes(markdownRoot);
  const sections = createEmptySections();
  SECTION_KEYS.forEach((key) => {
    sections[key] = nodesToHtml(doc, sectionNodes.get(key) ?? []).trim();
  });

  const hasStructuredContent = SECTION_KEYS.some((key) => sections[key].length > 0);
  if (!hasStructuredContent) {
    sections.OVERALL = stripSectionTags(markdownRoot.innerHTML).trim() || fallback.OVERALL;
  }

  if (!sections.OVERALL) {
    sections.OVERALL = fallback.OVERALL;
  }

  return sections;
};

const renderSectionPage = (pageClassName: string, html: string, fallbackHtml: string): string => {
  const sectionHtml = html.trim() || fallbackHtml;
  return `
    <section class="page ${pageClassName}">
      <div class="analysis-markdown section-content">${sectionHtml}</div>
    </section>
  `;
};

export const buildPrintableBodyHtml = ({
  generatedAtText,
  imagePreviewUrl,
  reportHtml,
  reportTitle
}: BuildPrintableBodyHtmlParams): string => {
  const sections = buildPdfSections(reportHtml);

  return `
    <section class="page overall-page">
      <header class="pdf-header">
        <h1>${escapeHtml(reportTitle)}</h1>
        <p>出力日時: ${escapeHtml(generatedAtText)}</p>
      </header>
      ${imagePreviewUrl ? `<div class="pdf-image-wrap"><img src="${imagePreviewUrl}" alt="分析対象画像" /></div>` : ""}
      <div class="analysis-markdown overall-content">${sections.OVERALL.trim() || "<p>1. 総合評価の情報はありません。</p>"}</div>
    </section>
    ${renderSectionPage(
      "summary-page",
      sections.SUMMARY,
      "<h1>2. リスク要約表</h1><p>2. リスク要約表の情報はありません。</p>"
    )}
    ${renderSectionPage(
      "risks-page",
      sections.RISKS,
      "<h1>3. 詳細リスク</h1><p>3. 詳細リスクの情報はありません。</p>"
    )}
    ${renderSectionPage(
      "solutions-page",
      sections.SOLUTIONS,
      "<h1>4. 是正計画</h1><p>4. 是正計画の情報はありません。</p>"
    )}
    ${renderSectionPage(
      "additional-page",
      sections.ADDITIONAL,
      "<h1>5. 補足事項</h1><p>5. 補足事項の情報はありません。</p>"
    )}
  `;
};
