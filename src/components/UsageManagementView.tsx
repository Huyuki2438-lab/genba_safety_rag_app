import { useEffect, useMemo, useState } from "react";
import {
  exportUsageExcel, fetchPricingSettings, fetchUsage, saveExchangeRate,
  type CostAggregate, type PricingSettings,
  type UsageBreakdown, type UsageFilters, type UsageResponse
} from "../lib/usageApi";

const isoDate = (value: Date) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};
const today = new Date();
const initialFilters: UsageFilters = {
  dateFrom: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
  dateTo: isoDate(today),
  analysisState: ""
};
const number = (value: number | null) => value === null ? "未取得" : value.toLocaleString("ja-JP");
const money = (value: string | number | null, currency: "USD" | "JPY") => {
  if (value === null) return "未確定";
  const digits = currency === "USD" ? 6 : 2;
  return new Intl.NumberFormat("ja-JP", {
    style: "currency", currency, minimumFractionDigits: currency === "USD" ? 4 : 0,
    maximumFractionDigits: digits
  }).format(Number(value));
};
const cost = (summary: CostAggregate, currency: "USD" | "JPY") => {
  const complete = currency === "USD" ? summary.pricing_complete : summary.jpy_pricing_complete;
  const total = currency === "USD" ? summary.estimated_cost_usd_total : summary.estimated_cost_jpy_total;
  const subtotal = currency === "USD" ? summary.estimated_cost_usd_subtotal : summary.estimated_cost_jpy_subtotal;
  if (complete) return money(total, currency);
  return subtotal === null ? "未確定" : `${money(subtotal, currency)}（計算可能分）`;
};
const formatDate = (value: string) => new Intl.DateTimeFormat("ja-JP", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
}).format(new Date(value));
const statusLabel = (status: string) => status === "success" ? "成功" : "失敗";
const pricingLabel = (status: string) => ({
  estimated: "推定済み", partial: "一部未確定", unavailable: "未確定"
}[status] ?? status);

function BreakdownTable({ title, rows }: { title: string; rows: UsageBreakdown[] }) {
  return <section className="usage-section">
    <h2>{title}</h2>
    <div className="history-table-wrap"><table className="history-table usage-breakdown-table">
      <thead><tr><th>区分</th><th>API呼出し</th><th>料金（USD）</th><th>料金（JPY）</th><th>未確定</th></tr></thead>
      <tbody>
        {rows.map(row => <tr key={row.key}><td>{row.label}</td><td>{row.call_count.toLocaleString()}</td>
          <td>{cost(row, "USD")}</td><td>{cost(row, "JPY")}</td><td>{row.jpy_unavailable_count}</td></tr>)}
        {!rows.length && <tr><td colSpan={5}>該当データはありません。</td></tr>}
      </tbody>
    </table></div>
  </section>;
}

