import { useEffect, useState } from "react";
import { deleteAnalysisHistory, fetchAnalysisHistory, type HistoryFilters } from "../lib/analysisHistoryApi";
import type { AnalysisHistoryEntry } from "../types/analysis";
import { HtmlReport } from "./HtmlReport";
import { renderMarkdownToHtml } from "../utils/renderMarkdownToHtml";

type Props = { onOpenKy: () => void; onSelect: (entry: AnalysisHistoryEntry) => void };
const blank: HistoryFilters = {};
const formatDate = (value: string) => new Intl.DateTimeFormat("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));

export function HistoryView({ onOpenKy, onSelect }: Props) {
  const [filters, setFilters] = useState<HistoryFilters>(blank);
  const [entries, setEntries] = useState<AnalysisHistoryEntry[]>([]);
  const [selected, setSelected] = useState<AnalysisHistoryEntry | null>(null);
  const [offset, setOffset] = useState(0);
  const [reports, setReports] = useState<{name: string; url: string}[]>([]);
  const [message, setMessage] = useState("");
  const load = async (next = filters, start = 0) => { try { setMessage(""); setEntries(await fetchAnalysisHistory(next, start)); setOffset(start); setSelected(null); } catch (error) { setMessage(error instanceof Error ? error.message : "共有データへ接続できません。"); } };
  useEffect(() => { void load(blank); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setReports([]);
    if (selected) void fetch(`/api/v1/history/${selected.id}/reports`).then(async r => {
      if (!r.ok) throw new Error("PDF一覧を取得できません。NASの接続を確認してください。");
      setReports((await r.json()).reports);
    }).catch(e => setMessage(String(e.message)));
  }, [selected]);
  const exportSelected = async () => {
    if (!selected) return;
    try {
      const r = await fetch(`/api/v1/history/${selected.id}/export`, {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      if (!r.ok) throw new Error((await r.json()).detail);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a"); a.href = url; a.download = `KY_${selected.id}.zip`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setMessage(e instanceof Error ? e.message : "書き出しできませんでした。"); }
  };
  const update = (key: keyof HistoryFilters, value: string) => setFilters((previous) => ({ ...previous, [key]: value }));
  const remove = async () => {
    if (!selected || !window.confirm("この履歴を削除しますか？ 写真は履歴から非表示になります。")) return;
    try { await deleteAnalysisHistory(selected.id); setSelected(null); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "削除できませんでした。"); }
  };
  return <main className="app-main history-page">
    <div className="page-actions"><button type="button" className="secondary-button compact" onClick={onOpenKy}>KY作成へ戻る</button></div>
    <section className="history-filters"><h2>履歴</h2><p>検索ボタンで他のPCの保存結果を取得できます。破損・未対応形式の履歴は表示されません。</p><div className="filter-grid">
      <label>開始日<input type="date" value={filters.dateFrom ?? ""} onChange={(e) => update("dateFrom", e.target.value)} /></label>
      <label>終了日<input type="date" value={filters.dateTo ?? ""} onChange={(e) => update("dateTo", e.target.value)} /></label>
      <label>現場名<input value={filters.siteName ?? ""} onChange={(e) => update("siteName", e.target.value)} /></label>
      <label>作業内容<input value={filters.workContent ?? ""} onChange={(e) => update("workContent", e.target.value)} /></label>
      <label>登録者<input value={filters.createdBy ?? ""} onChange={(e) => update("createdBy", e.target.value)} /></label>
      <label>キーワード<input value={filters.keyword ?? ""} onChange={(e) => update("keyword", e.target.value)} /></label>
    </div><button type="button" className="analyze-button compact" onClick={() => void load()}>検索</button></section>
    {message && <p className="history-message" role="alert">{message}</p>}
    <section className="history-table-wrap"><table className="history-table"><thead><tr><th>日時</th><th>写真</th><th>現場名</th><th>作業内容</th><th>主な危険</th><th>登録者</th></tr></thead><tbody>
      {entries.map((entry) => <tr key={entry.id} onClick={() => setSelected(entry)}><td>{formatDate(entry.createdAt)}</td><td>{entry.imageUrl && <img loading="lazy" src={entry.imageUrl} alt="写真なし" />}</td><td>{entry.siteName}</td><td>{entry.workContent}</td><td>{entry.mainRisk}</td><td>{entry.createdBy}</td></tr>)}
      {!entries.length && <tr><td colSpan={6}>該当する履歴はありません。</td></tr>}</tbody></table></section>
    <div className="page-actions"><button disabled={offset === 0} onClick={() => void load(filters, Math.max(0, offset - 50))}>前の50件</button><span>{offset + 1}件目から表示</span><button disabled={entries.length < 50} onClick={() => void load(filters, offset + 50)}>次の50件</button></div>
    {selected && <section className="history-detail"><div className="detail-actions"><h2>履歴詳細</h2><button type="button" onClick={() => void exportSelected()}>写真・結果・PDFを書き出す</button><button type="button" className="secondary-button compact" onClick={() => { onSelect(selected); onOpenKy(); }}>KY作成画面で再表示</button><button type="button" className="delete-button" onClick={() => void remove()}>削除</button></div>
      <div>{reports.map(report => <p key={report.name}><a href={report.url} target="_blank" rel="noreferrer">保存済みPDF：{report.name}</a></p>)}</div>
      <img className="history-detail__image" src={selected.imageUrl} alt={selected.imageName} /><dl><dt>解析日時</dt><dd>{formatDate(selected.createdAt)}</dd><dt>現場名</dt><dd>{selected.siteName || "－"}</dd><dt>作業内容</dt><dd>{selected.workContent || "－"}</dd><dt>抽出された危険</dt><dd>{selected.mainRisk || "－"}</dd><dt>登録者</dt><dd>{selected.createdBy}</dd></dl><h3>解析結果（想定される災害・安全対策・KY活動内容）</h3><HtmlReport html={renderMarkdownToHtml(selected.markdown)} />
    </section>}
  </main>;
}
