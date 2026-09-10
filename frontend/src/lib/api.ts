/**
 * API client for the FastAPI backend.
 * All fetch calls include the Supabase JWT.
 */

import { supabase } from "@/lib/supabase";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getToken(): Promise<string> {
  if (typeof window === "undefined") return "";
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token ?? "";
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

// ---------- Wallets ----------
export interface Wallet {
  id: string;
  address: string;
  chain: string;
  label?: string;
  last_imported_at?: string;
  import_status?: { status?: string; count?: number; error?: string };
}

export const wallets = {
  list: () => apiFetch<Wallet[]>("/api/wallets"),
  add: (body: { address: string; chain: string; label?: string }) =>
    apiFetch<{ id: string }>("/api/wallets", { method: "POST", body: JSON.stringify(body) }),
  delete: async (id: string) => {
    const token = await getToken();
    return fetch(`${BASE_URL}/api/wallets/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  },
};

// ---------- Import ----------
export interface ImportStatus {
  status: "not_started" | "running" | "done" | "error";
  count?: number;
  error?: string;
  started_at?: string;
  finished_at?: string;
}

export const importApi = {
  trigger: (address: string, chain: string, force = false) =>
    apiFetch<{ message: string }>("/api/import", {
      method: "POST",
      body: JSON.stringify({ address, chain, force }),
    }),
  status: (address: string, chain: string) =>
    apiFetch<ImportStatus>(`/api/import/status?address=${address}&chain=${chain}`),
};

// ---------- Transactions ----------
export interface Transaction {
  tx_hash: string;
  chain: string;
  timestamp: string;
  tx_type: string;
  protocol?: string;
  raw_data?: Record<string, unknown>;
}

export interface TransactionPage {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  transactions: Transaction[];
}

export const transactions = {
  list: (params: {
    page?: number;
    page_size?: number;
    chain?: string;
    tx_type?: string;
    year?: number;
    address?: string;
    missing_price?: boolean;
  }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) q.set(k, String(v));
    });
    return apiFetch<TransactionPage>(`/api/transactions?${q}`);
  },
  overrideCategory: (txHash: string, chain: string, newType: string) =>
    apiFetch(`/api/transactions/${txHash}/category`, {
      method: "PATCH",
      body: JSON.stringify({ tx_hash: txHash, chain, new_type: newType }),
    }),
};

// ---------- Calculate ----------
export interface TaxSummary {
  year: number;
  method: string;
  total_gains: string;
  total_losses: string;
  net_gain_loss: string;
  short_term: string;
  long_term: string;
  estimated_tax: string;
  transaction_count: number;
}

export interface MethodComparison {
  year: number;
  methods: Record<string, { total_gains: string; total_losses: string; net: string; count: number } | null>;
}

export interface YearOverYearResult {
  current_year: TaxSummary;
  previous_year: TaxSummary;
  deltas_pct: Record<string, string>;
}

export const calculate = {
  run: (method: string, year: number) =>
    apiFetch("/api/calculate", { method: "POST", body: JSON.stringify({ method, year }) }),
  summary: (year: number, method = "FIFO") =>
    apiFetch<TaxSummary>(`/api/calculate/summary?year=${year}&method=${method}`),
  compare: (year: number) =>
    apiFetch<MethodComparison>(`/api/calculate/compare?year=${year}`),
  yearOverYear: (year: number, method = "FIFO") =>
    apiFetch<YearOverYearResult>(`/api/calculate/year-over-year?year=${year}&method=${method}`),
};

// ---------- Reports ----------
export const reports = {
  downloadUrl: (type: "form8949" | "turbotax" | "schedule_d" | "json", year: number, method: string) =>
    `${BASE_URL}/api/reports/${type}?year=${year}&method=${method}`,
  harvest: () => apiFetch<{ suggestions: unknown[] }>("/api/reports/harvest"),
};

// ---------- German Tax (Spekulationsfrist / Freigrenze) ----------
export interface SpekulationsfristLot {
  token: string;
  amount: string;
  acquisition_date: string;
  days_remaining: number;
  status: "taxable" | "approaching" | "exempt";
  current_value: string;
  unrealized_gain: string;
  tax_if_sold_now: string;
  spekulationsfrist_end: string;
}

export interface SpekulationsfristResponse {
  lots: SpekulationsfristLot[];
}

export interface FreigrenzeResponse {
  realized_gains_ytd: string;
  freigrenze_limit: string;
  remaining_headroom: string;
  status: "safe" | "warning" | "exceeded";
  projected_tax_if_exceeded: string;
  year: number;
}

export const germanTax = {
  spekulationsfrist: () =>
    apiFetch<SpekulationsfristResponse>("/api/tax/de/spekulationsfrist"),
  freigrenze: (year: number) =>
    apiFetch<FreigrenzeResponse>(`/api/tax/de/freigrenze?year=${year}`),
};

// ---------- Billing ----------
export interface TierLimits {
  max_wallets: number | null;
  chains: string[];
  max_transactions: number | null;
  methods: string[];
  reports: string[];
  harvest: boolean;
  price_monthly: string | null;
  price_annual: string | null;
}

export interface BillingStatus {
  tier: string;
  limits: TierLimits;
  usage: { wallets: number; transactions: number };
}

export const billing = {
  tiers: () => apiFetch<Record<string, TierLimits>>("/api/billing/tiers"),
  status: () => apiFetch<BillingStatus>("/api/billing/status"),
  checkout: (tier: string, interval: "monthly" | "annual") =>
    apiFetch<{ url: string }>("/api/billing/create-checkout", {
      method: "POST",
      body: JSON.stringify({
        tier,
        interval,
        success_url: `${window.location.origin}/dashboard?upgraded=true`,
        cancel_url: `${window.location.origin}/pricing`,
      }),
    }),
  portal: () =>
    apiFetch<{ url: string }>(
      `/api/billing/portal?return_url=${encodeURIComponent(window.location.origin + "/dashboard")}`,
    ),
};
