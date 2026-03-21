import "server-only";

import { createReadStream } from "node:fs";
import { promises as fs } from "node:fs";
import path from "node:path";
import readline from "node:readline";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const OPTIMIZATION_ROOT = path.join(REPO_ROOT, "src", "results", "optimization");
const VALIDATION_ROOT = path.join(REPO_ROOT, "src", "results", "validation");
const STRATEGIES_ROOT = path.join(REPO_ROOT, "src", "shared", "strategies");

const LEGACY_STRATEGY_ROUTES: Record<string, string> = {
  S1: "/strategy",
  S2: "/strategy2",
  S3: "/strategy3",
  S4: "/strategy4",
};

const METRIC_LABELS: Record<string, string> = {
  total_pnl: "Total P&L",
  roi: "ROI",
  win_rate: "Win Rate",
  win_rate_pct: "Win Rate",
  profit_factor: "Profit Factor",
  sharpe_ratio: "Sharpe Ratio",
  sortino_ratio: "Sortino Ratio",
  max_drawdown: "Max Drawdown",
  total_bets: "Trades Tested",
  trades_taken: "Trades Tested",
  expected_value: "Expected Value",
  avg_bet_pnl: "Avg Bet P&L",
  avg_pnl_per_trade: "Avg Trade P&L",
  total_fees: "Fees",
  consistency_score: "Consistency",
  pct_profitable_assets: "Profitable Assets",
  pct_profitable_durations: "Profitable Durations",
  probability_positive_pct: "Positive Bootstrap",
  wins: "Wins",
  losses: "Losses",
};

const SUMMARY_METRIC_PRIORITY = [
  "total_pnl",
  "roi",
  "win_rate_pct",
  "win_rate",
  "profit_factor",
  "sharpe_ratio",
  "max_drawdown",
  "total_bets",
  "trades_taken",
  "consistency_score",
  "pct_profitable_assets",
  "pct_profitable_durations",
  "expected_value",
  "avg_bet_pnl",
];

const KNOWN_PARAMETER_KEYS = new Set([
  "total_bets",
  "wins",
  "losses",
  "win_rate_pct",
  "win_rate",
  "total_pnl",
  "avg_bet_pnl",
  "avg_pnl_per_trade",
  "profit_factor",
  "expected_value",
  "total_entry_fees",
  "total_exit_fees",
  "total_fees",
  "sharpe_ratio",
  "sortino_ratio",
  "max_drawdown",
  "std_dev_pnl",
  "pct_profitable_assets",
  "pct_profitable_durations",
  "consistency_score",
  "q1_pnl",
  "q2_pnl",
  "q3_pnl",
  "q4_pnl",
  "eligible_markets",
  "skipped_markets_missing_features",
  "ranking_score",
  "config_id",
  "source_label",
  "strategy_id",
  "label",
  "rank",
  "stop_loss",
  "take_profit",
  "roi",
]);

type MetricValue = number | string | null;

export type MetricKind = "currency" | "percent" | "ratio" | "number" | "text";
export type MetricTone = "positive" | "negative" | "neutral";

export interface StrategyDisplayMetric {
  key: string;
  label: string;
  rawValue: MetricValue;
  displayValue: string;
  kind: MetricKind;
  tone: MetricTone;
}

export interface StrategyParameterChip {
  key: string;
  label: string;
  value: string;
}

export interface StrategyConfigComparisonPoint {
  rank: number;
  label: string;
  totalPnl: number | null;
  winRate: number | null;
  profitFactor: number | null;
  rankingScore: number | null;
}

export interface StrategySeriesPoint {
  label: string;
  totalPnl: number | null;
  winRate: number | null;
  secondaryValue: number | null;
}

export interface StrategySweepPoint {
  label: string;
  totalPnl: number | null;
  winRate: number | null;
  profitFactor: number | null;
}

export interface StrategyNeighborPoint {
  parameter: string;
  direction: string;
  candidateValue: string;
  neighborValue: string;
  deltaTotalPnl: number | null;
  deltaProfitFactor: number | null;
  deltaSharpeRatio: number | null;
}

export interface StrategyExitReasonPoint {
  label: string;
  count: number;
  totalPnl: number | null;
  avgBetPnl: number | null;
  winRate: number | null;
}

export interface StrategyBootstrapSummary {
  probabilityPositivePct: number | null;
  p05TotalPnl: number | null;
  p50TotalPnl: number | null;
  p95TotalPnl: number | null;
  meanTotalPnl: number | null;
}

