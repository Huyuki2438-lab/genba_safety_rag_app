import { useMemo } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Clock3,
  Download,
  FileText,
  Info,
  Lightbulb,
  Loader2
} from "lucide-react";
import type { AnalysisSectionKey, AnalysisHistoryEntry } from "../types/analysis";
import type { ResultTabKey } from "../types/ui";
import { parseAnalysisSections } from "../utils/parseAnalysisSections";
import { renderMarkdownToHtml } from "../utils/renderMarkdownToHtml";
import { HtmlReport } from "./HtmlReport";

type ResultTabsProps = {
  activeTab: ResultTabKey;
  onTabChange: (tab: ResultTabKey) => void;
  isAnalyzing: boolean;
  analysisMarkdown: string;
  analysisHistory: AnalysisHistoryEntry[];
  activeHistoryId: string | null;
  onSelectHistory: (historyId: string) => void;
  errorMessage: string | null;
  canSaveAsPdf: boolean;
  isSavingPdf: boolean;
  onSaveAsPdf: () => void;
};

const tabItems: Array<{
  key: ResultTabKey;
  label: string;
  icon: typeof FileText;
}> = [
  { key: "overview", label: "概要", icon: FileText },
  { key: "risks", label: "リスク", icon: AlertTriangle },
  { key: "solutions", label: "対策", icon: Lightbulb },
  { key: "additional", label: "補足事項", icon: Info }
];

const sectionConfigByTab: Record<
  ResultTabKey,
  Array<{ key: AnalysisSectionKey; title: string }>
> = {
  overview: [
    { key: "OVERALL", title: "全体評価" },
    { key: "SUMMARY", title: "要約" }
  ],
  risks: [{ key: "RISKS", title: "リスク詳細" }],
  solutions: [{ key: "SOLUTIONS", title: "推奨対策" }],
  additional: [{ key: "ADDITIONAL", title: "補足事項" }]
};

const formatHistoryDate = (isoDate: string): string => {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return "日時不明";

  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
};

const toHistoryOptionLabel = (entry: AnalysisHistoryEntry): string => {
  return `${formatHistoryDate(entry.createdAt)} | ${entry.imageName}`;
};

export function ResultTabs({
  activeTab,
  onTabChange,
  isAnalyzing,
  analysisMarkdown,
  analysisHistory,
  activeHistoryId,
  onSelectHistory,
  errorMessage,
  canSaveAsPdf,
  isSavingPdf,
  onSaveAsPdf
}: ResultTabsProps) {
  const parsed = useMemo(() => parseAnalysisSections(analysisMarkdown), [analysisMarkdown]);
  const fullReportHtml = useMemo(
    () => renderMarkdownToHtml(analysisMarkdown),
    [analysisMarkdown]
  );
  const hasResult = analysisMarkdown.trim().length > 0;

  const tabSections = useMemo(() => {
    if (!parsed.hasStructuredSections) return [];

    return sectionConfigByTab[activeTab]
      .map(({ key, title }) => ({
        title,
        html: renderMarkdownToHtml(parsed.sections[key])
      }))
      .filter((section) => section.html.length > 0);
  }, [activeTab, parsed]);

  return (
    <section className="result-tabs">
      <div className="result-tabs__header">
        <div className="result-tablist" role="tablist" aria-label="分析結果タブ">
          {tabItems.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;

            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => onTabChange(tab.key)}
                className={["result-tab", isActive ? "is-active" : ""].join(" ")}
              >
                <Icon className="size-4" aria-hidden="true" />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="result-actions">
          <label className="history-picker" htmlFor="analysis-history-select">
            <Clock3 className="size-4" aria-hidden="true" />
            <span>過去の出力</span>
            <select
              id="analysis-history-select"
              className="history-picker__select"
              value={activeHistoryId ?? ""}
              onChange={(event) => {
                const historyId = event.target.value;
                if (!historyId) return;
                onSelectHistory(historyId);
              }}
              disabled={analysisHistory.length === 0 || isAnalyzing}
            >
              {analysisHistory.length === 0 ? (
                <option value="">履歴はまだありません</option>
              ) : (
                <>
                  <option value="">履歴を選択</option>
                  {analysisHistory.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {toHistoryOptionLabel(entry)}
                    </option>
                  ))}
                </>
              )}
            </select>
          </label>

          <button
            type="button"
            className="result-save-button"
            onClick={onSaveAsPdf}
            disabled={!canSaveAsPdf || isSavingPdf}
          >
            {isSavingPdf ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                PDF出力準備中...
              </>
            ) : (
              <>
                <Download className="size-4" aria-hidden="true" />
                PDFとして保存
              </>
            )}
          </button>
        </div>
      </div>

      <div className="report-panel">
        {errorMessage && hasResult && <p className="history-message" role="alert">{errorMessage}</p>}
        {isAnalyzing ? (
          <div className="report-status report-status--loading">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <p>危険分析を実行中です。しばらくお待ちください。</p>
          </div>
        ) : errorMessage && !hasResult ? (
          <div className="report-status report-status--error" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <p>{errorMessage}</p>
          </div>
        ) : !hasResult ? (
          <p className="report-empty">画像を選択して「危険分析を開始」を押すと、ここに結果が表示されます。</p>
        ) : !parsed.hasStructuredSections || tabSections.length === 0 ? (
          <HtmlReport html={fullReportHtml} />
        ) : (
          <div className="report-sections">
            {tabSections.map((section) => (
              <article key={section.title} className="report-section">
                <h3 className="report-section__title">{section.title}</h3>
                <HtmlReport html={section.html} />
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
