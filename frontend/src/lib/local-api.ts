/**
 * Local API layer - replaces backend API calls with IndexedDB + Web Worker.
 *
 * Mirrors the interface of api.ts so pages need minimal changes.
 * Only billing and auth still go through the backend.
 */

import { db } from '@/db/index';
import {
  addWallet as dbAddWallet,
  getWallets as dbGetWallets,
  deleteWallet as dbDeleteWallet,
  getWalletAddresses,
  updateLastImported,
} from '@/db/wallets';
import {
  getTransactions as dbGetTransactions,
  getTransactionCount as dbGetTxCount,
  bulkUpsertTransactions,
} from '@/db/transactions';
import type { DBTransaction } from '@/db/index';
import type { SerializedTransaction } from '@/engine';
import { serializeTransaction, createTransaction } from '@/engine';
import { supabase } from '@/lib/supabase';

// Re-export types for compatibility
export type { Wallet } from '@/lib/api';
export type { ImportStatus } from '@/lib/api';
export type { TransactionPage, Transaction } from '@/lib/api';

// Re-export billing unchanged (still goes to backend)
export { billing } from '@/lib/api';

// In production (Vercel), use relative path to hit Next.js API proxy.
// In dev, call the backend directly.
const CHAIN_PROXY_URL = typeof window !== 'undefined' && process.env.NODE_ENV === 'production'
  ? ''  // relative - hits Next.js /api/chains/* proxy
  : (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000');

// ---------------------------------------------------------------------------
// Wallets - IndexedDB
// ---------------------------------------------------------------------------

export const localWallets = {
  list: async () => {
    const rows = await dbGetWallets();
    return rows.map((w) => ({
      id: w.id,
      address: w.address,
      chain: w.chain,
      label: w.label ?? undefined,
      last_imported_at: w.lastImportedAt ?? undefined,
      import_status: undefined as { status?: string; count?: number; error?: string } | undefined,
    }));
  },
  add: async (body: { address: string; chain: string; label?: string }) => {
    const id = crypto.randomUUID();
    await dbAddWallet({
      id,
      address: body.address.toLowerCase(),
      chain: body.chain.toLowerCase(),
      label: body.label,
    });
    return { id };
  },
  delete: async (id: string) => {
    await dbDeleteWallet(id);
  },
};

// ---------------------------------------------------------------------------
// Import - chain proxy + IndexedDB storage
// ---------------------------------------------------------------------------

// Track import states in memory (not persisted - page refresh resets)
const _importStates = new Map<string, {
  status: 'not_started' | 'running' | 'done' | 'error';
  count: number;
  error?: string;
}>();

function importKey(address: string, chain: string): string {
  return `${address.toLowerCase()}:${chain.toLowerCase()}`;
}

export const localImport = {
  trigger: async (address: string, chain: string) => {
    const key = importKey(address, chain);
    _importStates.set(key, { status: 'running', count: 0 });

    // Fetch from chain proxy in background
    _fetchAndStore(address, chain).catch((err) => {
      console.error('[import] Failed:', err);
      _importStates.set(key, { status: 'error', count: 0, error: err.message });
    });

    return { message: 'Import started' };
  },
  status: async (address: string, chain: string) => {
    const key = importKey(address, chain);
    const state = _importStates.get(key);
    if (!state) return { status: 'not_started' as const, count: 0 };
    return state;
  },
};

// EVM chains that use the /api/chains/evm/ prefix
const EVM_CHAINS = new Set([
  'ethereum', 'polygon', 'arbitrum', 'base', 'optimism',
  'bsc', 'avalanche', 'fantom', 'zksync', 'linea', 'scroll', 'mantle',
]);

async function _fetchFromProxy(
  path: string,
  headers: Record<string, string>,
): Promise<Record<string, unknown>[]> {
  const res = await fetch(`${CHAIN_PROXY_URL}/api/chains/${path}`, {
    method: 'GET',
    headers,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as Record<string, string>).detail ?? `Chain proxy error: ${res.status}`);
  }
  const data = await res.json();
  const txs = (data.transactions ?? data.result ?? []) as Record<string, unknown>[];

  // Surface upstream errors (e.g. invalid Etherscan API key)
  if (txs.length === 0 && data.raw_message) {
    throw new Error(`Chain API error: ${data.raw_message}`);
  }

  return txs;
}