export function UsageManagementView() {
  const [filters, setFilters] = useState<UsageFilters>(initialFilters);
  const [result, setResult] = useState<UsageResponse | null>(null);
  const [pricing, setPricing] = useState<PricingSettings | null>(null);
  const [rateInput, setRateInput] = useState("");
  const [appliedFilters, setAppliedFilters] = useState<UsageFilters>(initialFilters);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [savingRate, setSavingRate] = useState(false);
  const [exporting, setExporting] = useState(false);
  const load = async (page = 1, next = filters) => {
    setLoading(true); setMessage("");
    try {
      setResult(await fetchUsage(next, page));
      setAppliedFilters({ ...next });
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "利用料金を取得できませんでした。"); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    void load(1, initialFilters);
    void fetchPricingSettings().then(value => {
      setPricing(value);
      const latest = [...value.exchange_rates].sort((a, b) =>
        b.exchange_rate_effective_date.localeCompare(a.exchange_rate_effective_date))[0];
      setRateInput(latest?.jpy_per_usd === null || latest?.jpy_per_usd === undefined
        ? "" : String(latest.jpy_per_usd));
    }).catch(error => setMessage(String(error)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const models = useMemo(() => Array.from(new Set(result?.by_model.map(item => item.key) ?? [])), [result]);
  const update = (key: keyof UsageFilters, value: string) =>
    setFilters(previous => ({ ...previous, [key]: value }));
  const saveRate = async () => {
    const normalized = rateInput.trim();
    const numericRate = Number(normalized);
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized) || !Number.isFinite(numericRate) || numericRate <= 0) {
      setMessage("為替レートは0より大きい数値を入力してください。");
      return;
    }
    if (!pricing?.valid || !pricing.revision) {
      setMessage("料金設定を読み込んでから再試行してください。");
      return;
    }
    setSavingRate(true); setMessage("");
    try {
      const updated = await saveExchangeRate(normalized, pricing.revision);
      setPricing(updated);
      const latest = [...updated.exchange_rates].sort((a, b) =>
        b.exchange_rate_effective_date.localeCompare(a.exchange_rate_effective_date))[0];
      setRateInput(latest?.jpy_per_usd === null || latest?.jpy_per_usd === undefined
        ? "" : String(latest.jpy_per_usd));
      try {
        setResult(await fetchUsage(appliedFilters, 1));
        setMessage("為替レートを保存し、集計と明細を更新しました。");
      } catch (error) {
        setMessage(`為替レートは保存しましたが、集計の再取得に失敗しました。${error instanceof Error ? error.message : ""}`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "為替レートを保存できませんでした。");
    } finally {
      setSavingRate(false);
    }
  };
  const exportExcel = async () => {
    setExporting(true); setMessage("");
    try { await exportUsageExcel(appliedFilters); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Excelを出力できませんでした。"); }
    finally { setExporting(false); }
  };

  return <div className="usage-page">
    <section className="usage-section">
      <div className="usage-heading"><div><h1>利用料金管理</h1><p>API呼出し単位の利用実績と推定料金です。解析履歴件数とは異なります。</p></div>
        <div className="usage-rate">
          <strong>為替レート</strong>
          <div className="usage-rate-input"><span>1 USD =</span>
            <input aria-label="1 USDあたりの円" inputMode="decimal" value={rateInput}
              onChange={event => setRateInput(event.target.value)} placeholder="未設定" />
            <span>円</span>
          </div>
          <button type="button" className="analyze-button compact" disabled={savingRate || !pricing?.valid}
            onClick={() => void saveRate()}>{savingRate ? "保存中..." : "為替レートを保存"}</button>
          {pricing?.valid && pricing.exchange_rates.length > 0 && <small>最新の適用日：{[...pricing.exchange_rates]
            .sort((a, b) => b.exchange_rate_effective_date.localeCompare(a.exchange_rate_effective_date))[0].exchange_rate_effective_date}</small>}
          {!pricing?.valid && <small>{pricing?.error ?? "読み込み中..."}</small>}
        </div>
      </div>
    </section>

    {message && <p className="history-message" role="alert">{message}</p>}
    {result && <section className="usage-summary" aria-label="概要">
      <div><span>API呼出し数</span><strong>{result.summary.call_count.toLocaleString()}</strong></div>
      <div><span>推定料金（USD）</span><strong>{cost(result.summary, "USD")}</strong></div>
      <div><span>推定料金（JPY）</span><strong>{cost(result.summary, "JPY")}</strong></div>
      <div><span>1回平均（USD・計算可能分）</span><strong>{money(result.summary.average_cost_usd_known, "USD")}</strong></div>
      <div><span>合計トークン</span><strong>{number(result.summary.total_tokens.known_total)}</strong>
        {result.summary.total_tokens.unknown_count > 0 && <small>未取得 {result.summary.total_tokens.unknown_count}件</small>}</div>
      <div><span>料金未確定</span><strong>{result.summary.jpy_unavailable_count.toLocaleString()}件</strong></div>
    </section>}

    <section className="history-filters history-search-panel usage-section"><h2>検索条件</h2><div className="filter-grid">
      <label>開始日<input type="date" value={filters.dateFrom} onChange={e => update("dateFrom", e.target.value)} /></label>
      <label>終了日<input type="date" value={filters.dateTo} onChange={e => update("dateTo", e.target.value)} /></label>
      <label>工事名<input value={filters.constructionName ?? ""} onChange={e => update("constructionName", e.target.value)} /></label>
      <label>モデル<select value={filters.model ?? ""} onChange={e => update("model", e.target.value)}><option value="">すべて</option>{models.map(model => <option key={model}>{model}</option>)}</select></label>
      <label>解析状態<select value={filters.analysisState ?? ""} onChange={e => update("analysisState", e.target.value)}><option value="">すべて</option><option value="success">成功</option><option value="failure">失敗</option></select></label>
      <button type="button" className="analyze-button compact history-search-button" disabled={loading} onClick={() => void load()}>{loading ? "集計中..." : "検索"}</button>
      <button type="button" className="secondary-button compact" disabled={exporting || !result}
        onClick={() => void exportExcel()}>{exporting ? "Excel出力中..." : "Excel出力"}</button>
    </div></section>

    {result && <>
      {!result.aggregation_complete && <p className="usage-warning" role="alert">台帳の読み取りに不完全な箇所があります。破損 {result.corrupt_json_count}件、読み取り失敗 {result.read_failure_count}件。表示金額は完全な期間合計ではありません。</p>}
      {result.duplicate_count > 0 && <p className="usage-note">重複台帳 {result.duplicate_count}件は二重計上していません。</p>}
      <section className="usage-section"><h2>料金明細</h2><div className="history-table-wrap"><table className="history-table usage-detail-table">
        <thead><tr><th>解析日時</th><th>工事名</th><th>モデル名</th><th>入力</th><th>出力</th><th>思考</th><th>合計</th><th>USD</th><th>JPY</th><th>解析状態</th><th>料金計算状態</th></tr></thead>
        <tbody>{result.details.map(item => <tr key={item.usage_id}>
          <td>{formatDate(item.created_at)}</td><td>{item.construction_name}</td><td>{item.model}</td>
          <td>{number(item.prompt_token_count)}</td><td>{number(item.candidates_token_count)}</td><td>{number(item.thoughts_token_count)}</td><td>{number(item.total_token_count)}</td>
          <td>{money(item.estimated_cost_usd, "USD")}</td><td>{money(item.estimated_cost_jpy, "JPY")}</td>
          <td>{statusLabel(item.analysis_status)}</td><td title={item.pricing_error_reason ?? ""}>{pricingLabel(item.pricing_status)}</td>
        </tr>)}{!result.details.length && <tr><td colSpan={11}>該当データはありません。</td></tr>}</tbody>
      </table></div>
      <div className="page-actions"><button disabled={result.page <= 1 || loading} onClick={() => void load(result.page - 1, appliedFilters)}>前の50件</button><span>{result.total_items}件中 {result.details.length ? (result.page - 1) * result.page_size + 1 : 0}件目から表示</span><button disabled={result.page >= result.total_pages || loading} onClick={() => void load(result.page + 1, appliedFilters)}>次の50件</button></div>
      </section>
      <div className="usage-aggregates"><BreakdownTable title="月別料金" rows={result.monthly} /><BreakdownTable title="モデル別料金" rows={result.by_model} /><BreakdownTable title="工事別料金" rows={result.by_construction} /></div>
    </>}
  </div>;
}
