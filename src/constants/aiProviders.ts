import type { AiMode, AIProviderType } from "../types/ai";

export type AiModeMeta = {
  optionLabel: string;
  providerType: AIProviderType;
  providerLabel: string;
  modeLabel: string;
  modeDescription: string;
};

export const AI_MODE_META_BY_MODE: Readonly<Record<AiMode, AiModeMeta>> = {
  gemini_a: {
    optionLabel: "KY",
    providerType: "gemini",
    providerLabel: "KY",
    modeLabel: "gemini_a",
    modeDescription: "Gemini系メイン実行先（target=gemini_a）"
  },
  gemini_b: {
    optionLabel: "KY予備",
    providerType: "gemini",
    providerLabel: "KY予備",
    modeLabel: "gemini_b",
    modeDescription: "Gemini系予備実行先（target=gemini_b）"
  },
  vertex: {
    optionLabel: "VERTEX",
    providerType: "vertex",
    providerLabel: "VERTEX",
    modeLabel: "vertex",
    modeDescription: "Vertex実行先（target=vertex）"
  }
};

export const AI_MODE_OPTIONS = [
  { value: "gemini_a", label: AI_MODE_META_BY_MODE.gemini_a.optionLabel },
  { value: "gemini_b", label: AI_MODE_META_BY_MODE.gemini_b.optionLabel },
  { value: "vertex", label: AI_MODE_META_BY_MODE.vertex.optionLabel }
] as const satisfies ReadonlyArray<{ value: AiMode; label: string }>;

export const getAiModeMeta = (mode: AiMode): AiModeMeta => AI_MODE_META_BY_MODE[mode];
