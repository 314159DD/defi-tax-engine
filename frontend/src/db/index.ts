/**
 * Dexie (IndexedDB) database for crypto-tax client-side storage.
 *
 * Schema mirrors the Python SQLite schema from src/storage/database.py
 * with additions for user settings.
 *
 * All monetary values are stored as strings (serialized Decimals).
 * Deserialization to Decimal happens at the CRUD layer boundary.
 */

import Dexie, { type Table } from 'dexie';

// ---------------------------------------------------------------------------
// Row types (DB layer - all monetary values are strings)
// ---------------------------------------------------------------------------

export interface DBWallet {
  id: string;
  address: string;
  chain: string;
  label: string | null;
  lastImportedAt: string | null; // ISO
}

export interface DBTransaction {
  txHash: string;
  chain: string;
  timestamp: string; // ISO
  txType: string | null;
  protocol: string | null;
  rawJson: string | null; // JSON string of full transaction data
}

export interface DBTaxLot {
  id: string;
  token: string;
  amount: string; // Decimal as string
  costBasisUsd: string; // Decimal as string
  acquisitionDate: string; // ISO
  remaining: string; // Decimal as string
  source: string;
  txHash: string;
  method: string; // calculation method this lot belongs to
  spekulationsfristEnd: string | null; // ISO date
}

export interface DBDisposal {
  id: string;
  token: string;
  amount: string; // Decimal as string
  proceedsUsd: string; // Decimal as string
  costBasisUsd: string; // Decimal as string
  gainLossUsd: string; // Decimal as string
  holdingPeriod: string;
  method: string;
  disposalDate: string; // ISO
  txHash: string;
  year: number;
  country: string;
  lotsConsumedJson: string | null; // JSON string of LotConsumption[]
  exemptionJson: string | null; // JSON string of Exemption
  citationCode: string | null;
  citationText: string | null;
  citationSource: string | null;
  isGrayArea: number; // 0 | 1 (IndexedDB boolean)
}

export interface DBPriceCache {
  token: string;
  date: string; // YYYY-MM-DD
  usdPrice: string; // Decimal as string
  source: string | null;
}

export interface DBSettings {
  id: string; // always 'default'
  country: string;
  defaultMethod: string;
  currentYear: number;
  updatedAt: string; // ISO
}

// ---------------------------------------------------------------------------
// Database class
// ---------------------------------------------------------------------------

export class CryptoTaxDB extends Dexie {
  wallets!: Table<DBWallet, string>;
  transactions!: Table<DBTransaction, [string, string]>;
  taxLots!: Table<DBTaxLot, string>;
  disposals!: Table<DBDisposal, string>;
  priceCache!: Table<DBPriceCache, [string, string]>;
  settings!: Table<DBSettings, string>;

  constructor() {
    super('CryptoTaxDB');

    this.version(1).stores({
      // PK listed first, then indexed columns
      wallets: 'id, address, chain, [address+chain]',
      transactions: '[txHash+chain], txHash, chain, timestamp, txType',
      taxLots: 'id, token, method, txHash, [token+method]',
      disposals: 'id, token, method, year, country, txHash, [method+year+country]',
      priceCache: '[token+date], token, date',
      settings: 'id',
    });
  }
}

/** Singleton database instance. */
export const db = new CryptoTaxDB();
