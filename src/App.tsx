import { useEffect, useMemo, useState } from "react";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { DevicePreviewFrame } from "./components/DevicePreviewFrame";
import { Header } from "./components/Header";
import { ImageUploadPanel } from "./components/ImageUploadPanel";
import { ResultTabs } from "./components/ResultTabs";
import { HistoryView } from "./components/HistoryView";
import { EXCEL_ENDPOINT, PDF_ENDPOINT } from "./constants/endpoints";
import { useGeminiSafetyAnalysis } from "./hooks/useGeminiSafetyAnalysis";
import { buildPrintableBodyHtml } from "./utils/buildPrintableBodyHtml";
import { formatDisplayTimestamp, formatFileTimestamp } from "./utils/formatTimestamp";
import { fileToBase64, getImageMimeType } from "./utils/imageFile";
import { renderMarkdownToHtml } from "./utils/renderMarkdownToHtml";
import { sanitizeHtml } from "./utils/sanitizeHtml";
import type { AnalysisHistoryEntry } from "./types/analysis";
import type { ResultTabKey } from "./types/ui";

const PDF_REPORT_TITLE = "現場安全 危険分析レポート";

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

const downloadBlob = (blob: Blob, fileName: string): void => {
  const downloadUrl = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(downloadUrl);
};

type ReportExportFormat = "pdf" | "excel";

type ReportExportData = {
  recordId: string | null;
  fileBaseName: string;
  generatedAtText: string;
  markdown: string;
  reportHtml: string;
  imageDataUrl: string | null;
  siteName: string;
  workContent: string;
  mainRisk: string;
  createdBy: string;
};

function App() {
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [activeTab, setActiveTab] = useState<ResultTabKey>("overview");
  const [isSavingPdf, setIsSavingPdf] = useState(false);
  const [isSavingExcel, setIsSavingExcel] = useState(false);
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
    showHistoryEntry
  } = useGeminiSafetyAnalysis();

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

  const prepareReportExport = async (historyEntry?: AnalysisHistoryEntry): Promise<ReportExportData | null> => {
    if (typeof window === "undefined") return null;
    const markdown = historyEntry?.markdown ?? analysisMarkdown;
    if (!markdown.trim()) return null;

    const reportHtml = sanitizeHtml(renderMarkdownToHtml(markdown));
    if (!reportHtml) return null;

    const generatedAt = new Date();
    const generatedAtText = formatDisplayTimestamp(generatedAt);
    const savedImageUrl = historyEntry?.imageUrl ?? activeHistoryEntry?.imageUrl;
    const imageDataUrl = !historyEntry && selectedImage
      ? await fileToDataUrl(selectedImage)
      : savedImageUrl
        ? await fetchImageAsDataUrl(savedImageUrl)
        : null;
    return {
      recordId: historyEntry?.id ?? activeHistoryId,
      fileBaseName: `安全分析レポート_${formatFileTimestamp(generatedAt)}`,
      generatedAtText,
      markdown,
      reportHtml,
      imageDataUrl,
      siteName: historyEntry?.siteName ?? siteName,
      workContent: historyEntry?.workContent ?? workContent,
      mainRisk: historyEntry?.mainRisk ?? mainRisk,
      createdBy: historyEntry?.createdBy ?? activeHistoryEntry?.createdBy ?? ""
    };
  };

  const generateReport = async (
    format: ReportExportFormat,
    historyEntry?: AnalysisHistoryEntry
  ): Promise<void> => {
    const report = await prepareReportExport(historyEntry);
    if (!report) return;
    const isPdf = format === "pdf";
    const extension = isPdf ? "pdf" : "xlsx";
    const fileName = `${report.fileBaseName}.${extension}`;
    const endpoint = isPdf ? PDF_ENDPOINT : EXCEL_ENDPOINT;
    if (isPdf) setIsSavingPdf(true);
    else setIsSavingExcel(true);

    try {
      const body = isPdf
        ? {
            template_name: "report.html",
            output_filename: fileName,
            engine: "playwright",
            record_id: report.recordId,
            context: {
              title: PDF_REPORT_TITLE,
              body_html: buildPrintableBodyHtml({
                generatedAtText: report.generatedAtText,
                imagePreviewUrl: report.imageDataUrl,
                reportHtml: report.reportHtml,
                reportTitle: PDF_REPORT_TITLE
              })
            }
          }
        : {
            output_filename: fileName,
            record_id: report.recordId,
            title: PDF_REPORT_TITLE,
            generated_at: report.generatedAtText,
            markdown: report.markdown,
            image_data_url: report.imageDataUrl,
            site_name: report.siteName,
            work_content: report.workContent,
            main_risk: report.mainRisk,
            created_by: report.createdBy
          };
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        throw new Error((await response.json()).detail || `${isPdf ? "PDF" : "Excel"}を保存できませんでした。`);
      }

      downloadBlob(await response.blob(), fileName);
    } finally {
      if (isPdf) setIsSavingPdf(false);
      else setIsSavingExcel(false);
    }
  };

  const generatePdf = (historyEntry?: AnalysisHistoryEntry): Promise<void> => generateReport("pdf", historyEntry);
  const generateExcel = (historyEntry?: AnalysisHistoryEntry): Promise<void> => generateReport("excel", historyEntry);

  const handleSaveAsPdf = (): void => {
    void generatePdf().catch((error: unknown) => {
      console.error("PDF保存に失敗しました:", error);
      window.alert(error instanceof Error ? error.message : "PDFの保存に失敗しました。");
    });
  };

  const handleSaveAsExcel = (): void => {
    void generateExcel().catch((error: unknown) => {
      console.error("Excel保存に失敗しました:", error);
      window.alert(error instanceof Error ? error.message : "Excelの保存に失敗しました。");
    });
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
    return <div className="app-shell"><Header /><HistoryView onOpenKy={() => setPage("create")} onSelect={handleSelectHistory} onSaveAsPdf={generatePdf} onSaveAsExcel={generateExcel} isSavingPdf={isSavingPdf} isSavingExcel={isSavingExcel} /></div>;
  }

  return (
    <div className="app-shell">
      <Header />

      <main className="app-main">
        <nav className="app-navigation" aria-label="メインメニュー">
          <button type="button" className="nav-button is-active">KY作成</button>
          <button type="button" className="nav-button" onClick={() => setPage("history")}>履歴</button>
        </nav>

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
                canSaveAsExcel={canSavePdf}
                isSavingExcel={isSavingExcel}
                onSaveAsExcel={handleSaveAsExcel}
              />
            </DevicePreviewFrame>
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
