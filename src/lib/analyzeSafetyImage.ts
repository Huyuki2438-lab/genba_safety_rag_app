import { ANALYZE_ENDPOINT } from "../constants/endpoints";
import { getErrorMessage } from "./providers/providerUtils";
import { fileToBase64, getImageMimeType } from "../utils/imageFile";
import type {
  AnalyzeImageSafetyInput,
  AnalyzeImageSafetyResult
} from "../types/analysis";
import { SafetyAnalysisError as SafetyAnalysisErrorClass } from "../types/analysis";

type AnalyzeApiErrorDetail = {
  error_type?: string;
  error_message?: string;
};

const extractAnalyzeApiError = async (
  response: Response
): Promise<AnalyzeApiErrorDetail | null> => {
  try {
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== "object") return null;

    const detail =
      "detail" in payload ? (payload as { detail?: unknown }).detail : payload;
    if (!detail || typeof detail !== "object") return null;

    const candidate = detail as AnalyzeApiErrorDetail;
    return {
      error_type:
        typeof candidate.error_type === "string" ? candidate.error_type : undefined,
      error_message:
        typeof candidate.error_message === "string" ? candidate.error_message : undefined
    };
  } catch {
    return null;
  }
};

const normalizeResultFromAnalyzeResponse = (
  data: unknown
): AnalyzeImageSafetyResult | null => {
  if (!data || typeof data !== "object") return null;

  const directMarkdown =
    "markdown" in data ? (data as { markdown?: unknown }).markdown : undefined;
  const directModel =
    "used_model" in data ? (data as { used_model?: unknown }).used_model : undefined;

  if (typeof directMarkdown === "string" && typeof directModel === "string") {
    return { markdown: directMarkdown.trim(), usedModel: directModel };
  }

  const nestedResult =
    "result" in data ? (data as { result?: unknown }).result : undefined;
  if (!nestedResult || typeof nestedResult !== "object") return null;

  const nestedMarkdown =
    "markdown" in nestedResult
      ? (nestedResult as { markdown?: unknown }).markdown
      : undefined;
  const nestedModel =
    "used_model" in nestedResult
      ? (nestedResult as { used_model?: unknown }).used_model
      : undefined;
  if (typeof nestedMarkdown !== "string" || typeof nestedModel !== "string") return null;

  return { markdown: nestedMarkdown.trim(), usedModel: nestedModel };
};

const callSafetyAnalyzeApi = async ({
  imageFile
}: {
  imageFile: File;
}): Promise<AnalyzeImageSafetyResult> => {
  const requestBody = JSON.stringify({
    image_base64: await fileToBase64(imageFile),
    image_mime_type: getImageMimeType(imageFile)
  });

  const response = await fetch(ANALYZE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: requestBody
  });

  if (!response.ok) {
    const detail = await extractAnalyzeApiError(response);
    const message =
      detail?.error_message ||
      `analyze request failed: HTTP ${response.status} (${ANALYZE_ENDPOINT})`;

    if (detail?.error_type === "configuration_error") {
      throw new SafetyAnalysisErrorClass("CONFIG_MISSING", message);
    }
    if (detail?.error_type === "upstream_error") {
      throw new SafetyAnalysisErrorClass("PROVIDER_REQUEST_FAILED", message);
    }

    throw new SafetyAnalysisErrorClass("UNKNOWN", message);
  }

  const data: unknown = await response.json();
  const normalized = normalizeResultFromAnalyzeResponse(data);
  if (normalized === null) {
    throw new SafetyAnalysisErrorClass(
      "API_RESPONSE_INVALID",
      "analyze response markdown is missing."
    );
  }
  if (normalized.markdown.length === 0) {
    throw new SafetyAnalysisErrorClass(
      "EMPTY_RESPONSE",
      "analyze response markdown is empty."
    );
  }

  return normalized;
};

const isLikelyNetworkError = (error: unknown): boolean => {
  if (error instanceof TypeError) return true;
  if (!(error instanceof Error)) return false;

  const message = error.message.toLowerCase();
  return (
    message.includes("failed to fetch") ||
    message.includes("network") ||
    message.includes("econnreset") ||
    message.includes("timed out")
  );
};

export const analyzeSafetyImage = async ({
  imageFile
}: AnalyzeImageSafetyInput): Promise<AnalyzeImageSafetyResult> => {
  if (!imageFile) {
    throw new SafetyAnalysisErrorClass(
      "IMAGE_NOT_SELECTED",
      "分析を実行する前に画像を選択してください。"
    );
  }

  try {
    return await callSafetyAnalyzeApi({ imageFile });
  } catch (error) {
    if (error instanceof SafetyAnalysisErrorClass) {
      throw error;
    }

    const detailedMessage = getErrorMessage(error);

    if (isLikelyNetworkError(error)) {
      throw new SafetyAnalysisErrorClass(
        "NETWORK_ERROR",
        `AI解析呼び出し中にネットワークエラーが発生しました: ${detailedMessage}`,
        error
      );
    }

    throw new SafetyAnalysisErrorClass(
      "UNKNOWN",
      `AI解析呼び出し中に予期しないエラーが発生しました: ${detailedMessage}`,
      error
    );
  }
};
