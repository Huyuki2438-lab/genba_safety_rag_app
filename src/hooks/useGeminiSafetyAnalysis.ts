import { useCallback, useEffect, useMemo, useState } from "react";
import { analyzeSafetyImage } from "../lib/analyzeSafetyImage";
import { createAnalysisHistory, fetchAnalysisHistory, type CreateHistoryInput } from "../lib/analysisHistoryApi";
import { fetchSettings, getSafetyAnalysisRuntimeConfig } from "../lib/providers/providerRuntime";
import type { AiMode, AIProviderType } from "../types/ai";
import type { AnalysisHistoryEntry } from "../types/analysis";
import { isSafetyAnalysisError } from "../types/analysis";
import type { SettingsResponse } from "../types/settings";
import { fileToBase64, getImageMimeType } from "../utils/imageFile";

type KyMetadata = { siteName: string; workContent: string; mainRisk: string };
const toErrorMessage = (error: unknown, _provider: AIProviderType): string => {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (isSafetyAnalysisError(error)) return error.message;
  return "処理中に問題が発生しました。";
};

export const useGeminiSafetyAnalysis = (mode: AiMode) => {
  const [pendingSave, setPendingSave] = useState<CreateHistoryInput | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisMarkdown, setAnalysisMarkdown] = useState("");
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisHistoryEntry[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<SettingsResponse | null>(null);
  const reloadHistory = useCallback(async () => { const history = await fetchAnalysisHistory(); setAnalysisHistory(history); return history; }, []);
  useEffect(() => { void fetchSettings().then(setRuntimeSettings).catch(() => setRuntimeSettings(null)); }, []);
  const runtimeConfig = useMemo(() => getSafetyAnalysisRuntimeConfig(mode, runtimeSettings), [mode, runtimeSettings]);
  const activeHistoryEntry = useMemo(() => analysisHistory.find((entry) => entry.id === activeHistoryId) ?? null, [analysisHistory, activeHistoryId]);
  const showHistoryEntry = useCallback((entry: AnalysisHistoryEntry) => { setErrorMessage(null); setActiveHistoryId(entry.id); setAnalysisMarkdown(entry.markdown); setAnalysisHistory(previous => [entry, ...previous.filter(item => item.id !== entry.id)]); }, []);
  const analyzeSelectedImage = useCallback(async (selectedImage: File | null, metadata: KyMetadata): Promise<void> => {
    if (isAnalyzing || !selectedImage) { if (!selectedImage) setErrorMessage("写真を選択してください。"); return; }
    setIsAnalyzing(true); setErrorMessage(null); setAnalysisMarkdown(""); setActiveHistoryId(null); setPendingSave(null);
    try {
      const result = await analyzeSafetyImage({ imageFile: selectedImage, mode });
      setAnalysisMarkdown(result.markdown);
      const saveInput: CreateHistoryInput = { imageName: selectedImage.name || "現場写真", imageMimeType: getImageMimeType(selectedImage), imageBase64: await fileToBase64(selectedImage), mode, providerDisplayLabel: runtimeConfig.providerDisplayLabel, model: runtimeConfig.model, markdown: result.markdown, ...metadata };
      setPendingSave(saveInput);
      const saved = await createAnalysisHistory(saveInput);
      setPendingSave(null);
      setAnalysisHistory((previous) => [saved, ...previous.filter((entry) => entry.id !== saved.id)]);
      showHistoryEntry(saved);
    } catch (error) { setErrorMessage(toErrorMessage(error, runtimeConfig.providerType)); }
    finally { setIsAnalyzing(false); }
  }, [isAnalyzing, mode, runtimeConfig, showHistoryEntry]);
  const retrySave = async () => {
    if (!pendingSave || isAnalyzing) return;
    setIsAnalyzing(true);
    try { const saved = await createAnalysisHistory(pendingSave); setPendingSave(null); showHistoryEntry(saved); }
    catch (error) { setErrorMessage(toErrorMessage(error, runtimeConfig.providerType)); }
    finally { setIsAnalyzing(false); }
  };
  return { pendingSave, retrySave, isAnalyzing, analysisMarkdown, analysisHistory, activeHistoryId, activeHistoryEntry, errorMessage, analyzeSelectedImage, runtimeConfig, showHistoryEntry, reloadHistory };
};
