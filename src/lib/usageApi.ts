import {
  USAGE_ENDPOINT, USAGE_EXCHANGE_RATE_ENDPOINT, USAGE_EXPORT_ENDPOINT,
  USAGE_PRICING_SETTINGS_ENDPOINT
} from "../constants/endpoints";

export type TokenAggregate = {
  known_total: number | null;
  known_count: number;
  unknown_count: number;
};
export type CostAggregate = {
  call_count: number;
  success_count: number;
  failure_count: number;
  pricing_unavailable_count: number;
  jpy_unavailable_count: number;
  input_tokens: TokenAggregate;
  output_tokens: TokenAggregate;
  thoughts_tokens: TokenAggregate;
  cached_tokens: TokenAggregate;
  total_tokens: TokenAggregate;
  estimated_cost_usd_subtotal: string | number | null;
  estimated_cost_usd_total: string | number | null;
  estimated_cost_jpy_subtotal: string | number | null;
  estimated_cost_jpy_total: string | number | null;
  average_cost_usd_known: string | number | null;
  average_cost_jpy_known: string | number | null;
  pricing_complete: boolean;
  jpy_pricing_complete: boolean;
};
export type UsageBreakdown = CostAggregate & { key: string; label: string };
export type UsageDetail = {
  usage_id: string;
  request_id: string;
  created_at: string;
  model: string;
  analysis_status: string;
  construction_id: string | null;
  construction_name: string;
  prompt_token_count: number | null;
  candidates_token_count: number | null;
  thoughts_token_count: number | null;
  cached_content_token_count: number | null;
  total_token_count: number | null;
  estimated_cost_usd: string | number | null;
  estimated_cost_jpy: string | number | null;
  exchange_rate_jpy_per_usd: string | number | null;
  exchange_rate_effective_date: string | null;
  pricing_status: "estimated" | "partial" | "unavailable";
  pricing_error_reason: string | null;
};
export type UsageResponse = {
  date_from: string;
  date_to: string;
  summary: CostAggregate;
  monthly: UsageBreakdown[];
  by_model: UsageBreakdown[];
  by_construction: UsageBreakdown[];
  details: UsageDetail[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  corrupt_json_count: number;
  read_failure_count: number;
  duplicate_count: number;
  aggregation_complete: boolean;
};
export type UsageFilters = {
  dateFrom: string;
  dateTo: string;
  constructionName?: string;
  model?: string;
  analysisState?: "" | "success" | "failure";
};
export type PricingSettings = {
  schema_version: number | null;
  exchange_rates: {
    exchange_rate_effective_date: string;
    jpy_per_usd: string | number | null;
    source: string | null;
  }[];
  revision: string | null;
  valid: boolean;
  editable: boolean;
  error: string | null;
};

const detail = async (response: Response, fallback: string): Promise<string> => {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
};

const usageParams = (filters: UsageFilters) => {
  const params = new URLSearchParams({
    date_from: filters.dateFrom,
    date_to: filters.dateTo
  });
  if (filters.constructionName?.trim()) params.set("construction_name", filters.constructionName.trim());
  if (filters.model) params.set("model", filters.model);
  if (filters.analysisState) params.set("analysis_state", filters.analysisState);
  return params;
};

export async function fetchUsage(filters: UsageFilters, page = 1): Promise<UsageResponse> {
  const params = usageParams(filters);
  params.set("page", String(page));
  params.set("page_size", "50");
  const response = await fetch(`${USAGE_ENDPOINT}?${params}`);
  if (!response.ok) throw new Error(await detail(response, "利用料金を取得できませんでした。"));
  return response.json();
}

export async function fetchPricingSettings(): Promise<PricingSettings> {
  const response = await fetch(USAGE_PRICING_SETTINGS_ENDPOINT);
  if (!response.ok) throw new Error(await detail(response, "料金設定を取得できませんでした。"));
  return response.json();
}

export async function saveExchangeRate(
  jpyPerUsd: string,
  expectedRevision: string
): Promise<PricingSettings> {
  const response = await fetch(USAGE_EXCHANGE_RATE_ENDPOINT, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jpy_per_usd: jpyPerUsd, expected_revision: expectedRevision })
  });
  if (!response.ok) throw new Error(await detail(response, "為替レートを保存できませんでした。"));
  return response.json();
}

export async function exportUsageExcel(filters: UsageFilters): Promise<void> {
  const response = await fetch(`${USAGE_EXPORT_ENDPOINT}?${usageParams(filters)}`);
  if (!response.ok) throw new Error(await detail(response, "Excelを出力できませんでした。"));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `利用料金_${filters.dateFrom}_${filters.dateTo}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
