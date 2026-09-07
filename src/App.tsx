import { useEffect, useMemo, useState } from "react";
import { AiSettingsStatusBar } from "./components/AiSettingsStatusBar";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { DevicePreviewFrame } from "./components/DevicePreviewFrame";
import { Header } from "./components/Header";
import { ImageUploadPanel } from "./components/ImageUploadPanel";
import { ResultTabs } from "./components/ResultTabs";
import { PDF_ENDPOINT } from "./constants/endpoints";
import { useGeminiSafetyAnalysis } from "./hooks/useGeminiSafetyAnalysis";
import { isAiMode } from "./types/ai";
import { buildPrintableBodyHtml } from "./utils/buildPrintableBodyHtml";
import { formatDisplayTimestamp, formatFileTimestamp } from "./utils/formatTimestamp";
import { fileToBase64, getImageMimeType } from "./utils/imageFile";
import { renderMarkdownToHtml } from "./utils/renderMarkdownToHtml";
import { sanitizeHtml } from "./utils/sanitizeHtml";
import type { AiMode } from "./types/ai";
import type { ResultTabKey } from "./types/ui";

const AI_MODE_STORAGE_KEY = "genba_safety_rag_app.ai_mode";
const DEFAULT_AI_MODE: AiMode = "gemini_a";
const PDF_REPORT_TITLE = "現場安全 危険分析レポート";

const getInitialAiMode = (): AiMode => {
  if (typeof window === "undefined") {
    return DEFAULT_AI_MODE;
  }

  const storedMode = window.localStorage.getItem(AI_MODE_STORAGE_KEY);
  return isAiMode(storedMode) ? storedMode : DEFAULT_AI_MODE;
};

const fileToDataUrl = async (file: File): Promise<string> => {
  const base64 = await fileToBase64(file);
  return `data:${getImageMimeType(file)};base64,${base64}`;
};

const blobToDataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }
      reject(new Error("画像データURLへの変換に失敗しました。"));
    };
    reader.onerror = () => reject(reader.error ?? new Error("画像読み込みに失敗しました。"));
    reader.readAsDataURL(blob);
  });

const fetchImageAsDataUrl = async (imageUrl: string): Promise<string | null> => {
  const response = await fetch(imageUrl);
  if (!response.ok) return null;
  const blob = await response.blob();
  return blobToDataUrl(blob);
};

const toDataUrlFromHistoryEntry = (
  imageBase64?: string,
  imageMimeType?: string
): string | null => {
  if (!imageBase64) return null;
  const mimeType = imageMimeType?.trim() || "image/jpeg";
  return `data:${mimeType};base64,${imageBase64}`;
};

const downloadPdfBlob = (blob: Blob, fileName: string): void => {
  const downloadUrl = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(downloadUrl);
};

function App() {
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [activeTab, setActiveTab] = useState<ResultTabKey>("overview");
  const [mode, setMode] = useState<AiMode>(() => getInitialAiMode());
  const [isSavingPdf, setIsSavingPdf] = useState(false);
  const {
    isAnalyzing,
    analysisMarkdown,
    analysisHistory,
    activeHistoryId,
    activeHistoryEntry,
    errorMessage,
    analyzeSelectedImage,
    showHistoryEntry,
    runtimeConfig
  } = useGeminiSafetyAnalysis(mode);

  const analysisHtml = useMemo(
    () => renderMarkdownToHtml(analysisMarkdown),
    [analysisMarkdown]
  );

  const localImagePreviewUrl = useMemo(() => {
    if (!selectedImage) return null;
    return URL.createObjectURL(selectedImage);
  }, [selectedImage]);
  const imagePreviewUrl = localImagePreviewUrl ?? activeHistoryEntry?.imageUrl ?? null;

  useEffect(() => {
    return () => {
      if (localImagePreviewUrl) URL.revokeObjectURL(localImagePreviewUrl);
    };
  }, [localImagePreviewUrl]);

  useEffect(() => {
    window.localStorage.setItem(AI_MODE_STORAGE_KEY, mode);
  }, [mode]);

  const handleSaveAsPdf = async () => {
    if (typeof window === "undefined") return;
    if (!analysisHtml.trim()) return;

    const reportHtml = sanitizeHtml(analysisHtml);
    if (!reportHtml) return;

    const generatedAt = new Date();
    const generatedAtText = formatDisplayTimestamp(generatedAt);
    const fileName = `安全分析レポート_${formatFileTimestamp(generatedAt)}.pdf`;
    setIsSavingPdf(true);

    try {
      const imageDataUrl = selectedImage
        ? await fileToDataUrl(selectedImage)
        : activeHistoryEntry?.imageUrl
          ? await fetchImageAsDataUrl(activeHistoryEntry.imageUrl)
          : toDataUrlFromHistoryEntry(
              activeHistoryEntry?.imageBase64,
              activeHistoryEntry?.imageMimeType
            );
      const printableBodyHtml = buildPrintableBodyHtml({
        generatedAtText,
        imagePreviewUrl: imageDataUrl,
        reportHtml,
        reportTitle: PDF_REPORT_TITLE
      });

      const response = await fetch(PDF_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          template_name: "report.html",
          output_filename: fileName,
          engine: "playwright",
          context: {
            title: PDF_REPORT_TITLE,
            body_html: printableBodyHtml
          }
        })
      });

      if (!response.ok) {
        throw new Error(`PDF生成に失敗しました (${response.status})`);
      }

      const pdfBlob = await response.blob();
      downloadPdfBlob(pdfBlob, fileName);
    } catch (error) {
      console.error("PDF保存に失敗しました:", error);
      window.alert("PDFの保存に失敗しました。もう一度お試しください。");
    } finally {
      setIsSavingPdf(false);
    }
  };

  const canSavePdf = analysisMarkdown.trim().length > 0 && !isAnalyzing;
  const handleSelectHistory = (historyId: string): void => {
    setSelectedImage(null);
    showHistoryEntry(historyId);
  };

  return (
    <div className="app-shell">
      <Header />

      <main className="app-main">
        <AiSettingsStatusBar
          mode={mode}
          onModeChange={setMode}
          runtimeConfig={runtimeConfig}
        />

        <div className="main-grid">
          <section className="operation-column">
            <ImageUploadPanel
              selectedImage={selectedImage}
              imagePreviewUrl={imagePreviewUrl}
              onImageChange={setSelectedImage}
            />

            <AnalysisPanel
              isAnalyzing={isAnalyzing}
              onAnalyze={() => {
                void analyzeSelectedImage(selectedImage);
              }}
            />
          </section>

          <section className="result-column">
            <DevicePreviewFrame imagePreviewUrl={imagePreviewUrl}>
              <ResultTabs
                activeTab={activeTab}
                onTabChange={setActiveTab}
                isAnalyzing={isAnalyzing}
                analysisMarkdown={analysisMarkdown}
                analysisHistory={analysisHistory}
                activeHistoryId={activeHistoryId}
                onSelectHistory={handleSelectHistory}
                errorMessage={errorMessage}
                canSaveAsPdf={canSavePdf}
                isSavingPdf={isSavingPdf}
                onSaveAsPdf={handleSaveAsPdf}
              />
            </DevicePreviewFrame>
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
