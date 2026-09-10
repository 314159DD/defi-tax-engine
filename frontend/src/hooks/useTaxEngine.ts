'use client'

/**
 * React hook for running tax calculations via the Web Worker.
 *
 * Spawns a single Worker instance per component lifetime and communicates
 * via the typed WorkerRequest / WorkerResponse protocol.
 *
 * Sprint C.6
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  WorkerRequest,
  WorkerResponse,
  SerializedTransaction,
  SerializedDisposal,
  SerializedTaxLot,
  SerializedTaxSummary,
} from '@/engine'
import type {
  CalculateResult as WorkerCalculateResult,
  CategorizeResult as WorkerCategorizeResult,
  ParseCsvResult as WorkerParseCsvResult,
  CompareResult as WorkerCompareResult,
} from '@/engine/worker-types'

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export type TaxEngineStatus =
  | 'idle'
  | 'parsing'
  | 'categorizing'
  | 'calculating'
  | 'comparing'
  | 'done'
  | 'error'

/** Deserialized calculate result as returned from the worker. */
export interface CalculateResultData {
  disposals: SerializedDisposal[]
  lots: SerializedTaxLot[]
  summary: SerializedTaxSummary
}

export interface TaxEngineState {
  status: TaxEngineStatus
  progress: number // 0-100
  progressMessage: string
  result: CalculateResultData | null
  categorized: SerializedTransaction[] | null
  parsed: SerializedTransaction[] | null
  comparison: Record<string, SerializedTaxSummary> | null
  error: string | null
}

const INITIAL_STATE: TaxEngineState = {
  status: 'idle',
  progress: 0,
  progressMessage: '',
  result: null,
  categorized: null,
  parsed: null,
  comparison: null,
  error: null,
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTaxEngine() {
  const workerRef = useRef<Worker | null>(null)
  const [state, setState] = useState<TaxEngineState>(INITIAL_STATE)

  // Lazily create and wire up the Worker
  const getWorker = useCallback(() => {
    if (!workerRef.current) {
      workerRef.current = new Worker(
        new URL('@/engine/worker.ts', import.meta.url),
        { type: 'module' },
      )

      workerRef.current.onmessage = (e: MessageEvent<WorkerResponse>) => {
        const msg = e.data

        switch (msg.type) {
          case 'progress':
            setState((s) => ({
              ...s,
              progress: msg.percent,
              progressMessage: msg.message,
            }))
            break

          case 'calculate-result': {
            const calcMsg = msg as WorkerCalculateResult
            setState((s) => ({
              ...s,
              status: 'done',
              progress: 100,
              result: {
                disposals: calcMsg.disposals,
                lots: calcMsg.lots,
                summary: calcMsg.summary,
              },
              error: null,
            }))
            break
          }

          case 'categorize-result':
            setState((s) => ({
              ...s,
              status: 'done',
              progress: 100,
              categorized: (msg as WorkerCategorizeResult).transactions,
              error: null,
            }))
            break

          case 'parse-csv-result':
            setState((s) => ({
              ...s,
              status: 'done',
              progress: 100,
              parsed: (msg as WorkerParseCsvResult).transactions,
              error: null,
            }))
            break

          case 'compare-result':
            setState((s) => ({
              ...s,
              status: 'done',
              progress: 100,
              comparison: (msg as WorkerCompareResult).comparison,
              error: null,
            }))
            break

          case 'error':
            setState((s) => ({
              ...s,
              status: 'error',
              error: msg.message,
            }))
            break

          default:
            // Spekulationsfrist / Freigrenze results handled by dedicated hooks
            break
        }
      }

      workerRef.current.onerror = (err) => {
        setState((s) => ({
          ...s,
          status: 'error',
          error: err.message ?? 'Worker error',
        }))
      }
    }
    return workerRef.current
  }, [])

  // ── Commands ──────────────────────────────────────────────────────

  const calculate = useCallback(
    (
      transactions: SerializedTransaction[],
      method: 'FIFO' | 'LIFO' | 'HIFO',
      country: 'US' | 'DE',
      year?: number,
      knownWallets: string[] = [],
    ) => {
      setState({
        ...INITIAL_STATE,
        status: 'calculating',
      })
      const req: WorkerRequest = {
        type: 'calculate',
        transactions,
        method,
        country,
        year,
        knownWallets,
      }
      getWorker().postMessage(req)
    },
    [getWorker],
  )

  const categorize = useCallback(
    (transactions: SerializedTransaction[], knownWallets: string[] = []) => {
      setState({
        ...INITIAL_STATE,
        status: 'categorizing',
      })
      const req: WorkerRequest = {
        type: 'categorize',
        transactions,
        knownWallets,
      }
      getWorker().postMessage(req)
    },
    [getWorker],
  )

  const parseCSV = useCallback(
    (csvText: string, format: string = 'unknown') => {
      setState({
        ...INITIAL_STATE,
        status: 'parsing',
      })
      const req: WorkerRequest = {
        type: 'parse-csv',
        csvText,
        format,
      }
      getWorker().postMessage(req)
    },
    [getWorker],
  )

  const compare = useCallback(
    (
      transactions: SerializedTransaction[],
      year: number,
      country: 'US' | 'DE',
      knownWallets: string[] = [],
    ) => {
      setState({
        ...INITIAL_STATE,
        status: 'comparing',
      })
      const req: WorkerRequest = {
        type: 'compare',
        transactions,
        year,
        country,
        knownWallets,
      }
      getWorker().postMessage(req)
    },
    [getWorker],
  )

  const reset = useCallback(() => {
    setState(INITIAL_STATE)
  }, [])

  const terminate = useCallback(() => {
    workerRef.current?.terminate()
    workerRef.current = null
    setState(INITIAL_STATE)
  }, [])

  // Clean up on unmount
  useEffect(() => {
    return () => {
      workerRef.current?.terminate()
      workerRef.current = null
    }
  }, [])

  return {
    ...state,
    calculate,
    categorize,
    parseCSV,
    compare,
    reset,
    terminate,
  }
}
