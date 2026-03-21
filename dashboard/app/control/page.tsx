"use client";

import { useState, useEffect, useCallback } from "react";
import { signIn, signOut, useSession } from "next-auth/react";
import { Navbar } from "@/components/navbar";
import { LogOut, AlertTriangle, Lock } from "lucide-react";

interface ConfigRow {
  key: string;
  value: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Momentum strategy defaults
// ---------------------------------------------------------------------------

const DEFAULTS: Record<string, string> = {
  strategy_momentum_enabled: "false",
  momentum_price_a_seconds: "45",
  momentum_price_b_seconds: "60",
  momentum_price_open_seconds: "0",
  momentum_entry_after_seconds: "65",
  momentum_entry_until_seconds: "90",
  momentum_threshold: "0.10",
  momentum_context_max_delta: "0.1",
  momentum_price_min: "0.50",
  momentum_price_max: "0.75",
  momentum_direction: "up_only",
  momentum_markets: "xrp_sol_only",
  momentum_hours_start: "0",
  momentum_hours_end: "24",
  momentum_bet_pct: "0.02",
  momentum_fallback_shares: "2",
  momentum_stop_loss_enabled: "true",
  momentum_stop_loss_price: "0.35",
};

// ---------------------------------------------------------------------------
// Field definitions
// ---------------------------------------------------------------------------

interface FieldDef {
  key: string;
  label: string;
  type: "number" | "decimal" | "text" | "toggle" | "select";
  options?: { value: string; label: string }[];
  hint?: string;
  subgroup?: string;
  /** When true this field is only visible if its parent toggle is on */
  parentToggle?: string;
  /** Display the raw value as percentage (multiply by 100, append %) */
  displayAsPercent?: boolean;
  min?: number;
  max?: number;
  step?: number;
}

const FIELDS: FieldDef[] = [
  // Signal timing
  { key: "momentum_price_a_seconds", label: "Price sample A", type: "number", subgroup: "Signal Timing", hint: "First snapshot second. Default 45", min: 0, max: 300, step: 1 },
  { key: "momentum_price_b_seconds", label: "Price sample B", type: "number", hint: "Second snapshot. Must be > A. Default 60", min: 0, max: 300, step: 1 },
  { key: "momentum_price_open_seconds", label: "Open price sample", type: "number", hint: "Second used for context filter baseline. Default 0", min: 0, max: 300, step: 1 },
  { key: "momentum_entry_after_seconds", label: "Enter after", type: "number", hint: "Don't fire before this second. Default 65", min: 0, max: 300, step: 1 },
  { key: "momentum_entry_until_seconds", label: "Enter until", type: "number", hint: "Stop firing after this second. Default 90", min: 0, max: 300, step: 1 },
  // Signal strength
  { key: "momentum_threshold", label: "Momentum threshold", type: "decimal", subgroup: "Signal Strength", hint: "Min price delta between A and B to trigger. Default 0.10", min: 0.001, max: 1, step: 0.001 },
  { key: "momentum_context_max_delta", label: "Context filter delta", type: "text", hint: 'Max allowed gap between open price and price_b in opposite direction. Use "off" to disable. Default 0.1' },
  // Entry price filter
  { key: "momentum_price_min", label: "Min entry price", type: "decimal", subgroup: "Entry Price Filter", hint: "Don't enter below this. Default 0.50", min: 0.01, max: 0.99, step: 0.01 },
  { key: "momentum_price_max", label: "Max entry price", type: "decimal", hint: "Don't enter above this. Default 0.75", min: 0.01, max: 0.99, step: 0.01 },
  // Market and hour filter
  { key: "momentum_direction", label: "Direction", type: "select", subgroup: "Market & Hour Filter", options: [
    { value: "up_only", label: "Up signals only" },
    { value: "down_only", label: "Down signals only" },
    { value: "both", label: "Both directions" },
  ] },
  { key: "momentum_markets", label: "Markets", type: "select", options: [
    { value: "xrp_sol_only", label: "XRP and SOL only" },
    { value: "no_btc", label: "All except BTC" },
    { value: "all", label: "All 4 assets" },
  ] },
  { key: "momentum_hours_start", label: "Active from (UTC)", type: "number", hint: "Inclusive. Default 0", min: 0, max: 23, step: 1 },
  { key: "momentum_hours_end", label: "Active until (UTC)", type: "number", hint: "Exclusive. Default 24", min: 1, max: 24, step: 1 },
  // Position sizing
  { key: "momentum_bet_pct", label: "Bet size (% of balance)", type: "decimal", subgroup: "Position Sizing", displayAsPercent: true, hint: "Percentage of current balance per trade. Default 2%", min: 0.001, max: 1, step: 0.001 },
  { key: "momentum_fallback_shares", label: "Fallback shares", type: "number", hint: "Shares to use if balance cannot be fetched. Default 2", min: 1, max: 1000, step: 1 },
  // Stop-loss
  { key: "momentum_stop_loss_enabled", label: "Enable stop-loss", type: "toggle", subgroup: "Stop-Loss", hint: "Default true" },
  { key: "momentum_stop_loss_price", label: "Stop-loss price", type: "decimal", parentToggle: "momentum_stop_loss_enabled", hint: "GTC sell price. Default 0.35", min: 0.01, max: 0.99, step: 0.01 },
];

function formatTimestamp(ts: string) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

// ---------------------------------------------------------------------------
// Toggle switch component
// ---------------------------------------------------------------------------

function ToggleSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-primary" : "bg-zinc-700"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-zinc-950 shadow-lg transition-transform duration-200 ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Saved indicator
// ---------------------------------------------------------------------------

function SavedIndicator({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <span className="text-xs font-medium text-emerald-400 animate-fade-in">
      Saved ✓
    </span>
  );
}

// ---------------------------------------------------------------------------
// Control page
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Login modal (shown when not authenticated)
// ---------------------------------------------------------------------------

function LoginModal() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);

    const result = await signIn("credentials", {
      password,
      redirect: false,
    });

    if (result?.error) {
      setError("Invalid password");
      setBusy(false);
    }
    // on success useSession() will update automatically
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm">
      <div className="w-full max-w-sm mx-4">
        <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/50 backdrop-blur-sm p-8">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
              <Lock className="h-5 w-5 text-primary" />
            </div>
            <h1 className="text-2xl font-bold text-primary">PolyEdge</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Enter password to access control panel
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-zinc-300">
                Password
              </span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter dashboard password"
                className="w-full rounded-lg border border-zinc-800/60 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none transition-colors focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
              />
            </label>

            {error && (
              <p className="text-sm font-medium text-red-400">{error}</p>
            )}

            <button
              type="submit"
              disabled={busy || !password}
              className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-zinc-950 transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Control page
