import { useEffect, useMemo, useRef, useState } from "react";
import type { AppPage } from "./components/AppNavigation";
import { AnalysisPanel } from "./components/AnalysisPanel";
import { DevicePreviewFrame } from "./components/DevicePreviewFrame";
import { Header } from "./components/Header";
import { ImageUploadPanel } from "./components/ImageUploadPanel";
import { ResultTabs, ResultToolbar } from "./components/ResultTabs";
import { HistoryView } from "./components/HistoryView";
import { SettingsView } from "./components/SettingsView";
import { SetupWizard } from "./components/SetupWizard";
import { StorageUnavailableScreen } from "./components/StorageUnavailableScreen";
import { EXCEL_ENDPOINT, PDF_ENDPOINT } from "./constants/endpoints";
import { fetchLastRegistrant, saveLastRegistrant } from "./lib/analysisHistoryApi";
import { BACKEND_UNREACHABLE_MESSAGE, fetchSetupStatus, type SetupStatus } from "./lib/storageSetupApi";
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

const HASH_BY_PAGE: Record<AppPage, string> = { create: "#/", history: "#/history", settings: "#/settings" };

const pageFromHash = (): AppPage => {
  if (window.location.hash === HASH_BY_PAGE.history) return "history";
  if (window.location.hash === HASH_BY_PAGE.settings) return "settings";
  return "create";
};

function App() {
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [activeTab, setActiveTab] = useState<ResultTabKey>("overview");
  const [isSavingPdf, setIsSavingPdf] = useState(false);
  const [isSavingExcel, setIsSavingExcel] = useState(false);
  const [page, setPage] = useState<AppPage>(pageFromHash);
  const pageRef = useRef(page);
  pageRef.current = page;
  useEffect(() => {
    const onPopState = (): void => {
      const next = pageFromHash();
      // 設定画面を離れるときは保存先の状態を再取得する
      if (pageRef.current === "settings" && next !== "settings") refreshStorageStatus();
      setPage(next);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const navigate = (next: AppPage): void => {
    if (next === page) return;
    window.history.pushState(null, "", HASH_BY_PAGE[next]);
    if (page === "settings") refreshStorageStatus();
    setPage(next);
  };
  const [siteName, setSiteName] = useState("");
  const [storageStatus, setStorageStatus] = useState<SetupStatus | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const refreshStorageStatus = (): void => {
    setStorageStatus(null);
    setBackendError(null);
    // 通信失敗を「未設定」と取り違えて初回セットアップ画面を出さない(出すと以降の操作が全て通信失敗になる)。
    void fetchSetupStatus()
      .then(setStorageStatus)
      .catch((error: unknown) => setBackendError(error instanceof Error ? error.message : BACKEND_UNREACHABLE_MESSAGE));
  };
  useEffect(refreshStorageStatus, []);
  const storageReady = storageStatus?.configured && storageStatus.reachable;
  useEffect(() => {
    if (storageReady) {
      void fetch("/api/v1/project").then(r => r.json()).then(p => setSiteName(p.project_name)).catch(() => {});
    }
  }, [storageReady]);
  const [createdBy, setCreatedBy] = useState("");
  useEffect(() => {
    void fetchLastRegistrant().then(name => setCreatedBy(current => current || name)).catch(() => {});
  }, []);
  const [workContent, setWorkContent] = useState("");
  const [mainRisk, setMainRisk] = useState("");
  const {
    pendingSave, retrySave,
    isAnalyzing,
    analysisMarkdown,
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

  if (backendError !== null) {
    return (
      <div className="app-shell">
        <Header />
        <main className="app-main">
          <div className="setup-wizard__card" role="alert">
            <h2 className="panel-title">アプリ内部と通信できません</h2>
            <p>{backendError}</p>
            <p>アプリを一度終了して起動し直してください。古いブラウザのタブを開いたままの場合は、そのタブを閉じて、新しく開いたウィンドウを使ってください。</p>
            <div className="page-actions">
              <button type="button" className="nav-button is-active" onClick={refreshStorageStatus}>再試行</button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (storageStatus === null) {
    return <div className="app-shell"><Header /><main className="app-main"><p>読み込み中...</p></main></div>;
  }

  if (!storageStatus.configured) {
    return <SetupWizard />;
  }

  if (!storageStatus.reachable && page !== "settings") {
    return (
      <StorageUnavailableScreen
        message={storageStatus.reachableMessage}
        onRetry={refreshStorageStatus}
        onChangeStorage={() => navigate("settings")}
      />
    );
  }

  if (page === "history") {
    return (
      <div className="app-shell">
        <Header activePage="history" onNavigate={navigate} />
        <main className="app-main">
          <HistoryView onOpenKy={() => navigate("create")} onSelect={handleSelectHistory} onSaveAsPdf={generatePdf} onSaveAsExcel={generateExcel} isSavingPdf={isSavingPdf} isSavingExcel={isSavingExcel} />
        </main>
      </div>
    );
  }

  if (page === "settings") {
    return (
      <div className="app-shell">
        <Header activePage="settings" onNavigate={navigate} />
        <main className="app-main">
          <SettingsView />
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Header activePage="create" onNavigate={navigate} />

      <main className="app-main">
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
              <div className="metadata-row">
                <label>現場名<input value={siteName} onChange={(event) => setSiteName(event.target.value)} placeholder="例：芝原" /></label>
                <label>登録者名<input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} placeholder="例：山田" maxLength={255} /></label>
              </div>
              <label>作業内容<input value={workContent} onChange={(event) => setWorkContent(event.target.value)} placeholder="例：掘削" /></label>
              <label>主な危険（任意）<input value={mainRisk} onChange={(event) => setMainRisk(event.target.value)} placeholder="例：重機接触" /></label>
            </section>

            <AnalysisPanel
              isAnalyzing={isAnalyzing}
              onAnalyze={() => {
                if (createdBy.trim()) saveLastRegistrant(createdBy.trim());
                void analyzeSelectedImage(selectedImage, { siteName, workContent, mainRisk, createdBy: createdBy.trim() });
              }}
            />
          </section>

          <section className="result-column">
            <DevicePreviewFrame
              imagePreviewUrl={imagePreviewUrl}
              toolbar={(
                <ResultToolbar
                  activeTab={activeTab}
                  onTabChange={setActiveTab}
                  canSaveAsPdf={canSavePdf}
                  isSavingPdf={isSavingPdf}
                  onSaveAsPdf={handleSaveAsPdf}
                  canSaveAsExcel={canSavePdf}
                  isSavingExcel={isSavingExcel}
                  onSaveAsExcel={handleSaveAsExcel}
                />
              )}
            >
              <ResultTabs
                activeTab={activeTab}
                isAnalyzing={isAnalyzing}
                analysisMarkdown={analysisMarkdown}
                errorMessage={errorMessage}
              />
            </DevicePreviewFrame>
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
