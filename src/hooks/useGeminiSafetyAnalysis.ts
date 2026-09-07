import { useCallback, useEffect, useMemo, useState } from "react";
import { analyzeSafetyImage } from "../lib/analyzeSafetyImage";
import {
  fetchAnalysisHistory,
  saveAnalysisHistory
} from "../lib/analysisHistoryApi";
import {
  fetchSettings,
  getSafetyAnalysisRuntimeConfig
} from "../lib/providers/providerRuntime";
import type { AiMode, AIProviderType } from "../types/ai";
import type {
  AnalysisErrorCode,
  AnalysisHistoryEntry
} from "../types/analysis";
import { isSafetyAnalysisError } from "../types/analysis";
import type { SettingsResponse } from "../types/settings";
import { fileToBase64, getImageMimeType } from "../utils/imageFile";

const ANALYSIS_ERROR_MESSAGES: Record<AnalysisErrorCode, string> = {
  API_KEY_MISSING:
    "APIキーが設定されていません。GEMINI_A_API_KEY / GEMINI_B_API_KEY / VERTEX_API_KEY を確認してください。",
  CONFIG_MISSING: "プロバイダー設定が不足しています。",
  IMAGE_NOT_SELECTED: "画像を選択してから分析してください。",
  API_RESPONSE_INVALID:
    "AIプロバイダーから不正な形式の応答が返されました。時間をおいて再試行してください。",
  PROVIDER_REQUEST_FAILED:
    "AIプロバイダーへのリクエストに失敗しました。認証情報とモデル設定を確認してください。",
  NETWORK_ERROR:
    "ネットワーク接続に失敗しました。環境を確認して再試行してください。",
  EMPTY_RESPONSE:
    "AIプロバイダーから空の応答が返されました。別の画像で再試行してください。",
  UNKNOWN: "分析中に予期しないエラーが発生しました。"
};

const PROVIDER_CONFIG_ERROR_MESSAGE: Record<AIProviderType, string> = {
  gemini: "KY / KY予防 の設定が未設定です。",
  vertex: "VERTEX の設定が未設定です。"
};

const ANALYSIS_HISTORY_LIMIT = 20;
const UNKNOWN_IMAGE_NAME = "画像名不明";

const createHistoryEntryId = (): string => {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
};

const toErrorMessage = (error: unknown, providerType: AIProviderType): string => {
  if (isSafetyAnalysisError(error)) {
    if (error.code === "API_KEY_MISSING" || error.code === "CONFIG_MISSING") {
      return PROVIDER_CONFIG_ERROR_MESSAGE[providerType];
    }

    const detailedMessage = error.message.trim();
    if (detailedMessage.length > 0) {
      return detailedMessage;
    }

    return ANALYSIS_ERROR_MESSAGES[error.code];
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return ANALYSIS_ERROR_MESSAGES.UNKNOWN;
};

export const useGeminiSafetyAnalysis = (mode: AiMode) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisMarkdown, setAnalysisMarkdown] = useState("");
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisHistoryEntry[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<SettingsResponse | null>(null);
  const [isHistoryLoaded, setIsHistoryLoaded] = useState(false);
  const [hasSkippedInitialSave, setHasSkippedInitialSave] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const loadInitialData = async (): Promise<void> => {
      const [settings, history] = await Promise.all([
        fetchSettings(),
        fetchAnalysisHistory()
      ]);
      if (!isMounted) return;

      setRuntimeSettings(settings);

      const normalizedHistory = history.slice(0, ANALYSIS_HISTORY_LIMIT);
      const latestEntry = normalizedHistory[0];
      setAnalysisHistory(normalizedHistory);
      setAnalysisMarkdown(latestEntry?.markdown ?? "");
      setActiveHistoryId(latestEntry?.id ?? null);
      setIsHistoryLoaded(true);
    };

    void loadInitialData();

    return () => {
      isMounted = false;
    };
  }, []);

  const runtimeConfig = useMemo(
    () => getSafetyAnalysisRuntimeConfig(mode, runtimeSettings),
    [mode, runtimeSettings]
  );

  const activeHistoryEntry = useMemo(
    () => analysisHistory.find((entry) => entry.id === activeHistoryId) ?? null,
    [analysisHistory, activeHistoryId]
  );

  useEffect(() => {
    if (!isHistoryLoaded) return;

    // 初回ロード直後は、読み込んだ履歴をそのまま保存し直すのを防ぐ。
    if (!hasSkippedInitialSave) {
      setHasSkippedInitialSave(true);
      return;
    }

    void saveAnalysisHistory(analysisHistory).catch(() => {
      // 履歴保存失敗は分析フローを止めない。
    });
  }, [analysisHistory, isHistoryLoaded, hasSkippedInitialSave]);

  const showHistoryEntry = useCallback(
    (historyId: string): void => {
      const selectedEntry = analysisHistory.find((entry) => entry.id === historyId);
      if (!selectedEntry) return;

      setErrorMessage(null);
      setActiveHistoryId(selectedEntry.id);
      setAnalysisMarkdown(selectedEntry.markdown);
    },
    [analysisHistory]
  );

  const analyzeSelectedImage = useCallback(
    async (selectedImage: File | null): Promise<void> => {
      if (isAnalyzing) return;

      setIsAnalyzing(true);
      setErrorMessage(null);
      setAnalysisMarkdown("");
      setActiveHistoryId(null);

      try {
        const result = await analyzeSafetyImage({ imageFile: selectedImage, mode });
        const imageBase64 = selectedImage ? await fileToBase64(selectedImage) : undefined;
        const imageMimeType = selectedImage ? getImageMimeType(selectedImage) : undefined;
        const historyEntry: AnalysisHistoryEntry = {
          id: createHistoryEntryId(),
          createdAt: new Date().toISOString(),
          imageName: selectedImage?.name?.trim() || UNKNOWN_IMAGE_NAME,
          imageBase64,
          imageMimeType,
          mode,
          providerDisplayLabel: runtimeConfig.providerDisplayLabel,
          model: runtimeConfig.model,
          markdown: result.markdown
        };

        setAnalysisHistory((prev) => {
          const normalizedPrev = prev.map((entry) => ({
            ...entry,
            imageBase64: undefined
          }));
          return [historyEntry, ...normalizedPrev].slice(0, ANALYSIS_HISTORY_LIMIT);
        });
        setActiveHistoryId(historyEntry.id);
        setAnalysisMarkdown(result.markdown);
      } catch (error) {
        setErrorMessage(toErrorMessage(error, runtimeConfig.providerType));
      } finally {
        setIsAnalyzing(false);
      }
    },
    [isAnalyzing, mode, runtimeConfig]
  );

  return {
    isAnalyzing,
    analysisMarkdown,
    analysisHistory,
    activeHistoryId,
    activeHistoryEntry,
    errorMessage,
    analyzeSelectedImage,
    runtimeConfig,
    showHistoryEntry
  };
};
