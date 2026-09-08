import type { AiMode } from "./ai";

export type AnalysisErrorCode =
  | "API_KEY_MISSING"
  | "CONFIG_MISSING"
  | "IMAGE_NOT_SELECTED"
  | "API_RESPONSE_INVALID"
  | "PROVIDER_REQUEST_FAILED"
  | "NETWORK_ERROR"
  | "EMPTY_RESPONSE"
  | "UNKNOWN";

export type AnalyzeImageSafetyInput = {
  imageFile: File | null;
  mode: AiMode;
};

export type AnalyzeImageSafetyResult = {
  markdown: string;
};

export type AnalysisHistoryEntry = {
  id: string;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  siteName: string;
  workContent: string;
  mainRisk: string;
  imageName: string;
  imageMimeType?: string;
  imageUrl?: string;
  mode: AiMode;
  providerDisplayLabel: string;
  model: string;
  markdown: string;
};

export const ANALYSIS_SECTION_KEYS = [
  "OVERALL",
  "SUMMARY",
  "RISKS",
  "SOLUTIONS",
  "ADDITIONAL"
] as const;

export type AnalysisSectionKey = (typeof ANALYSIS_SECTION_KEYS)[number];

export type AnalysisSections = Record<AnalysisSectionKey, string>;

export type ParsedAnalysisSections = {
  sections: AnalysisSections;
  foundSectionCount: number;
  hasStructuredSections: boolean;
};

export class SafetyAnalysisError extends Error {
  readonly code: AnalysisErrorCode;
  readonly cause?: unknown;

  constructor(code: AnalysisErrorCode, message: string, cause?: unknown) {
    super(message);
    this.name = "SafetyAnalysisError";
    this.code = code;
    this.cause = cause;
  }
}

export const isSafetyAnalysisError = (
  error: unknown
): error is SafetyAnalysisError => {
  return error instanceof SafetyAnalysisError;
};
