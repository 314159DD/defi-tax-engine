/**
 * Tax citation database -- maps tax treatments to legal references.
 *
 * Every Disposal and IncomeEvent can be tagged with a citation that explains
 * *why* a particular tax treatment was applied. This builds user trust by
 * making the logic transparent and auditable.
 *
 * US citations reference IRS guidance (IRC, Revenue Rulings, Notices).
 * DE citations reference BMF-Schreiben 2025 and EStG paragraphs.
 *
 * Ported from: src/tax/citations.py
 */

// ---------------------------------------------------------------------------
// CitationCode enum
// ---------------------------------------------------------------------------

export enum CitationCode {
  // ── US citations ──────────────────────────────────────────────────────
  US_SHORT_TERM_GAIN = 'US_SHORT_TERM_GAIN',
  US_LONG_TERM_GAIN = 'US_LONG_TERM_GAIN',
  US_STAKING_INCOME = 'US_STAKING_INCOME',
  US_MINING_INCOME = 'US_MINING_INCOME',
  US_AIRDROP_INCOME = 'US_AIRDROP_INCOME',
  US_BRIDGE_TRANSFER = 'US_BRIDGE_TRANSFER',
  US_WASH_SALE_WARNING = 'US_WASH_SALE_WARNING',

  // ── DE citations ──────────────────────────────────────────────────────
  DE_SPEKULATIONSFRIST_TAXABLE = 'DE_SPEKULATIONSFRIST_TAXABLE',
  DE_SPEKULATIONSFRIST_EXEMPT = 'DE_SPEKULATIONSFRIST_EXEMPT',
  DE_FREIGRENZE_EXEMPT = 'DE_FREIGRENZE_EXEMPT',
  DE_FREIGRENZE_EXCEEDED = 'DE_FREIGRENZE_EXCEEDED',
  DE_STAKING_INCOME = 'DE_STAKING_INCOME',
  DE_FIFO_METHOD = 'DE_FIFO_METHOD',
  DE_LP_DEPOSIT_GRAY_AREA = 'DE_LP_DEPOSIT_GRAY_AREA',
  DE_BRIDGE_TRANSFER = 'DE_BRIDGE_TRANSFER',
}

// ---------------------------------------------------------------------------
// Citation data type
// ---------------------------------------------------------------------------

export interface CitationData {
  code: string;
  text: string;
  source: string;
  isGrayArea: boolean;
}

// ---------------------------------------------------------------------------
// Citations map
// ---------------------------------------------------------------------------

