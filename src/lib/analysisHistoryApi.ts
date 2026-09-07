import { HISTORY_ENDPOINT } from "../constants/endpoints";
import { isAiMode } from "../types/ai";
import type { AnalysisHistoryEntry } from "../types/analysis";

type AnalysisHistoryApiResponse = {
  history?: unknown;
};

const toOptionalString = (value: unknown): string | undefined =>
  typeof value === "string" ? value : undefined;

const isAnalysisHistoryEntry = (value: unknown): value is AnalysisHistoryEntry => {
  if (!value || typeof value !== "object") return false;

  const candidate = value as Partial<AnalysisHistoryEntry>;
  const hasValidOptionalString = (field: unknown): boolean =>
    field === undefined || field === null || typeof field === "string";

  return (
    typeof candidate.id === "string" &&
    candidate.id.length > 0 &&
    typeof candidate.createdAt === "string" &&
    candidate.createdAt.length > 0 &&
    typeof candidate.imageName === "string" &&
    candidate.imageName.length > 0 &&
    isAiMode(candidate.mode) &&
    typeof candidate.providerDisplayLabel === "string" &&
    candidate.providerDisplayLabel.length > 0 &&
    typeof candidate.model === "string" &&
    candidate.model.length > 0 &&
    typeof candidate.markdown === "string" &&
    hasValidOptionalString(candidate.historyFolder) &&
    hasValidOptionalString(candidate.imageFileName) &&
    hasValidOptionalString(candidate.imageMimeType) &&
    hasValidOptionalString(candidate.imageBase64) &&
    hasValidOptionalString(candidate.imageUrl)
  );
};

const normalizeHistoryFromResponse = (value: unknown): AnalysisHistoryEntry[] => {
  if (!value || typeof value !== "object") return [];

  const candidate = value as AnalysisHistoryApiResponse;
  if (!Array.isArray(candidate.history)) return [];

  return candidate.history
    .filter((entry): entry is AnalysisHistoryEntry => isAnalysisHistoryEntry(entry))
    .map((entry) => ({
      ...entry,
      historyFolder: toOptionalString(entry.historyFolder),
      imageFileName: toOptionalString(entry.imageFileName),
      imageMimeType: toOptionalString(entry.imageMimeType),
      imageBase64: toOptionalString(entry.imageBase64),
      imageUrl: toOptionalString(entry.imageUrl)
    }));
};

export const fetchAnalysisHistory = async (): Promise<AnalysisHistoryEntry[]> => {
  try {
    const response = await fetch(HISTORY_ENDPOINT);
    if (!response.ok) return [];

    const data: unknown = await response.json();
    return normalizeHistoryFromResponse(data);
  } catch {
    return [];
  }
};

export const saveAnalysisHistory = async (
  history: AnalysisHistoryEntry[]
): Promise<void> => {
  await fetch(HISTORY_ENDPOINT, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ history })
  });
};
