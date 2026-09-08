import { useEffect, useMemo, useState } from "react";
import { AiSettingsStatusBar } from "./components/AiSettingsStatusBar";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { DevicePreviewFrame } from "./components/DevicePreviewFrame";
import { Header } from "./components/Header";
import { ImageUploadPanel } from "./components/ImageUploadPanel";
import { ResultTabs } from "./components/ResultTabs";
import { HistoryView } from "./components/HistoryView";
import { PDF_ENDPOINT } from "./constants/endpoints";
import { useGeminiSafetyAnalysis } from "./hooks/useGeminiSafetyAnalysis";
import { isAiMode } from "./types/ai";
import { buildPrintableBodyHtml } from "./utils/buildPrintableBodyHtml";
import { formatDisplayTimestamp, formatFileTimestamp } from "./utils/formatTimestamp";
import { fileToBase64, getImageMimeType } from "./utils/imageFile";
import { renderMarkdownToHtml } from "./utils/renderMarkdownToHtml";
import { sanitizeHtml } from "./utils/sanitizeHtml";
import type { AiMode } from "./types/ai";
import type { AnalysisHistoryEntry } from "./types/analysis";
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
  const [page, setPage] = useState<"create" | "history">("create");
  const [siteName, setSiteName] = useState("");
  useEffect(() => { void fetch("/api/v1/project").then(r => r.json()).then(p => setSiteName(p.project_name)).catch(() => {}); }, []);
  const [workContent, setWorkContent] = useState("");
  const [mainRisk, setMainRisk] = useState("");
  const {
    pendingSave, retrySave,
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
          : null;
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
          record_id: activeHistoryId,
          context: {
            title: PDF_REPORT_TITLE,
            body_html: printableBodyHtml
          }
        })
      });

      if (!response.ok) {
        throw new Error((await response.json()).detail || "PDFを保存できませんでした。");
      }

      const pdfBlob = await response.blob();
      downloadPdfBlob(pdfBlob, fileName);
    } catch (error) {
      console.error("PDF保存に失敗しました:", error);
      window.alert(error instanceof Error ? error.message : "PDFの保存に失敗しました。");
    } finally {
      setIsSavingPdf(false);
    }
  };

  const canSavePdf = analysisMarkdown.trim().length > 0 && !isAnalyzing;
  const handleSelectHistory = (entry: AnalysisHistoryEntry): void => {
    setSelectedImage(null);
    setSiteName(entry.siteName);
    setWorkContent(entry.workContent);
    setMainRisk(entry.mainRisk);
    showHistoryEntry(entry);
  };

  if (page === "history") {
    return <div className="app-shell"><Header /><HistoryView onOpenKy={() => setPage("create")} onSelect={handleSelectHistory} /></div>;
  }

  return (
    <div className="app-shell">
      <Header />

      <main className="app-main">
        <nav className="app-navigation" aria-label="メインメニュー">
          <button type="button" className="nav-button is-active">KY作成</button>
          <button type="button" className="nav-button" onClick={() => setPage("history")}>履歴</button>
        </nav>
        <AiSettingsStatusBar
          mode={mode}
          onModeChange={setMode}
          runtimeConfig={runtimeConfig}
        />

        {pendingSave && !isAnalyzing && <div role="alert"><p>分析結果はまだ保存されていません。NAS復旧後、先に履歴で保存済みか確認してください。</p><button onClick={() => void retrySave()}>分析結果の保存を再試行</button></div>}
        <div className="main-grid">
          <section className="operation-column">
            <ImageUploadPanel
              selectedImage={selectedImage}
              imagePreviewUrl={imagePreviewUrl}
              onImageChange={setSelectedImage}
            />

            <section className="upload-panel metadata-panel">
              <h2 className="panel-title">2. 記録情報</h2>
              <label>現場名<input value={siteName} onChange={(event) => setSiteName(event.target.value)} placeholder="例：芝原" /></label>
              <label>作業内容<input value={workContent} onChange={(event) => setWorkContent(event.target.value)} placeholder="例：掘削" /></label>
              <label>主な危険<input value={mainRisk} onChange={(event) => setMainRisk(event.target.value)} placeholder="例：重機接触" /></label>
            </section>

            <AnalysisPanel
              isAnalyzing={isAnalyzing}
              onAnalyze={() => {
                void analyzeSelectedImage(selectedImage, { siteName, workContent, mainRisk });
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
                onSelectHistory={(historyId) => {
                  const entry = analysisHistory.find((item) => item.id === historyId);
                  if (entry) handleSelectHistory(entry);
                }}
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
