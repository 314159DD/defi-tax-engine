export type CompetitorFeature = {
  defiAccuracy: "yes" | "no" | "partial";
  privacy: "yes" | "no" | "partial";
  chains: string;
  startingPrice: string;
  reports: string;
  cpaTools: "yes" | "no" | "partial";
};

export type CompetitorTier = {
  name: string;
  price: string;
  transactions: string;
};

export type Competitor = {
  slug: string;
  name: string;
  /** Primary market: "us" or "de" */
  market: "us" | "de";
  tagline: string;
  features: CompetitorFeature;
  tiers: CompetitorTier[];
  whySwitch: string[];
};

export const PRODUCT_NAME = "CryptoTax DeFi";

export const OUR_FEATURES: CompetitorFeature = {
  defiAccuracy: "yes",
  privacy: "yes",
  chains: "6 chains (EVM + Solana)",
  startingPrice: "$9.99/mo",
  reports: "Form 8949, TurboTax CSV, Schedule D, JSON",
  cpaTools: "partial",
};

export const OUR_TIERS: CompetitorTier[] = [
  { name: "Free", price: "$0", transactions: "100 txns" },
  { name: "Pro", price: "$9.99/mo", transactions: "5,000 txns" },
  { name: "Unlimited", price: "$29.99/mo", transactions: "Unlimited" },
];

export const COMPETITORS: Record<string, Competitor> = {
  koinly: {
    slug: "koinly",
    name: "Koinly",
    market: "us",
    tagline: "Koinly is popular but struggles with DeFi accuracy and charges per tax year.",
    features: {
      defiAccuracy: "partial",
      privacy: "no",
      chains: "20+ chains",
      startingPrice: "$49/yr (100 txns)",
      reports: "Form 8949, TurboTax, Schedule D",
      cpaTools: "yes",
    },
    tiers: [
      { name: "Newbie", price: "$49/yr", transactions: "100 txns" },
      { name: "Hodler", price: "$99/yr", transactions: "1,000 txns" },
      { name: "Trader", price: "$179/yr", transactions: "3,000 txns" },
      { name: "Oracle", price: "$279/yr", transactions: "10,000 txns" },
    ],
    whySwitch: [
      "Accurate DeFi handling: LP deposits, bridges, and vaults handled correctly without phantom gains.",
      "Privacy-first: Your financial data stays on your device. Koinly uploads everything to their cloud.",
      "Better value: $9.99/mo for 5,000 transactions vs Koinly's $179/yr for 3,000.",
    ],
  },
  cointracker: {
    slug: "cointracker",
    name: "CoinTracker",
    market: "us",
    tagline: "CoinTracker is well-funded but expensive, and DeFi accuracy is limited.",
    features: {
      defiAccuracy: "partial",
      privacy: "no",
      chains: "10+ chains",
      startingPrice: "$59/yr (100 txns)",
      reports: "Form 8949, TurboTax",
      cpaTools: "yes",
    },
    tiers: [
      { name: "Base", price: "$59/yr", transactions: "100 txns" },
      { name: "Prime", price: "$199/yr", transactions: "1,000 txns" },
      { name: "Ultra", price: "$599/yr", transactions: "10,000 txns" },
    ],
    whySwitch: [
      "5x cheaper at mid-tier: $120/yr (Pro annual) for 5,000 txns vs CoinTracker's $199/yr for 1,000.",
      "No cloud data: CoinTracker stores your complete financial history on their servers.",
      "DeFi-native: Built from day one for concentrated liquidity, cross-chain bridges, and yield farming.",
    ],
  },
  coinledger: {
    slug: "coinledger",
    name: "CoinLedger",
    market: "us",
    tagline: "CoinLedger is beginner-friendly but lacks DeFi depth and local compute.",
    features: {
      defiAccuracy: "partial",
      privacy: "no",
      chains: "10+ chains",
      startingPrice: "$49/yr (100 txns)",
      reports: "Form 8949, TurboTax",
      cpaTools: "no",
    },
    tiers: [
      { name: "Hobbyist", price: "$49/yr", transactions: "100 txns" },
      { name: "Investor", price: "$99/yr", transactions: "1,500 txns" },
      { name: "Trader", price: "$199/yr", transactions: "5,000 txns" },
      { name: "Unlimited", price: "$299/yr", transactions: "Unlimited" },
    ],
    whySwitch: [
      "Privacy architecture: CoinLedger processes everything in the cloud. We keep your data local.",
      "Better LP/bridge handling: No phantom gains on LP deposits. Bridges recognized as transfers.",
      "Monthly billing: Pay $9.99/mo instead of committing to a full year upfront.",
    ],
  },
  cointracking: {
    slug: "cointracking",
    name: "CoinTracking",
    market: "de",
    tagline: "CoinTracking is the German market leader but has a steep learning curve and no local compute.",
    features: {
      defiAccuracy: "partial",
      privacy: "no",
      chains: "20+ chains",
      startingPrice: "€99/yr",
      reports: "Anlage SO, WISO, DATEV",
      cpaTools: "yes",
    },
    tiers: [
      { name: "Free", price: "€0", transactions: "200 txns" },
      { name: "Pro", price: "€99/yr", transactions: "3,500 txns" },
      { name: "Expert", price: "€169/yr", transactions: "20,000 txns" },
      { name: "Unlimited", price: "€329/yr", transactions: "Unlimited" },
    ],
    whySwitch: [
      "Modern UX: No 1-hour onboarding. Clean, intuitive interface designed for 2026.",
      "True local compute: Your wallet addresses and balances never leave your device.",
      "DeFi-native from day one: Concentrated liquidity, bridges, and vault tracking built in.",
    ],
  },
  blockpit: {
    slug: "blockpit",
    name: "Blockpit",
    market: "de",
    tagline: "Blockpit is the Austrian alternative but charges up to 549 EUR for DeFi users.",
    features: {
      defiAccuracy: "partial",
      privacy: "no",
      chains: "15+ chains",
      startingPrice: "€49/yr",
      reports: "Anlage SO, WISO",
      cpaTools: "partial",
    },
    tiers: [
      { name: "Lite", price: "€49/yr", transactions: "250 txns" },
      { name: "Basic", price: "€99/yr", transactions: "1,000 txns" },
      { name: "Advanced", price: "€199/yr", transactions: "5,000 txns" },
      { name: "Unlimited", price: "€549/yr", transactions: "Unlimited" },
    ],
    whySwitch: [
      "Massive savings: Our Unlimited is 179 EUR vs Blockpit's 549 EUR. Same coverage, 67% less.",
      "True local compute: Blockpit processes in the cloud. We calculate everything on your device.",
      "Better DeFi accuracy: Concentrated liquidity and cross-chain bridges handled correctly.",
    ],
  },
};

export const COMPETITOR_SLUGS = Object.keys(COMPETITORS);