async function _fetchAndStore(address: string, chain: string): Promise<void> {
  const key = importKey(address, chain);
  try {
    // Get auth token for tier-gated proxy
    const { data: { session } } = await supabase.auth.getSession();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (session?.access_token) {
      headers['Authorization'] = `Bearer ${session.access_token}`;
    }

    let rawTxs: Record<string, unknown>[] = [];

    if (EVM_CHAINS.has(chain.toLowerCase())) {
      // EVM: fetch normal txs + token transfers in parallel
      const [normalTxs, tokenTxs] = await Promise.all([
        _fetchFromProxy(`evm/${chain}/${address}?action=txlist&offset=10000`, headers),
        _fetchFromProxy(`evm/${chain}/${address}?action=tokentx&offset=10000`, headers),
      ]);
      rawTxs = [...normalTxs, ...tokenTxs];
    } else if (chain.toLowerCase() === 'bitcoin') {
      rawTxs = await _fetchFromProxy(`bitcoin/${address}`, headers);
    } else if (chain.toLowerCase() === 'solana') {
      rawTxs = await _fetchFromProxy(`solana/${address}`, headers);
    } else {
      // Cosmos chains
      rawTxs = await _fetchFromProxy(`cosmos/${chain}/${address}`, headers);
    }

    // Deduplicate by tx hash (normal + token transfers can share the same hash)
    const seen = new Set<string>();
    const uniqueTxs = rawTxs.filter((tx) => {
      const hash = String(tx.hash ?? tx.txHash ?? tx.tx_hash ?? '');
      if (!hash || seen.has(hash)) return false;
      seen.add(hash);
      return true;
    });

    // Convert to DB format and store
    const dbTxs: DBTransaction[] = uniqueTxs.map((tx: Record<string, unknown>) => {
      // Etherscan returns Unix timestamps (seconds), convert to ISO
      const rawTs = tx.timestamp ?? tx.timeStamp ?? '';
      const tsStr = String(rawTs);
      let isoTimestamp: string;
      if (/^\d{9,10}$/.test(tsStr)) {
        // Unix timestamp in seconds
        isoTimestamp = new Date(Number(tsStr) * 1000).toISOString();
      } else if (/^\d{13,}$/.test(tsStr)) {
        // Unix timestamp in milliseconds
        isoTimestamp = new Date(Number(tsStr)).toISOString();
      } else if (tsStr) {
        isoTimestamp = tsStr; // already ISO or other format
      } else {
        isoTimestamp = new Date().toISOString();
      }

      // Basic type detection from Etherscan data
      let txType: string | null = null;
      if (tx.tx_type) {
        txType = String(tx.tx_type);
      } else if (tx.token_symbol || tx.token_address) {
        txType = 'token_transfer';
      } else if (tx.functionName && String(tx.functionName).includes('swap')) {
        txType = 'swap';
      }

      return {
        txHash: String(tx.hash ?? tx.txHash ?? tx.tx_hash ?? ''),
        chain: chain.toLowerCase(),
        timestamp: isoTimestamp,
        txType,
        protocol: tx.protocol ? String(tx.protocol) : null,
        rawJson: JSON.stringify(tx),
      };
    });

    await bulkUpsertTransactions(dbTxs);

    // Update wallet's last imported timestamp
    const wallets = await dbGetWallets();
    const wallet = wallets.find(
      (w) => w.address === address.toLowerCase() && w.chain === chain.toLowerCase(),
    );
    if (wallet) {
      await updateLastImported(wallet.id, new Date().toISOString());
    }

    _importStates.set(key, { status: 'done', count: dbTxs.length });
  } catch (err) {
    _importStates.set(key, {
      status: 'error',
      count: 0,
      error: err instanceof Error ? err.message : String(err),
    });
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Transactions - IndexedDB
// ---------------------------------------------------------------------------

export const localTransactions = {
  list: async (params: {
    page?: number;
    page_size?: number;
    chain?: string;
    tx_type?: string;
    year?: number;
  }) => {
    const page = params.page ?? 1;
    const pageSize = params.page_size ?? 25;

    const total = await dbGetTxCount({
      chain: params.chain,
      txType: params.tx_type,
      year: params.year,
    });

    const rows = await dbGetTransactions({
      chain: params.chain,
      txType: params.tx_type,
      year: params.year,
      offset: (page - 1) * pageSize,
      limit: pageSize,
    });

    return {
      total,
      page,
      page_size: pageSize,
      pages: Math.ceil(total / pageSize),
      transactions: rows.map((r) => ({
        tx_hash: r.txHash,
        chain: r.chain,
        timestamp: r.timestamp,
        tx_type: r.txType ?? 'unknown',
        protocol: r.protocol ?? undefined,
      })),
    };
  },
  overrideCategory: async (txHash: string, chain: string, newType: string) => {
    await db.transactions
      .where('[txHash+chain]')
      .equals([txHash, chain.toLowerCase()])
      .modify({ txType: newType });
  },
};

// ---------------------------------------------------------------------------
// Calculate - Web Worker (via useTaxEngine hook)
//
// The dashboard uses these as adapters; the actual Worker communication
// goes through the useTaxEngine hook in the component.
// ---------------------------------------------------------------------------

/** Get all transactions as serialized engine format. */
export async function getAllSerializedTransactions(): Promise<SerializedTransaction[]> {
  const rows = await db.transactions.toArray();
  return rows.map((r) => {
    // If rawJson exists, try to reconstruct the full Transaction
    if (r.rawJson) {
      try {
        const raw = JSON.parse(r.rawJson);
        const tx = createTransaction({
          txHash: r.txHash,
          chain: r.chain,
          blockNumber: raw.blockNumber ?? raw.block_number ?? 0,
          timestamp: r.timestamp,
          fromAddress: raw.fromAddress ?? raw.from_address ?? raw.from ?? '',
          toAddress: raw.toAddress ?? raw.to_address ?? raw.to ?? '',
          txType: r.txType ?? 'unknown',
          assetsIn: raw.assetsIn ?? raw.assets_in ?? [],
          assetsOut: raw.assetsOut ?? raw.assets_out ?? [],
          fee: raw.fee ?? null,
          protocol: r.protocol,
          rawData: raw,
        });
        return serializeTransaction(tx);
      } catch {
        // fallback below
      }
    }

    // Minimal fallback
    return {
      txHash: r.txHash,
      chain: r.chain,
      blockNumber: 0,
      timestamp: r.timestamp,
      fromAddress: '',
      toAddress: '',
      txType: r.txType ?? 'unknown',
      assetsIn: [],
      assetsOut: [],
      fee: null,
      protocol: r.protocol,
      rawData: {},
    };
  });
}

/** Get all known wallet addresses for self-transfer detection. */
export async function getKnownWallets(): Promise<string[]> {
  return getWalletAddresses();
}
