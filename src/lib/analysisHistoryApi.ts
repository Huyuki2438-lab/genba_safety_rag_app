import { HISTORY_ENDPOINT } from "../constants/endpoints";
import type { AiMode } from "../types/ai";
import type { AnalysisHistoryEntry } from "../types/analysis";

export type HistoryFilters = { dateFrom?: string; dateTo?: string; siteName?: string; workContent?: string; createdBy?: string; keyword?: string };
export type CreateHistoryInput = { imageName: string; imageMimeType: string; imageBase64: string; mode: AiMode; providerDisplayLabel: string; model: string; markdown: string; siteName: string; workContent: string; mainRisk: string };

const readError = async (response: Response): Promise<string> => {
  try { const data: unknown = await response.json(); if (data && typeof data === "object" && "detail" in data && typeof data.detail === "string") return data.detail; } catch { /* not JSON */ }
  return "共有データへ接続できません。ネットワーク接続を確認してください。";
};

export const fetchAnalysisHistory = async (filters: HistoryFilters = {}, offset = 0): Promise<AnalysisHistoryEntry[]> => {
  const params = new URLSearchParams({ offset: String(offset), limit: "50" });
  [["date_from", filters.dateFrom], ["date_to", filters.dateTo], ["site_name", filters.siteName], ["work_content", filters.workContent], ["created_by", filters.createdBy], ["keyword", filters.keyword]].forEach(([key, value]) => { const normalized = value?.trim(); if (normalized) params.set(String(key), normalized); });
  const response = await fetch(`${HISTORY_ENDPOINT}${params.size ? `?${params}` : ""}`);
  if (!response.ok) throw new Error(await readError(response));
  const data: unknown = await response.json();
  return data && typeof data === "object" && "history" in data && Array.isArray(data.history) ? data.history as AnalysisHistoryEntry[] : [];
};

export const createAnalysisHistory = async (entry: CreateHistoryInput): Promise<AnalysisHistoryEntry> => {
  const response = await fetch(HISTORY_ENDPOINT, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(entry) });
  if (!response.ok) throw new Error(await readError(response));
  return await response.json() as AnalysisHistoryEntry;
};

export const deleteAnalysisHistory = async (entryId: string): Promise<void> => {
  const response = await fetch(`${HISTORY_ENDPOINT}/${encodeURIComponent(entryId)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readError(response));
};