export interface StrategySummary {
  strategyId: string;
  displayName: string;
  description: string | null;
  route: string;
  legacyRoute: string | null;
  statusLabel: string;
  latestSourceLabel: string;
  lastUpdatedAt: string | null;
  totalPnl: number | null;
  roi: number | null;
  winRate: number | null;
  primaryMetric: StrategyDisplayMetric | null;
  summaryMetrics: StrategyDisplayMetric[];
}

export interface StrategyDetail extends StrategySummary {
  sourceSummary: string[];
  parameterChips: StrategyParameterChip[];
  topConfigurations: StrategyConfigComparisonPoint[];
  quarterlyPerformance: StrategySeriesPoint[];
  chronologicalFolds: StrategySeriesPoint[];
  assetBreakdown: StrategySeriesPoint[];
  durationBreakdown: StrategySeriesPoint[];
  dayBreakdown: StrategySeriesPoint[];
  slippageSweep: StrategySweepPoint[];
  entryDelaySweep: StrategySweepPoint[];
  parameterNeighbors: StrategyNeighborPoint[];
  exitReasonBreakdown: StrategyExitReasonPoint[];
  defaultDrift: StrategyParameterChip[];
  bootstrapSummary: StrategyBootstrapSummary | null;
}

type ArtifactFile = {
  path: string;
  mtimeMs: number;
};

type StrategyArtifacts = {
  analysis?: ArtifactFile;
  bestConfigs?: ArtifactFile;
  csv?: ArtifactFile;
  validationJson?: ArtifactFile;
  validationMarkdown?: ArtifactFile;
  optimizationValidation?: ArtifactFile;
};

type ValidationPayload = {
  generated_at?: string;
  candidate?: {
    strategy_id?: string;
    config_id?: string | null;
    label?: string;
    rank?: number | null;
    source_label?: string;
    param_dict?: Record<string, unknown>;
  };
  overall?: {
    base_slippage?: number;
    accelerated?: boolean;
    metrics?: Record<string, unknown>;
    execution_stats?: Record<string, unknown>;
  };
  slippage_sweep?: Array<{
    slippage?: number;
    metrics?: Record<string, unknown>;
  }>;
  entry_delay_sweep?: Array<{
    entry_delay_seconds?: number;
    metrics?: Record<string, unknown>;
  }>;
  chronological_folds?: Array<{
    fold?: number;
    markets?: number;
    start_at?: string;
    end_at?: string;
    metrics?: Record<string, unknown>;
  }>;
  asset_slices?: Array<{
    label?: string;
    markets?: number;
    metrics?: Record<string, unknown>;
  }>;
  duration_slices?: Array<{
    label?: string;
    markets?: number;
    metrics?: Record<string, unknown>;
  }>;
  day_slices?: Array<{
    label?: string;
    markets?: number;
    metrics?: Record<string, unknown>;
  }>;
  exit_reason_breakdown?: Array<{
    exit_reason?: string;
    count?: number;
    total_pnl?: number;
    avg_bet_pnl?: number;
    win_rate_pct?: number;
  }>;
  default_drift?: Array<{
    field?: string;
    default_value?: unknown;
    candidate_value?: unknown;
    kind?: string;
  }>;
  bootstrap?: {
    probability_positive_pct?: number;
    p05_total_pnl?: number;
    p50_total_pnl?: number;
    p95_total_pnl?: number;
    mean_total_pnl?: number;
  };
  parameter_neighbors?: Array<{
    parameter?: string;
    direction?: string;
    candidate_value?: unknown;
    neighbor_value?: unknown;
    delta_total_pnl?: number;
    delta_profit_factor?: number;
    delta_sharpe_ratio?: number;
  }>;
};

type StrategyMetadata = {
  displayName: string;
  description: string | null;
};

type ConfigurationCandidate = {
  rank: number;
  label: string;
  metrics: Record<string, MetricValue>;
  parameters: Record<string, MetricValue>;
};

