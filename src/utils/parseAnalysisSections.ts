import {
  ANALYSIS_SECTION_KEYS,
  type AnalysisSectionKey,
  type AnalysisSections,
  type ParsedAnalysisSections
} from "../types/analysis";

const SECTION_MARKER_PATTERN =
  /\[SECTION:(OVERALL|SUMMARY|RISKS|SOLUTIONS|ADDITIONAL)\]/g;

const createEmptySections = (): AnalysisSections => ({
  OVERALL: "",
  SUMMARY: "",
  RISKS: "",
  SOLUTIONS: "",
  ADDITIONAL: ""
});

const countFilledSections = (sections: AnalysisSections): number => {
  return ANALYSIS_SECTION_KEYS.filter((key) => sections[key].trim().length > 0)
    .length;
};

export const parseAnalysisSections = (
  markdown: string
): ParsedAnalysisSections => {
  const normalized = markdown.trim();
  const sections = createEmptySections();

  if (!normalized) {
    return {
      sections,
      foundSectionCount: 0,
      hasStructuredSections: false
    };
  }

  const matches = [...normalized.matchAll(SECTION_MARKER_PATTERN)];
  if (matches.length === 0) {
    sections.OVERALL = normalized;
    return {
      sections,
      foundSectionCount: 1,
      hasStructuredSections: false
    };
  }

  const firstMarkerIndex = matches[0]?.index ?? 0;
  const preface = normalized.slice(0, firstMarkerIndex).trim();
  if (preface) {
    sections.OVERALL = preface;
  }

  matches.forEach((match, index) => {
    const sectionKey = match[1] as AnalysisSectionKey;
    const contentStart = (match.index ?? 0) + match[0].length;
    const contentEnd = matches[index + 1]?.index ?? normalized.length;
    const content = normalized.slice(contentStart, contentEnd).trim();

    if (!content) return;
    sections[sectionKey] = sections[sectionKey]
      ? `${sections[sectionKey]}\n\n${content}`
      : content;
  });

  const foundSectionCount = countFilledSections(sections);
  if (foundSectionCount === 0) {
    sections.OVERALL = normalized;
    return {
      sections,
      foundSectionCount: 1,
      hasStructuredSections: false
    };
  }

  return {
    sections,
    foundSectionCount,
    hasStructuredSections: true
  };
};

