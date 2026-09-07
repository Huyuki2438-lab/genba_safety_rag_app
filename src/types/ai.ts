export const AI_MODES = [
  "gemini_a",
  "gemini_b",
  "vertex"
] as const;

export type AiMode = (typeof AI_MODES)[number];

export const isAiMode = (value: string | null | undefined): value is AiMode => {
  if (!value) return false;
  return (AI_MODES as readonly string[]).includes(value);
};

export const AI_PROVIDER_TYPES = ["gemini", "vertex"] as const;

export type AIProviderType = (typeof AI_PROVIDER_TYPES)[number];