export const CITATIONS: Record<CitationCode, CitationData> = {
  // ── US ─────────────────────────────────────────────────────────────────
  [CitationCode.US_SHORT_TERM_GAIN]: {
    code: 'US_SHORT_TERM_GAIN',
    text: 'IRC \u00a71222(1) \u2014 Short-term capital gain on property held one year or less.',
    source: 'Internal Revenue Code \u00a71222(1)',
    isGrayArea: false,
  },
  [CitationCode.US_LONG_TERM_GAIN]: {
    code: 'US_LONG_TERM_GAIN',
    text: 'IRC \u00a71222(3) \u2014 Long-term capital gain on property held more than one year.',
    source: 'Internal Revenue Code \u00a71222(3)',
    isGrayArea: false,
  },
  [CitationCode.US_STAKING_INCOME]: {
    code: 'US_STAKING_INCOME',
    text:
      'Rev. Rul. 2023-14 \u2014 Staking rewards are gross income at fair market ' +
      'value upon receipt for cash-method taxpayers.',
    source: 'Revenue Ruling 2023-14',
    isGrayArea: false,
  },
  [CitationCode.US_MINING_INCOME]: {
    code: 'US_MINING_INCOME',
    text:
      'Notice 2014-21, Q&A 8 \u2014 Mining rewards constitute gross income ' +
      'at fair market value on the date of receipt.',
    source: 'IRS Notice 2014-21, Q-8',
    isGrayArea: false,
  },
  [CitationCode.US_AIRDROP_INCOME]: {
    code: 'US_AIRDROP_INCOME',
    text:
      'Rev. Rul. 2019-24 \u2014 Airdrop of cryptocurrency constitutes gross ' +
      'income at fair market value on date of receipt.',
    source: 'Revenue Ruling 2019-24',
    isGrayArea: false,
  },
  [CitationCode.US_BRIDGE_TRANSFER]: {
    code: 'US_BRIDGE_TRANSFER',
    text:
      'Non-taxable \u2014 Bridge transfer is a movement of the same asset between ' +
      'chains by the same taxpayer. No change in economic interest; cost basis ' +
      'carries over.',
    source: 'General tax principles (same taxpayer, same economic interest)',
    isGrayArea: false,
  },
  [CitationCode.US_WASH_SALE_WARNING]: {
    code: 'US_WASH_SALE_WARNING',
    text:
      'IRC \u00a71091 \u2014 Wash sale rules may apply. Note: the IRS has not ' +
      'formally extended wash sale rules to cryptocurrency as of 2025. ' +
      'Proposed legislation may change this.',
    source: 'Internal Revenue Code \u00a71091 (applicability to crypto uncertain)',
    isGrayArea: true,
  },

  // ── DE ─────────────────────────────────────────────────────────────────
  [CitationCode.DE_SPEKULATIONSFRIST_TAXABLE]: {
    code: 'DE_SPEKULATIONSFRIST_TAXABLE',
    text:
      '\u00a723 Abs. 1 Satz 1 Nr. 2 EStG \u2014 ' +
      'Ver\u00e4u\u00dferung innerhalb der Spekulationsfrist von einem Jahr. ' +
      'Der Gewinn ist als privates Ver\u00e4u\u00dferungsgesch\u00e4ft steuerpflichtig.',
    source: '\u00a723 Abs. 1 Satz 1 Nr. 2 EStG',
    isGrayArea: false,
  },
  [CitationCode.DE_SPEKULATIONSFRIST_EXEMPT]: {
    code: 'DE_SPEKULATIONSFRIST_EXEMPT',
    text:
      '\u00a723 Abs. 1 Satz 1 Nr. 2 EStG \u2014 ' +
      'Steuerfrei nach Ablauf der Spekulationsfrist. ' +
      'Kryptow\u00e4hrungen, die l\u00e4nger als ein Jahr gehalten wurden, ' +
      'sind von der Besteuerung ausgenommen.',
    source: '\u00a723 Abs. 1 Satz 1 Nr. 2 EStG',
    isGrayArea: false,
  },
  [CitationCode.DE_FREIGRENZE_EXEMPT]: {
    code: 'DE_FREIGRENZE_EXEMPT',
    text:
      '\u00a723 Abs. 3 Satz 5 EStG \u2014 Freigrenze von 1.000 EUR. ' +
      'Der Gesamtgewinn aus privaten Ver\u00e4u\u00dferungsgesch\u00e4ften ' +
      'im Kalenderjahr liegt unter der Freigrenze und ist daher steuerfrei.',
    source: '\u00a723 Abs. 3 Satz 5 EStG',
    isGrayArea: false,
  },
  [CitationCode.DE_FREIGRENZE_EXCEEDED]: {
    code: 'DE_FREIGRENZE_EXCEEDED',
    text:
      '\u00a723 Abs. 3 Satz 5 EStG \u2014 Freigrenze \u00fcberschritten. ' +
      'Der Gesamtgewinn aus privaten Ver\u00e4u\u00dferungsgesch\u00e4ften ' +
      'im Kalenderjahr betr\u00e4gt 1.000 EUR oder mehr. ' +
      'S\u00e4mtliche Gewinne sind steuerpflichtig (Freigrenze, kein Freibetrag!).',
    source: '\u00a723 Abs. 3 Satz 5 EStG',
    isGrayArea: false,
  },
  [CitationCode.DE_STAKING_INCOME]: {
    code: 'DE_STAKING_INCOME',
    text:
      '\u00a722 Nr. 3 EStG \u2014 Sonstige Eink\u00fcnfte. ' +
      'Staking-Ertr\u00e4ge sind als sonstige Eink\u00fcnfte zum ' +
      'Zeitpunkt des Zuflusses mit dem gemeinen Wert zu versteuern ' +
      '(vgl. BMF-Schreiben 06.03.2025, Rn. 56).',
    source: '\u00a722 Nr. 3 EStG; BMF-Schreiben 06.03.2025, Rn. 56',
    isGrayArea: false,
  },
  [CitationCode.DE_FIFO_METHOD]: {
    code: 'DE_FIFO_METHOD',
    text:
      'BMF-Schreiben 06.03.2025, Rn. 45 \u2014 ' +
      'FIFO (First In, First Out) als Verbrauchsreihenfolge f\u00fcr ' +
      'die Bestimmung der Anschaffungskosten bei Ver\u00e4u\u00dferung ' +
      'von Kryptow\u00e4hrungen.',
    source: 'BMF-Schreiben 06.03.2025, Rn. 45',
    isGrayArea: false,
  },
  [CitationCode.DE_LP_DEPOSIT_GRAY_AREA]: {
    code: 'DE_LP_DEPOSIT_GRAY_AREA',
    text:
      'BMF-Schreiben 06.03.2025, Rn. 68 \u2014 ' +
      'Tauschvorgang bei Liquidit\u00e4tspool-Einlage. ' +
      'Die Einlage in einen Liquidit\u00e4tspool wird als Tausch behandelt ' +
      '(strittig). Konservative Behandlung angewandt.',
    source: 'BMF-Schreiben 06.03.2025, Rn. 68',
    isGrayArea: true,
  },
  [CitationCode.DE_BRIDGE_TRANSFER]: {
    code: 'DE_BRIDGE_TRANSFER',
    text:
      'Kein steuerbarer Vorgang \u2014 Bridge-Transfer zwischen Chains ' +
      'durch denselben Steuerpflichtigen. Die Anschaffungskosten werden ' +
      'fortgef\u00fchrt.',
    source: 'Allgemeine Grunds\u00e4tze (gleicher Steuerpflichtiger, gleicher Verm\u00f6genswert)',
    isGrayArea: false,
  },
};

// ---------------------------------------------------------------------------
// Lookup helpers
// ---------------------------------------------------------------------------

/**
 * Retrieve citation data for a given CitationCode.
 *
 * @param code - CitationCode enum value
 * @returns CitationData object
 * @throws Error if the code is not in the database
 */
export function getCitation(code: CitationCode): CitationData {
  const data = CITATIONS[code];
  if (!data) {
    throw new Error(`Unknown citation code: ${code}`);
  }
  return data;
}

/**
 * Return all citations for a given country code.
 *
 * @param countryCode - "US" or "DE" (case-insensitive)
 * @returns Record mapping CitationCode to CitationData for that country
 */
export function getCitationsForCountry(
  countryCode: string,
): Partial<Record<CitationCode, CitationData>> {
  const prefix = countryCode.toUpperCase() + '_';
  const result: Partial<Record<CitationCode, CitationData>> = {};

  for (const [code, data] of Object.entries(CITATIONS)) {
    if (code.startsWith(prefix)) {
      result[code as CitationCode] = data;
    }
  }

  return result;
}
