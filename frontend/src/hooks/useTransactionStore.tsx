'use client'

/**
 * In-memory transaction store with optional IndexedDB persistence.
 *
 * Uses React context to share transaction state across components.
 * Falls back to memory-only if IndexedDB is unavailable.
 *
 * Sprint C.6
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { SerializedTransaction } from '@/engine'

// ---------------------------------------------------------------------------
// IndexedDB helpers (fail-safe - falls back silently)
// ---------------------------------------------------------------------------

const DB_NAME = 'crypto-tax-store'
const DB_VERSION = 1
const STORE_NAME = 'transactions'

function openDb(): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    if (typeof indexedDB === 'undefined') {
      resolve(null)
      return
    }
    try {
      const request = indexedDB.open(DB_NAME, DB_VERSION)
      request.onupgradeneeded = () => {
        const db = request.result
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'txHash' })
        }
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => resolve(null)
    } catch {
      resolve(null)
    }
  })
}

async function idbSave(txs: SerializedTransaction[]): Promise<void> {
  const db = await openDb()
  if (!db) return
  try {
    const txn = db.transaction(STORE_NAME, 'readwrite')
    const store = txn.objectStore(STORE_NAME)
    // Clear existing, then write all
    store.clear()
    for (const tx of txs) {
      store.put(tx)
    }
  } catch {
    // IndexedDB write failed - continue with memory-only
  }
}

async function idbLoad(): Promise<SerializedTransaction[]> {
  const db = await openDb()
  if (!db) return []
  return new Promise((resolve) => {
    try {
      const txn = db.transaction(STORE_NAME, 'readonly')
      const store = txn.objectStore(STORE_NAME)
      const request = store.getAll()
      request.onsuccess = () => resolve(request.result ?? [])
      request.onerror = () => resolve([])
    } catch {
      resolve([])
    }
  })
}

async function idbClear(): Promise<void> {
  const db = await openDb()
  if (!db) return
  try {
    const txn = db.transaction(STORE_NAME, 'readwrite')
    txn.objectStore(STORE_NAME).clear()
  } catch {
    // Silently fail
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface TransactionStoreValue {
  /** Current in-memory transactions. */
  transactions: SerializedTransaction[]
  /** Number of transactions currently stored. */
  transactionCount: number
  /** Whether the store is loading from IndexedDB. */
  loading: boolean
  /** Add transactions (deduplicates by txHash). */
  addTransactions: (txs: SerializedTransaction[]) => void
  /** Replace all transactions. */
  setTransactions: (txs: SerializedTransaction[]) => void
  /** Remove all transactions. */
  clearTransactions: () => void
}

const TransactionStoreContext = createContext<TransactionStoreValue | null>(null)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function TransactionStoreProvider({ children }: { children: ReactNode }) {
  const [transactions, setTransactionsState] = useState<SerializedTransaction[]>([])
  const [loading, setLoading] = useState(true)
  const initialLoadDone = useRef(false)

  // Load from IndexedDB on mount
  useEffect(() => {
    if (initialLoadDone.current) return
    initialLoadDone.current = true

    idbLoad().then((stored) => {
      if (stored.length > 0) {
        setTransactionsState(stored)
      }
      setLoading(false)
    })
  }, [])

  // Persist to IndexedDB whenever transactions change (skip initial empty state)
  useEffect(() => {
    if (loading) return
    idbSave(transactions)
  }, [transactions, loading])

  const addTransactions = useCallback((txs: SerializedTransaction[]) => {
    setTransactionsState((prev) => {
      const existing = new Set(prev.map((t) => t.txHash))
      const newTxs = txs.filter((t) => !existing.has(t.txHash))
      if (newTxs.length === 0) return prev
      return [...prev, ...newTxs]
    })
  }, [])

  const setTransactions = useCallback((txs: SerializedTransaction[]) => {
    setTransactionsState(txs)
  }, [])

  const clearTransactions = useCallback(() => {
    setTransactionsState([])
    idbClear()
  }, [])

  const value: TransactionStoreValue = {
    transactions,
    transactionCount: transactions.length,
    loading,
    addTransactions,
    setTransactions,
    clearTransactions,
  }

  return (
    <TransactionStoreContext.Provider value={value}>
      {children}
    </TransactionStoreContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Access the shared transaction store.
 *
 * Must be used within a <TransactionStoreProvider>.
 */
export function useTransactionStore(): TransactionStoreValue {
  const ctx = useContext(TransactionStoreContext)
  if (!ctx) {
    throw new Error(
      'useTransactionStore must be used within a <TransactionStoreProvider>',
    )
  }
  return ctx
}