// ---------------------------------------------------------------------------

export default function ControlPage() {
  const { status } = useSession();
  const [config, setConfig] = useState<ConfigRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [savedKeys, setSavedKeys] = useState<Record<string, boolean>>({});
  const [paramValues, setParamValues] = useState<Record<string, string>>({});

  const authenticated = status === "authenticated";

  const fetchConfig = useCallback(async () => {
    if (!authenticated) {
      setLoading(false);
      return;
    }
    try {
      const res = await fetch("/api/bot-config");
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        const vals: Record<string, string> = {};
        data.forEach((row: ConfigRow) => {
          vals[row.key] = row.value;
        });
        setParamValues(vals);
      }
    } finally {
      setLoading(false);
    }
  }, [authenticated]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  function getVal(key: string): string {
    return paramValues[key] ?? DEFAULTS[key] ?? "";
  }

  function getConfigTimestamp(key: string): string {
    const row = config.find((r) => r.key === key);
    return row?.updated_at ?? "";
  }

  async function saveKey(key: string, value: string) {
    const res = await fetch("/api/bot-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    if (res.ok) {
      setSavedKeys((prev) => ({ ...prev, [key]: true }));
      setTimeout(() => {
        setSavedKeys((prev) => ({ ...prev, [key]: false }));
      }, 2000);
      fetchConfig();
    }
  }

  // Show login modal when not authenticated
  if (status === "unauthenticated") {
    return (
      <>
        <Navbar />
        <LoginModal />
      </>
    );
  }

  if (status === "loading" || loading) {
    return (
      <>
        <Navbar />
        <main className="mx-auto max-w-4xl px-4 py-8 md:px-6">
          <p className="text-sm text-muted-foreground">Loading configuration...</p>
        </main>
      </>
    );
  }

  const masterEnabled = getVal("strategy_momentum_enabled") === "true";

  // For the bet-size helper note
  const betPct = parseFloat(getVal("momentum_bet_pct")) || 0.02;

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-4xl px-4 py-6 md:px-6">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-zinc-50">Bot Control</h1>
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="flex items-center gap-2 rounded-lg border border-zinc-800/60 bg-zinc-900/50 px-3 py-1.5 text-sm font-medium text-zinc-400 transition-colors hover:bg-zinc-800/80 hover:text-zinc-200"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>

        {/* Warning banner */}
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-4 py-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-amber-400" />
          <p className="text-sm font-medium text-amber-300">
            Changes take effect within 5 seconds — the bot reads configuration on every loop.
          </p>
        </div>

        {/* Momentum Strategy */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-100 mb-4">
            Momentum Strategy
          </h2>

          {/* Master toggle */}
          <div className="mb-4 flex items-center justify-between rounded-lg border border-zinc-800/60 bg-zinc-900/50 px-4 py-3">
            <div className="flex items-center gap-3">
              <ToggleSwitch
                checked={masterEnabled}
                onChange={(v) => {
                  const val = v ? "true" : "false";
                  setParamValues((prev) => ({ ...prev, strategy_momentum_enabled: val }));
                  saveKey("strategy_momentum_enabled", val);
                }}
              />
              <span className="text-sm font-medium text-zinc-200">
                Momentum strategy enabled
              </span>
              <SavedIndicator show={!!savedKeys["strategy_momentum_enabled"]} />
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  masterEnabled
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-zinc-800 text-zinc-500"
                }`}
              >
                {masterEnabled ? "Enabled" : "Disabled"}
              </span>
              {getConfigTimestamp("strategy_momentum_enabled") && (
                <span className="text-xs text-muted-foreground">
                  Updated {formatTimestamp(getConfigTimestamp("strategy_momentum_enabled"))}
                </span>
              )}
            </div>
          </div>

          {/* Fields */}
          <div className="space-y-2">
            {FIELDS.map((field) => {
              // Hide child params when parent toggle is off
              if (field.parentToggle) {
                const parentVal = getVal(field.parentToggle);
                if (parentVal !== "true") return null;
              }

              const dbKey = field.key;
              const ts = getConfigTimestamp(dbKey);
              const currentValue = getVal(dbKey);

              // Subgroup divider
              const subgroupEl = field.subgroup ? (
                <div className="flex items-center gap-3 pt-3 pb-1">
                  <div className="h-px flex-1 bg-zinc-800/60" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                    {field.subgroup}
                  </span>
                  <div className="h-px flex-1 bg-zinc-800/60" />
                </div>
              ) : null;

              if (field.type === "toggle") {
                const checked = currentValue === "true";
                return (
                  <div key={dbKey}>
                    {subgroupEl}
                    <div className="flex items-center gap-3 rounded-lg border border-zinc-800/60 bg-zinc-900/50 px-4 py-3">
                      <div className="min-w-[180px]">
                        <label className="text-sm text-zinc-300">{field.label}</label>
                        {field.hint && <p className="text-xs text-muted-foreground mt-0.5">{field.hint}</p>}
                      </div>
                      <div className="flex flex-1 items-center gap-2">
                        <ToggleSwitch
                          checked={checked}
                          onChange={(v) => {
                            const val = v ? "true" : "false";
                            setParamValues((prev) => ({ ...prev, [dbKey]: val }));
                            saveKey(dbKey, val);
                          }}
                        />
                        <span className={`text-xs font-medium ${checked ? "text-emerald-400" : "text-zinc-500"}`}>
                          {checked ? "On" : "Off"}
                        </span>
                        <SavedIndicator show={!!savedKeys[dbKey]} />
                      </div>
                      {ts && (
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          Updated {formatTimestamp(ts)}
                        </span>
                      )}
                    </div>
                    {/* Stop-loss warning */}
                    {dbKey === "momentum_stop_loss_enabled" && checked && (
                      <div className="mt-1 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-4 py-2">
                        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
                        <p className="text-xs font-medium text-amber-300">
                          Stop-loss only activates when trade cost &ge; $5.00. At low balance or low entry price, stop-loss may be skipped automatically.
                        </p>
                      </div>
                    )}
                  </div>
                );
              }

              if (field.type === "select") {
                return (
                  <div key={dbKey}>
                    {subgroupEl}
                    <div className="flex items-center gap-3 rounded-lg border border-zinc-800/60 bg-zinc-900/50 px-4 py-3">
                      <div className="min-w-[180px]">
                        <label htmlFor={dbKey} className="text-sm text-zinc-300">{field.label}</label>
                        {field.hint && <p className="text-xs text-muted-foreground mt-0.5">{field.hint}</p>}
                      </div>
                      <div className="flex flex-1 items-center gap-2">
                        <select
                          id={dbKey}
                          value={currentValue}
                          onChange={(e) =>
                            setParamValues((prev) => ({ ...prev, [dbKey]: e.target.value }))
                          }
                          className="w-48 rounded-lg border border-zinc-800/60 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
                        >
                          {field.options?.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => saveKey(dbKey, paramValues[dbKey] ?? DEFAULTS[dbKey] ?? "")}
                          className="rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
                        >
                          Save
                        </button>
                        <SavedIndicator show={!!savedKeys[dbKey]} />
                      </div>
                      {ts && (
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          Updated {formatTimestamp(ts)}
                        </span>
                      )}
                    </div>
                  </div>
                );
              }

              // text input (for context_max_delta which accepts "off")
              if (field.type === "text") {
                return (
                  <div key={dbKey}>
                    {subgroupEl}
                    <div className="flex items-center gap-3 rounded-lg border border-zinc-800/60 bg-zinc-900/50 px-4 py-3">
                      <div className="min-w-[180px]">
                        <label htmlFor={dbKey} className="text-sm text-zinc-300">{field.label}</label>
                        {field.hint && <p className="text-xs text-muted-foreground mt-0.5">{field.hint}</p>}
                      </div>
                      <div className="flex flex-1 items-center gap-2">
                        <input
                          id={dbKey}
                          type="text"
                          value={currentValue}
                          onChange={(e) =>
                            setParamValues((prev) => ({ ...prev, [dbKey]: e.target.value }))
                          }
                          className="w-32 rounded-lg border border-zinc-800/60 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
                        />
                        <button
                          onClick={() => saveKey(dbKey, paramValues[dbKey] ?? DEFAULTS[dbKey] ?? "")}
                          className="rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
                        >
                          Save
                        </button>
                        <SavedIndicator show={!!savedKeys[dbKey]} />
                      </div>
                      {ts && (
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          Updated {formatTimestamp(ts)}
                        </span>
                      )}
                    </div>
                  </div>
                );
              }

              // number / decimal input
              // For displayAsPercent fields, show as percentage in the input
              const isPercent = field.displayAsPercent;
              const displayValue = isPercent
                ? String(Math.round(parseFloat(currentValue) * 10000) / 100)
                : currentValue;

              return (
                <div key={dbKey}>
                  {subgroupEl}
                  <div className="flex items-center gap-3 rounded-lg border border-zinc-800/60 bg-zinc-900/50 px-4 py-3">
                    <div className="min-w-[180px]">
                      <label htmlFor={dbKey} className="text-sm text-zinc-300">{field.label}</label>
                      {field.hint && <p className="text-xs text-muted-foreground mt-0.5">{field.hint}</p>}
                    </div>
                    <div className="flex flex-1 items-center gap-2">
                      <div className="relative">
                        <input
                          id={dbKey}
                          type="number"
                          min={isPercent ? 0.1 : field.min}
                          max={isPercent ? 100 : field.max}
                          step={isPercent ? 0.1 : field.step}
                          value={displayValue}
                          onChange={(e) => {
                            if (isPercent) {
                              const raw = parseFloat(e.target.value) / 100;
                              setParamValues((prev) => ({ ...prev, [dbKey]: String(raw) }));
                            } else {
                              setParamValues((prev) => ({ ...prev, [dbKey]: e.target.value }));
                            }
                          }}
                          className="w-32 rounded-lg border border-zinc-800/60 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
                        />
                        {isPercent && (
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-zinc-500 pointer-events-none">%</span>
                        )}
                      </div>
                      <button
                        onClick={() => saveKey(dbKey, paramValues[dbKey] ?? DEFAULTS[dbKey] ?? "")}
                        className="rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
                      >
                        Save
                      </button>
                      <SavedIndicator show={!!savedKeys[dbKey]} />
                    </div>
                    {ts && (
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        Updated {formatTimestamp(ts)}
                      </span>
                    )}
                  </div>
                  {/* Bet size helper note */}
                  {dbKey === "momentum_bet_pct" && (
                    <p className="text-xs text-muted-foreground mt-1 ml-1">
                      e.g. at {Math.round(betPct * 100)}% and $500 balance, each trade costs ~$6.20 at 62¢ entry (10 shares)
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </main>
    </>
  );
}
