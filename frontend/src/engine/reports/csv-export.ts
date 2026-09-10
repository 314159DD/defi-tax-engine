/**
 * Generic CSV string builder.
 *
 * Ported from src/reports/csv_export.py - provides a lightweight CSV
 * generation utility that runs entirely client-side (no file I/O).
 *
 * CRITICAL: All monetary values use decimal.js Decimal -- NEVER native number for money.
 */

/**
 * Escape a single CSV field value according to RFC 4180.
 *
 * - Wraps in double-quotes if the value contains commas, quotes, or newlines.
 * - Escapes internal double-quotes by doubling them.
 */
function escapeField(value: string, delimiter: string = ','): string {
  const needsQuoting =
    value.includes(delimiter) ||
    value.includes('"') ||
    value.includes('\n') ||
    value.includes('\r');
  if (needsQuoting) {
    return '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

/**
 * Build a single CSV row from an array of field values.
 */
function buildRow(fields: string[], delimiter: string = ','): string {
  return fields.map((f) => escapeField(f, delimiter)).join(delimiter);
}

/**
 * Build a complete CSV string from a header row and data rows.
 *
 * @param headers - Column header strings
 * @param rows    - Array of arrays, each inner array is one data row
 * @param delimiter - Column delimiter (default: comma)
 * @returns       Complete CSV string with trailing newline
 */
export function buildCsv(
  headers: string[],
  rows: string[][],
  delimiter: string = ',',
): string {
  const lines: string[] = [];
  lines.push(buildRow(headers, delimiter));
  for (const row of rows) {
    lines.push(buildRow(row, delimiter));
  }
  return lines.join('\n') + '\n';
}

/**
 * Build a CSV from an array of objects using specified column keys.
 *
 * @param headers   - Column header strings (displayed in output)
 * @param keys      - Object keys corresponding to each header
 * @param data      - Array of row objects
 * @param delimiter - Column delimiter (default: comma)
 */
export function buildCsvFromObjects<T extends Record<string, unknown>>(
  headers: string[],
  keys: string[],
  data: T[],
  delimiter: string = ',',
): string {
  const rows = data.map((obj) =>
    keys.map((key) => {
      const val = obj[key];
      return val === null || val === undefined ? '' : String(val);
    }),
  );
  return buildCsv(headers, rows, delimiter);
}