async function pathExists(targetPath: string) {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

async function walkFiles(rootDir: string): Promise<string[]> {
  if (!(await pathExists(rootDir))) {
    return [];
  }

  const entries = await fs.readdir(rootDir, { withFileTypes: true });
  const files = await Promise.all(
    entries.map(async (entry) => {
      const entryPath = path.join(rootDir, entry.name);
      if (entry.isDirectory()) {
        return walkFiles(entryPath);
      }
      return [entryPath];
    })
  );

  return files.flat();
}

function getStrategyIdFromPath(filePath: string): string | null {
  const basename = path.basename(filePath);
  const filenameMatch = basename.match(/(?:Test_)?optimize_(S\d+)_/i);
  if (filenameMatch?.[1]) {
    return filenameMatch[1].toUpperCase();
  }

  const normalized = filePath.replace(/\\/g, "/");
  const pathMatch = normalized.match(/\/(S\d+)\/(?:run_[^/]+\/)?[^/]+$/i);
  return pathMatch ? pathMatch[1].toUpperCase() : null;
}

async function getArtifactFile(filePath: string): Promise<ArtifactFile> {
  const stats = await fs.stat(filePath);
  return {
    path: filePath,
    mtimeMs: stats.mtimeMs,
  };
}

function setLatestArtifact(
  artifactMap: Map<string, StrategyArtifacts>,
  strategyId: string,
  key: keyof StrategyArtifacts,
  file: ArtifactFile
) {
  const current = artifactMap.get(strategyId) ?? {};
  const existing = current[key];
  if (!existing || file.mtimeMs >= existing.mtimeMs) {
    current[key] = file;
    artifactMap.set(strategyId, current);
  }
}

async function discoverStrategyArtifacts() {
  const artifactMap = new Map<string, StrategyArtifacts>();
  const [optimizationFiles, validationFiles] = await Promise.all([
    walkFiles(OPTIMIZATION_ROOT),
    walkFiles(VALIDATION_ROOT),
  ]);

  const allFiles = [...optimizationFiles, ...validationFiles];

  for (const filePath of allFiles) {
    const strategyId = getStrategyIdFromPath(filePath);
    if (!strategyId) {
      continue;
    }

    const artifactFile = await getArtifactFile(filePath);
    const basename = path.basename(filePath);

    if (/optimize_(S\d+)_Analysis\.md$/i.test(basename)) {
      setLatestArtifact(artifactMap, strategyId, "analysis", artifactFile);
      continue;
    }

    if (/optimize_(S\d+)_Best_Configs\.txt$/i.test(basename)) {
      setLatestArtifact(artifactMap, strategyId, "bestConfigs", artifactFile);
      continue;
    }

    if (/(?:Test_)?optimize_(S\d+)_Results\.csv$/i.test(basename)) {
      setLatestArtifact(artifactMap, strategyId, "csv", artifactFile);
      continue;
    }

    if (/optimize_(S\d+)_Validation\.md$/i.test(basename)) {
      setLatestArtifact(artifactMap, strategyId, "optimizationValidation", artifactFile);
      continue;
    }

    if (/candidate_\d+\.json$/i.test(basename)) {
      setLatestArtifact(artifactMap, strategyId, "validationJson", artifactFile);
      continue;
    }

    if (/candidate_\d+\.md$/i.test(basename)) {
      setLatestArtifact(artifactMap, strategyId, "validationMarkdown", artifactFile);
    }
  }

  return artifactMap;
}

async function readTextIfExists(file: ArtifactFile | undefined) {
  if (!file) {
    return null;
  }

  return fs.readFile(file.path, "utf8");
}

function cleanSentence(text: string) {
  return text.replace(/\s+/g, " ").replace(/\s+([.,:;!?])/g, "$1").trim();
}

function titleCase(value: string) {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function prettifyStrategyName(rawName: string, strategyId: string) {
  const withoutPrefix = rawName.replace(new RegExp(`^${strategyId}_?`, "i"), "");
  return titleCase(withoutPrefix);
}

function extractDocstring(text: string, pattern?: RegExp) {
  if (pattern) {
    const match = pattern.exec(text);
    if (match?.[1]) {
      return cleanSentence(match[1]);
    }
  }

  const genericMatch = text.match(/"""([\s\S]*?)"""/);
  return genericMatch?.[1] ? cleanSentence(genericMatch[1]) : null;
}

async function loadStrategyMetadata(strategyId: string): Promise<StrategyMetadata> {
  const strategyDir = path.join(STRATEGIES_ROOT, strategyId);
  const [configText, strategyText] = await Promise.all([
    fs.readFile(path.join(strategyDir, "config.py"), "utf8").catch(() => null),
    fs.readFile(path.join(strategyDir, "strategy.py"), "utf8").catch(() => null),
  ]);

  const configuredName = configText?.match(/strategy_name\s*=\s*["']([^"']+)["']/)?.[1];
  const displayName = configuredName
    ? prettifyStrategyName(configuredName, strategyId)
    : titleCase(
        (strategyText?.match(new RegExp(`${strategyId}\\s+Strategy:\\s*([^".]+)`, "i"))?.[1] ?? strategyId)
          .replace(/strategy/gi, "")
      );

  const classDocstring = strategyText
    ? extractDocstring(strategyText, /class\s+\w+\(.*?\):\s+"""([\s\S]*?)"""/)
    : null;
  const moduleDocstring = strategyText ? extractDocstring(strategyText) : null;

  return {
    displayName,
    description: classDocstring ?? moduleDocstring,
  };
}

function coerceValue(rawValue: string): MetricValue {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return null;
  }

  if ((trimmed.startsWith("[") && trimmed.endsWith("]")) || (trimmed.startsWith("{") && trimmed.endsWith("}"))) {
    try {
      return JSON.parse(trimmed.replace(/'/g, '"')) as MetricValue;
    } catch {
      return trimmed;
    }
  }

  const asNumber = Number(trimmed);
  if (Number.isFinite(asNumber)) {
    return asNumber;
  }

  return trimmed;
}

function normalizeMetricKey(key: string) {
  return key === "win_rate_pct" ? "win_rate" : key;
}

function toFiniteNumber(value: unknown): number | null {
  const asNumber = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(asNumber) ? asNumber : null;
}

function formatDateLabel(dateLike: string | undefined) {
  if (!dateLike) {
    return "Unknown";
  }

  const date = new Date(dateLike);
  if (Number.isNaN(date.getTime())) {
    return dateLike;
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function formatMetricValue(key: string, rawValue: MetricValue): StrategyDisplayMetric {
  const label = METRIC_LABELS[key] ?? titleCase(key);
  if (rawValue == null) {
    return {
      key,
      label,
      rawValue: null,
      displayValue: "—",
      kind: "text",
      tone: "neutral",
    };
  }

  const asNumber = toFiniteNumber(rawValue);
  if (asNumber == null) {
    return {
      key,
      label,
      rawValue: typeof rawValue === "string" ? rawValue : JSON.stringify(rawValue),
      displayValue: String(rawValue),
      kind: "text",
      tone: "neutral",
    };
  }

  const isPercentKey =
    key === "roi" ||
    key === "win_rate_pct" ||
    key === "win_rate" ||
    key.startsWith("pct_") ||
    key.endsWith("_pct") ||
    key === "probability_positive_pct";

  const percentValue = key === "win_rate" && Math.abs(asNumber) <= 1 ? asNumber * 100 : asNumber;
  const kind: MetricKind = isPercentKey
    ? "percent"
    : ["profit_factor", "sharpe_ratio", "sortino_ratio"].includes(key)
      ? "ratio"
      : [
            "total_pnl",
            "avg_bet_pnl",
            "avg_pnl_per_trade",
            "expected_value",
            "max_drawdown",
            "total_fees",
            "q1_pnl",
            "q2_pnl",
            "q3_pnl",
            "q4_pnl",
            "p05_total_pnl",
            "p50_total_pnl",
            "p95_total_pnl",
            "mean_total_pnl",
          ].includes(key)
        ? "currency"
        : "number";

  const displayValue =
    kind === "currency"
      ? `${asNumber < 0 ? "-" : ""}$${Math.abs(asNumber).toFixed(Math.abs(asNumber) >= 10 ? 2 : 3)}`
      : kind === "percent"
        ? `${percentValue.toFixed(percentValue >= 100 ? 0 : 1)}%`
        : kind === "ratio"
          ? asNumber.toFixed(2)
          : Number.isInteger(asNumber)
            ? asNumber.toLocaleString("en-US")
            : asNumber.toFixed(2);

  let tone: MetricTone = "neutral";
  if (["total_pnl", "avg_bet_pnl", "avg_pnl_per_trade", "expected_value", "roi", "sharpe_ratio", "sortino_ratio"].includes(key)) {
    tone = asNumber > 0 ? "positive" : asNumber < 0 ? "negative" : "neutral";
  } else if (["win_rate_pct", "win_rate", "pct_profitable_assets", "pct_profitable_durations", "probability_positive_pct"].includes(key)) {
    tone = percentValue > 50 ? "positive" : percentValue < 50 ? "negative" : "neutral";
  } else if (key === "profit_factor") {
    tone = asNumber > 1 ? "positive" : asNumber < 1 ? "negative" : "neutral";
  } else if (key === "max_drawdown") {
    tone = asNumber > 0 ? "negative" : "neutral";
  }

  return {
    key,
    label,
    rawValue: asNumber,
    displayValue,
    kind,
    tone,
  };
}

function parseMarkdownMetricTable(markdown: string, headingLabel: string) {
  const lines = markdown.split(/\r?\n/);
  const headingIndex = lines.findIndex((line) => line.trim().toLowerCase().includes(headingLabel.toLowerCase()));
  if (headingIndex < 0) {
    return null;
  }

  const tableIndex = lines.findIndex(
    (line, index) => index > headingIndex && line.includes("| Metric |") && line.includes("| Value |")
  );

  if (tableIndex < 0) {
    return null;
  }

  const metrics: Record<string, MetricValue> = {};
  for (let index = tableIndex + 2; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (!line.startsWith("|")) {
      break;
    }

    const cells = line
      .split("|")
      .map((cell) => cell.trim())
      .filter(Boolean);

    if (cells.length < 2) {
      continue;
    }

    const metricKey = cells[0].replace(/\s+/g, "_").toLowerCase();
    metrics[metricKey] = coerceValue(cells[1]);
  }

  return Object.keys(metrics).length > 0 ? metrics : null;
}

function parseSummaryBullets(markdown: string) {
  const lines = markdown.split(/\r?\n/);
  const summaryIndex = lines.findIndex((line) => line.trim().toLowerCase() === "## summary");
  if (summaryIndex < 0) {
    return [];
  }

  const bullets: string[] = [];
  for (let index = summaryIndex + 1; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (line.startsWith("## ")) {
      break;
    }

    if (line.startsWith("- ")) {
      bullets.push(line.slice(2).trim());
    }
  }

  return bullets;
}

function parseBestConfigs(content: string) {
  const blocks = content
    .split(/\r?\n(?=Rank \d+:)/)
    .map((block) => block.trim())
    .filter((block) => block.startsWith("Rank "));

  const parsed = blocks.map<ConfigurationCandidate | null>((block) => {
    const lines = block.split(/\r?\n/);
    const rank = Number(lines[0].match(/Rank (\d+)/)?.[1] ?? NaN);
    if (!Number.isFinite(rank)) {
      return null;
    }

    const metrics: Record<string, MetricValue> = {};
    const parameters: Record<string, MetricValue> = {};

    for (const line of lines.slice(1)) {
      const entryMatch = line.match(/^\s+([a-z0-9_]+):\s*(.+)$/i);
      if (!entryMatch) {
        continue;
      }

      const key = entryMatch[1];
      const value = coerceValue(entryMatch[2]);
      metrics[key] = value;
      if (!KNOWN_PARAMETER_KEYS.has(key)) {
        parameters[key] = value;
      }
    }

    return {
      rank,
      label: String(metrics.config_id ?? `Rank ${rank}`),
      metrics,
      parameters,
    };
  });

  return parsed.filter((candidate): candidate is ConfigurationCandidate => candidate !== null);
}

function parseCsvLine(line: string) {
  const values: string[] = [];
  let current = "";
  let insideQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (insideQuotes && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        insideQuotes = !insideQuotes;
      }
      continue;
    }

    if (character === "," && !insideQuotes) {
      values.push(current);
      current = "";
      continue;
    }

    current += character;
  }

  values.push(current);
  return values;
}

async function readCsvHead(file: ArtifactFile | undefined, rowLimit = 20) {
  if (!file) {
    return [];
  }

  const rows: Record<string, MetricValue>[] = [];
  const stream = createReadStream(file.path, { encoding: "utf8" });
  const input = readline.createInterface({
    input: stream,
    crlfDelay: Infinity,
  });

  let headers: string[] | null = null;

  for await (const line of input) {
    if (!line.trim()) {
      continue;
    }

    if (!headers) {
      headers = parseCsvLine(line);
      continue;
    }

    const values = parseCsvLine(line);
    const row: Record<string, MetricValue> = {};
    headers.forEach((header, index) => {
      row[header] = coerceValue(values[index] ?? "");
    });
    rows.push(row);

    if (rows.length >= rowLimit) {
      input.close();
      stream.close();
      break;
    }
  }

  return rows;
}

function buildParameterChips(parameters: Record<string, unknown>) {
  return Object.entries(parameters)
    .filter(([, value]) => value != null)
    .slice(0, 12)
    .map(([key, value]) => ({
      key,
      label: titleCase(key),
      value: Array.isArray(value) ? value.join(", ") : String(value),
    }));
}

function metricFromMap(metrics: Record<string, MetricValue> | null | undefined, keys: string[]) {
  if (!metrics) {
    return null;
  }

  for (const key of keys) {
    if (metrics[key] != null) {
      return toFiniteNumber(metrics[key]);
    }
  }

  return null;
}

function selectSummaryMetrics(metricMap: Record<string, MetricValue> | null | undefined) {
  if (!metricMap) {
    return [];
  }

  const selected: StrategyDisplayMetric[] = [];
  const seen = new Set<string>();

  for (const key of SUMMARY_METRIC_PRIORITY) {
    if (metricMap[key] == null) {
      continue;
    }

    const normalizedKey = normalizeMetricKey(key);
    if (seen.has(normalizedKey)) {
      continue;
    }

    selected.push(formatMetricValue(key, metricMap[key]));
    seen.add(normalizedKey);

    if (selected.length >= 5) {
      break;
    }
  }

  return selected;
}

async function buildStrategyDetail(strategyId: string, artifacts: StrategyArtifacts): Promise<StrategyDetail | null> {
  const [metadata, analysisMarkdown, bestConfigsText, validationPayload, csvHead] = await Promise.all([
    loadStrategyMetadata(strategyId),
    readTextIfExists(artifacts.analysis),
    readTextIfExists(artifacts.bestConfigs),
    artifacts.validationJson
      ? fs.readFile(artifacts.validationJson.path, "utf8").then((text) => JSON.parse(text) as ValidationPayload)
      : Promise.resolve<ValidationPayload | null>(null),
    readCsvHead(artifacts.csv),
  ]);

  const analysisMetrics = analysisMarkdown ? parseMarkdownMetricTable(analysisMarkdown, "Best Configuration") : null;
  const bestConfigurations = bestConfigsText ? parseBestConfigs(bestConfigsText) : [];
  const csvTopConfigurations = csvHead.map((row, index) => ({
    rank: index + 1,
    label: String(row.config_id ?? `Rank ${index + 1}`),
    metrics: row,
    parameters: Object.fromEntries(
      Object.entries(row).filter(([key]) => !KNOWN_PARAMETER_KEYS.has(key))
    ),
  }));

  const primaryMetricMap =
    (validationPayload?.overall?.metrics as Record<string, MetricValue> | undefined) ??
    analysisMetrics ??
    bestConfigurations[0]?.metrics ??
    csvTopConfigurations[0]?.metrics ??
    null;

  if (!primaryMetricMap && !artifacts.validationJson && !artifacts.analysis && !artifacts.bestConfigs && !artifacts.csv) {
    return null;
  }

  const latestTimestamps = [
    artifacts.validationJson?.mtimeMs,
    artifacts.validationMarkdown?.mtimeMs,
    artifacts.optimizationValidation?.mtimeMs,
    artifacts.analysis?.mtimeMs,
    artifacts.bestConfigs?.mtimeMs,
    artifacts.csv?.mtimeMs,
  ].filter((value): value is number => value != null);

  const latestMtime = latestTimestamps.length > 0 ? Math.max(...latestTimestamps) : null;
  const latestSourceLabel = artifacts.validationJson ? "Validation" : "Optimization";
  const statusLabel = artifacts.validationJson ? "Validated" : "Optimized";
  const topConfigurationsSource = bestConfigurations.length > 0 ? bestConfigurations : csvTopConfigurations;
  const parameterSource =
    validationPayload?.candidate?.param_dict ??
    topConfigurationsSource[0]?.parameters ??
    {};

  const summaryMetrics = selectSummaryMetrics(primaryMetricMap);

  const quarterlyPerformance = ["q1_pnl", "q2_pnl", "q3_pnl", "q4_pnl"]
    .map((key, index) => ({
      label: `Q${index + 1}`,
      totalPnl: toFiniteNumber(primaryMetricMap?.[key]),
      winRate: null,
      secondaryValue: null,
    }))
    .filter((point) => point.totalPnl != null);

  const chronologicalFolds =
    validationPayload?.chronological_folds?.map((fold) => ({
      label: `Fold ${fold.fold ?? "?"}`,
      totalPnl: metricFromMap(fold.metrics as Record<string, MetricValue>, ["total_pnl"]),
      winRate: metricFromMap(fold.metrics as Record<string, MetricValue>, ["win_rate_pct", "win_rate"]),
      secondaryValue: metricFromMap(fold.metrics as Record<string, MetricValue>, ["profit_factor"]),
    })) ?? [];

  const assetBreakdown =
    validationPayload?.asset_slices?.map((slice) => ({
      label: String(slice.label ?? "Unknown").toUpperCase(),
      totalPnl: metricFromMap(slice.metrics as Record<string, MetricValue>, ["total_pnl"]),
      winRate: metricFromMap(slice.metrics as Record<string, MetricValue>, ["win_rate_pct", "win_rate"]),
      secondaryValue: metricFromMap(slice.metrics as Record<string, MetricValue>, ["profit_factor"]),
    })) ?? [];

  const durationBreakdown =
    validationPayload?.duration_slices?.map((slice) => ({
      label: String(slice.label ?? "Unknown").toUpperCase(),
      totalPnl: metricFromMap(slice.metrics as Record<string, MetricValue>, ["total_pnl"]),
      winRate: metricFromMap(slice.metrics as Record<string, MetricValue>, ["win_rate_pct", "win_rate"]),
      secondaryValue: metricFromMap(slice.metrics as Record<string, MetricValue>, ["profit_factor"]),
    })) ?? [];

  const dayBreakdown =
    validationPayload?.day_slices?.map((slice) => ({
      label: formatDateLabel(slice.label),
      totalPnl: metricFromMap(slice.metrics as Record<string, MetricValue>, ["total_pnl"]),
      winRate: metricFromMap(slice.metrics as Record<string, MetricValue>, ["win_rate_pct", "win_rate"]),
      secondaryValue: metricFromMap(slice.metrics as Record<string, MetricValue>, ["profit_factor"]),
    })) ?? [];

  const slippageSweep =
    validationPayload?.slippage_sweep?.map((item) => ({
      label: `${toFiniteNumber(item.slippage)?.toFixed(2) ?? "?"} slip`,
      totalPnl: metricFromMap(item.metrics as Record<string, MetricValue>, ["total_pnl"]),
      winRate: metricFromMap(item.metrics as Record<string, MetricValue>, ["win_rate_pct", "win_rate"]),
      profitFactor: metricFromMap(item.metrics as Record<string, MetricValue>, ["profit_factor"]),
    })) ?? [];

  const entryDelaySweep =
    validationPayload?.entry_delay_sweep?.map((item) => ({
      label: `${item.entry_delay_seconds ?? 0}s`,
      totalPnl: metricFromMap(item.metrics as Record<string, MetricValue>, ["total_pnl"]),
      winRate: metricFromMap(item.metrics as Record<string, MetricValue>, ["win_rate_pct", "win_rate"]),
      profitFactor: metricFromMap(item.metrics as Record<string, MetricValue>, ["profit_factor"]),
    })) ?? [];

  const parameterNeighbors =
    validationPayload?.parameter_neighbors?.map((neighbor) => ({
      parameter: titleCase(String(neighbor.parameter ?? "parameter")),
      direction: String(neighbor.direction ?? ""),
      candidateValue: Array.isArray(neighbor.candidate_value)
        ? neighbor.candidate_value.join(", ")
        : String(neighbor.candidate_value ?? "—"),
      neighborValue: Array.isArray(neighbor.neighbor_value)
        ? neighbor.neighbor_value.join(", ")
        : String(neighbor.neighbor_value ?? "—"),
      deltaTotalPnl: toFiniteNumber(neighbor.delta_total_pnl),
      deltaProfitFactor: toFiniteNumber(neighbor.delta_profit_factor),
      deltaSharpeRatio: toFiniteNumber(neighbor.delta_sharpe_ratio),
    })) ?? [];

  const exitReasonBreakdown =
    validationPayload?.exit_reason_breakdown?.map((exitReason) => ({
      label: titleCase(String(exitReason.exit_reason ?? "Unknown")),
      count: toFiniteNumber(exitReason.count) ?? 0,
      totalPnl: toFiniteNumber(exitReason.total_pnl),
      avgBetPnl: toFiniteNumber(exitReason.avg_bet_pnl),
      winRate: toFiniteNumber(exitReason.win_rate_pct),
    })) ?? [];

  const topConfigurations = topConfigurationsSource.slice(0, 8).map((candidate) => ({
    rank: candidate.rank,
    label: `#${candidate.rank}`,
    totalPnl: metricFromMap(candidate.metrics, ["total_pnl"]),
    winRate: metricFromMap(candidate.metrics, ["win_rate_pct", "win_rate"]),
    profitFactor: metricFromMap(candidate.metrics, ["profit_factor"]),
    rankingScore: metricFromMap(candidate.metrics, ["ranking_score"]),
  }));

  const sourceSummary = [
    ...parseSummaryBullets(analysisMarkdown ?? ""),
    artifacts.validationJson ? "Includes latest validation candidate JSON." : "Using latest optimization artifacts.",
  ];

  const bootstrapSummary = validationPayload?.bootstrap
    ? {
        probabilityPositivePct: toFiniteNumber(validationPayload.bootstrap.probability_positive_pct),
        p05TotalPnl: toFiniteNumber(validationPayload.bootstrap.p05_total_pnl),
        p50TotalPnl: toFiniteNumber(validationPayload.bootstrap.p50_total_pnl),
        p95TotalPnl: toFiniteNumber(validationPayload.bootstrap.p95_total_pnl),
        meanTotalPnl: toFiniteNumber(validationPayload.bootstrap.mean_total_pnl),
      }
    : null;

  return {
    strategyId,
    displayName: metadata.displayName,
    description: metadata.description,
    route: `/strategies/${strategyId}`,
    legacyRoute: LEGACY_STRATEGY_ROUTES[strategyId] ?? null,
    statusLabel,
    latestSourceLabel,
    lastUpdatedAt:
      validationPayload?.generated_at ??
      (latestMtime ? new Date(latestMtime).toISOString() : null),
    totalPnl: metricFromMap(primaryMetricMap, ["total_pnl"]),
    roi: metricFromMap(primaryMetricMap, ["roi"]),
    winRate: metricFromMap(primaryMetricMap, ["win_rate_pct", "win_rate"]),
    primaryMetric: summaryMetrics[0] ?? null,
    summaryMetrics,
    sourceSummary,
    parameterChips: buildParameterChips(parameterSource),
    topConfigurations,
    quarterlyPerformance,
    chronologicalFolds,
    assetBreakdown,
    durationBreakdown,
    dayBreakdown,
    slippageSweep,
    entryDelaySweep,
    parameterNeighbors,
    exitReasonBreakdown,
    defaultDrift:
      validationPayload?.default_drift?.map((item) => ({
        key: String(item.field ?? "field"),
        label: titleCase(String(item.field ?? "field")),
        value: `${String(item.default_value ?? "—")} -> ${String(item.candidate_value ?? "—")}`,
      })) ?? [],
    bootstrapSummary,
  };
}

function compareStrategyIds(left: string, right: string) {
  const leftNumber = Number(left.replace(/\D/g, ""));
  const rightNumber = Number(right.replace(/\D/g, ""));
  return leftNumber - rightNumber;
}

export async function getAllStrategyDetails() {
  const artifacts = await discoverStrategyArtifacts();
  const strategyIds = [...artifacts.keys()].sort(compareStrategyIds);
  const details = await Promise.all(strategyIds.map((strategyId) => buildStrategyDetail(strategyId, artifacts.get(strategyId)!)));

  return details.filter((detail): detail is StrategyDetail => detail !== null);
}

export async function getStrategySummaries() {
  const details = await getAllStrategyDetails();
  return details.map<StrategySummary>((detail) => ({
    strategyId: detail.strategyId,
    displayName: detail.displayName,
    description: detail.description,
    route: detail.route,
    legacyRoute: detail.legacyRoute,
    statusLabel: detail.statusLabel,
    latestSourceLabel: detail.latestSourceLabel,
    lastUpdatedAt: detail.lastUpdatedAt,
    totalPnl: detail.totalPnl,
    roi: detail.roi,
    winRate: detail.winRate,
    primaryMetric: detail.primaryMetric,
    summaryMetrics: detail.summaryMetrics,
  }));
}

export async function getStrategyDetail(strategyId: string) {
  const normalizedId = strategyId.toUpperCase();
  const details = await getAllStrategyDetails();
  return details.find((detail) => detail.strategyId === normalizedId) ?? null;
}
