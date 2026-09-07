import type { AIProviderType } from "../types/ai";

const DEFAULT_SAFETY_ANALYSIS_MODEL = "gemini-2.5-flash";

export const SAFETY_ANALYSIS_MODEL_BY_PROVIDER: Readonly<
  Record<AIProviderType, string>
> = {
  gemini: DEFAULT_SAFETY_ANALYSIS_MODEL,
  vertex: DEFAULT_SAFETY_ANALYSIS_MODEL
};

export const getSafetyAnalysisModelForProvider = (
  providerType: AIProviderType
): string => {
  return SAFETY_ANALYSIS_MODEL_BY_PROVIDER[providerType];
};
