"""Order execution — places trades on Polymarket based on strategy signals."""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timezone

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

from trading import config
from trading import db
from trading.balance import get_usdc_balance
from trading.constants import EXECUTION_CONFIG
from trading.strategies import Signal
from trading.utils import debug_log, log, strategy_log_tag

# ── Daily net-loss tracking (resets at midnight UTC) ─────────────────────
_daily_net_loss: float = 0.0
_daily_date: str = ""

MIN_DOLLAR_SIZE = config.MIN_LIVE_BET_SIZE_USD

# ── Token ID cache (fetched from CLOB API, cached for session) ──────────
_token_cache: dict[str, tuple[str, str]] = {}  # market_id (condition ID) -> (up_token_id, down_token_id)


# ── Hybrid execution tracking ────────────────────────────────────────

class ExecutionStage:
    IDEAL_LIMIT = "stage_1_ideal"
    RELAXED_LIMIT = "stage_2_relaxed"
    MARKET_FOK = "stage_3_market"
    FAILED = "failed"

_STAGE_LABELS = {
    ExecutionStage.IDEAL_LIMIT: "Stage 1 (Ideal Limit)",
    ExecutionStage.RELAXED_LIMIT: f"Stage 2 (Relaxed +{EXECUTION_CONFIG['stage_2_offset']*100:.0f}¢)",
    ExecutionStage.MARKET_FOK: f"Stage 3 (FOK +{EXECUTION_CONFIG['stage_3_offset']*100:.0f}¢)",
}


class ExecutionMetrics:
    """Track hybrid execution fill rates and slippage across the session."""

    def __init__(self):
        self.total = 0
        self.filled = 0
        self.stage_1_fills = 0
        self.stage_2_fills = 0
        self.stage_3_fills = 0
        self.failed = 0
        self.total_slippage = 0.0
        self.total_time = 0.0

    def record(self, stage: str, filled: bool, slippage: float = 0.0, elapsed: float = 0.0):
        self.total += 1
        self.total_time += elapsed
        if not filled:
            self.failed += 1
            return
        self.filled += 1
        self.total_slippage += slippage
        if stage == ExecutionStage.IDEAL_LIMIT:
            self.stage_1_fills += 1
        elif stage == ExecutionStage.RELAXED_LIMIT:
            self.stage_2_fills += 1
        elif stage == ExecutionStage.MARKET_FOK:
            self.stage_3_fills += 1

    def summary(self) -> str:
        rate = (self.filled / self.total * 100) if self.total > 0 else 0
        avg_slip = (self.total_slippage / self.filled) if self.filled > 0 else 0
        avg_time = (self.total_time / self.total) if self.total > 0 else 0
        return (
            f"Orders: {self.total} | Filled: {self.filled} ({rate:.1f}%) | "
            f"S1: {self.stage_1_fills} S2: {self.stage_2_fills} S3: {self.stage_3_fills} | "
            f"Failed: {self.failed} | Avg Slippage: ${avg_slip:.3f} | Avg Time: {avg_time:.2f}s"
        )

    def reset(self):
        self.__init__()


_exec_metrics = ExecutionMetrics()


class VarianceMetrics:
    """Track execution variance from locked signal parameters."""

    def __init__(self):
        self.total_trades = 0
        self.perfect_executions = 0
        self.acceptable_variance = 0
        self.unacceptable_variance = 0
        self.total_price_variance = 0.0
        self.total_shares_variance = 0
        self.total_signal_age = 0.0

    def add_execution(self, price_variance_pct: float, shares_variance: int, signal_age_seconds: float):
        self.total_trades += 1
        if price_variance_pct == 0 and shares_variance == 0:
            self.perfect_executions += 1
        elif abs(price_variance_pct) < 1.0:
            self.acceptable_variance += 1
        else:
            self.unacceptable_variance += 1
        self.total_price_variance += price_variance_pct
        self.total_shares_variance += shares_variance
        self.total_signal_age += signal_age_seconds

    def summary(self) -> str:
        if self.total_trades == 0:
            return "No variance data yet"
        avg_pv = self.total_price_variance / self.total_trades
        avg_sv = self.total_shares_variance / self.total_trades
        avg_age = self.total_signal_age / self.total_trades
        perfect_pct = self.perfect_executions / self.total_trades * 100
        acceptable_pct = self.acceptable_variance / self.total_trades * 100
        bad_pct = self.unacceptable_variance / self.total_trades * 100
        return (
            f"Trades: {self.total_trades} | Perfect: {perfect_pct:.1f}% | "
            f"Acceptable (<1%): {acceptable_pct:.1f}% | Bad (>1%): {bad_pct:.1f}% | "
            f"Avg price variance: {avg_pv:+.2f}% | Avg shares variance: {avg_sv:+.1f} | "
            f"Avg signal age: {avg_age:.2f}s"
        )

    def reset(self):
        self.__init__()


_variance_metrics = VarianceMetrics()


def get_execution_metrics() -> ExecutionMetrics:
    return _exec_metrics


def get_variance_metrics() -> VarianceMetrics:
    return _variance_metrics


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _reset_daily_if_needed() -> None:
    global _daily_net_loss, _daily_date
    today = _today_utc()
    if _daily_date != today:
        if _daily_date:
            log.info("New UTC day — daily net loss reset (was $%.2f)", _daily_net_loss)
        _daily_date = today
        _daily_net_loss = 0.0


def record_trade_outcome(pnl: float) -> None:
    """Call this when a trade resolves. pnl is positive for win, negative for loss."""
    global _daily_net_loss
    _reset_daily_if_needed()
    if pnl < 0:
        _daily_net_loss += abs(pnl)
    else:
        _daily_net_loss = max(0.0, _daily_net_loss - pnl)


def is_daily_limit_reached(daily_limit: float | None = None) -> bool:
    _reset_daily_if_needed()
    limit = daily_limit if daily_limit is not None else config.DAILY_LOSS_LIMIT
    return _daily_net_loss >= limit


async def sync_daily_net_loss_from_db() -> float:
    """Refresh the in-memory daily loss tracker from resolved DB PnL."""
    global _daily_net_loss
    _reset_daily_if_needed()
    net_pnl = await db.get_daily_resolved_net_pnl()
    _daily_net_loss = max(0.0, -net_pnl)
    return _daily_net_loss


def _clamp_price(price: float) -> float:
    return round(max(0.01, min(0.99, price)), 4)


def _derive_exit_targets(
    *,
    locked_entry_price: float,
    actual_entry_price: float,
    raw_stop_loss: float | None,
    raw_take_profit: float | None,
) -> tuple[float | None, float | None]:
    stop_loss_price = None
    take_profit_price = None

    if raw_stop_loss is not None:
        sl_distance = abs(locked_entry_price - raw_stop_loss)
        if sl_distance > 0:
            stop_loss_price = _clamp_price(actual_entry_price - sl_distance)

    if raw_take_profit is not None:
        tp_distance = abs(raw_take_profit - locked_entry_price)
        if tp_distance > 0:
            take_profit_price = _clamp_price(actual_entry_price + tp_distance)

    return stop_loss_price, take_profit_price


def _validate_exit_targets(
    *,
    actual_entry_price: float,
    stop_loss_price: float | None,
    take_profit_price: float | None,
) -> str | None:
    if stop_loss_price is None:
        return "missing stop-loss target"
    if take_profit_price is None:
        return "missing take-profit target"
    if not (0 < stop_loss_price < actual_entry_price < take_profit_price < 1):
        return (
            f"invalid exit bracket: stop_loss={stop_loss_price:.4f}, "
            f"entry={actual_entry_price:.4f}, take_profit={take_profit_price:.4f}"
        )
    return None


async def _fetch_sellable_shares(
    clob: ClobClient,
    token_id: str,
    *,
    log_prefix: str,
    trade_id: int | None = None,
    initial_delay: float = 0.0,
    attempts: int = 5,
) -> tuple[float, int] | None:
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)

    loop = asyncio.get_event_loop()
    balance = 0
    attempts_used = 0
    for attempt in range(attempts):
        attempts_used = attempt + 1
        try:
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

            balance_resp = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: clob.get_balance_allowance(
                        BalanceAllowanceParams(
                            asset_type=AssetType.CONDITIONAL,
                            token_id=token_id,
                        )
                    ),
                ),
                timeout=5.0,
            )
            balance = int(balance_resp.get("balance", "0")) if isinstance(balance_resp, dict) else 0
            if balance > 0:
                break
            if attempt + 1 == attempts or attempt == 0:
                debug_log.info(
                    "[%s] No settled token balance yet for trade=%s on attempt %d/%d",
                    log_prefix,
                    trade_id if trade_id is not None else "?",
                    attempt + 1,
                    attempts,
                )
            await asyncio.sleep(1.0)
        except Exception as exc:
            log.warning("[%s] Balance check failed attempt %d: %s", log_prefix, attempt + 1, exc)
            await asyncio.sleep(1.0)

    if balance <= 0:
        if trade_id is None:
            log.warning("[%s] Token balance is 0 after %d attempts", log_prefix, attempts)
        else:
            log.warning(
                "[%s] Token balance is 0 after %d attempts for trade %d",
                log_prefix,
                attempts,
                trade_id,
            )
        return None

    actual_shares = balance / 1_000_000
    sellable_shares = math.floor(actual_shares)
    log.info(
        "[%s] Trade %s settled after %d attempt(s) | balance: %.4f shares | sellable: %d",
        log_prefix,
        trade_id if trade_id is not None else "?",
        attempts_used,
        actual_shares,
        sellable_shares,
    )

    if sellable_shares < config.MIN_EXIT_ORDER_SHARES:
        log.warning(
            "[%s] Sellable shares %d below exit minimum %d",
            log_prefix,
            sellable_shares,
            config.MIN_EXIT_ORDER_SHARES,
        )
        return None

    return actual_shares, sellable_shares


def _get_best_price(clob: ClobClient, token_id: str, side: str) -> float | None:
    """Fetch orderbook and return best executable price, or None if no liquidity."""
    try:
        book = clob.get_order_book(token_id)
    except Exception:
        log.warning("Failed to fetch orderbook for %s", token_id)
        return None

    if side == "BUY":
        asks = book.asks if hasattr(book, "asks") else []
        if not asks:
            return None
        return float(min(asks, key=lambda x: float(x.price)).price)
    else:
        bids = book.bids if hasattr(book, "bids") else []
        if not bids:
            return None
        return float(max(bids, key=lambda x: float(x.price)).price)


def _fetch_token_ids(clob: ClobClient, condition_id: str) -> tuple[str, str] | None:
    """Fetch token IDs for a market from the CLOB API. Returns (up_token_id, down_token_id)."""
    if condition_id in _token_cache:
        return _token_cache[condition_id]

    try:
        with config.get_sync_http_client(timeout=5.0) as client:
            resp = client.get(f"{config.CLOB_BASE_URL}/markets/{condition_id}")
            resp.raise_for_status()
            data = resp.json()


        # CLOB API returns a list of two token objects for binary markets
        if isinstance(data, list) and len(data) >= 2:
            tokens = {}
            for t in data:
                outcome = t.get("outcome", "").lower()
                token_id = t.get("token_id", "")
                if outcome in ("yes", "up"):
                    tokens["up"] = token_id
                elif outcome in ("no", "down"):
                    tokens["down"] = token_id
            if "up" in tokens and "down" in tokens:
                result = (tokens["up"], tokens["down"])
                _token_cache[condition_id] = result
                return result

        # Single market object with tokens array
        if isinstance(data, dict):
            tokens_list = data.get("tokens", [])
            if len(tokens_list) >= 2:
                up_id = tokens_list[0].get("token_id", "")
                down_id = tokens_list[1].get("token_id", "")
                if up_id and down_id:
                    result = (up_id, down_id)
                    _token_cache[condition_id] = result
                    return result
            else:
                log.warning("[TOKENS] No tokens in market detail for %s", condition_id[:16])

    except Exception as e:
        log.warning("[TOKENS] Error fetching market %s: %s", condition_id[:16], e)

    return None


async def place_stop_loss_order(clob, trade_id: int, token_id: str, shares: float, stop_loss_price: float) -> None:
    """Place a GTC sell order as a stop-loss for a filled trade."""
    await asyncio.sleep(5)  # wait for token settlement before placing stop-loss

    # Verify token balance before placing sell order
    loop = asyncio.get_event_loop()
    balance = 0
    for attempt in range(5):
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            balance_resp = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: clob.get_balance_allowance(
                    BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
                )),
                timeout=5.0,
            )
            log.info("[STOP-LOSS] Full balance response: %s", balance_resp)
            balance = int(balance_resp.get('balance', '0')) if isinstance(balance_resp, dict) else 0
            log.info("[STOP-LOSS] Token balance check attempt %d: %d", attempt + 1, balance)
            if balance > 0:
                break
            await asyncio.sleep(3)
        except Exception as e:
            log.warning("[STOP-LOSS] Balance check failed attempt %d: %s", attempt + 1, e)
            await asyncio.sleep(3)

    if balance == 0:
        log.warning("[STOP-LOSS] Token balance is 0 after 5 attempts — skipping stop-loss for trade %d", trade_id)
        return

    # Convert raw balance to shares (CTF tokens use 6 decimal places)
    actual_shares = balance / 1_000_000
    sellable_shares = math.floor(actual_shares)

    if sellable_shares <= 0:
        log.warning("[STOP-LOSS] Sellable shares is 0 after balance conversion — skipping")
        return

    log.info("[STOP-LOSS] Actual balance: %.4f shares | selling: %d shares", actual_shares, sellable_shares)

    from py_clob_client.order_builder.constants import SELL
    log.info("[STOP-LOSS] Attempting GTC sell — token: %s | shares: %d | price: %s | trade_id: %d",
             token_id[:16], sellable_shares, stop_loss_price, trade_id)
    try:
        def _place():
            log.info("[STOP-LOSS-DEBUG] token_id type: %s | value: %s | len: %d", type(token_id), token_id, len(str(token_id)))
            sell_args = OrderArgs(token_id=token_id, price=round(stop_loss_price, 2), size=float(sellable_shares), side=SELL)
            log.info("[STOP-LOSS-DEBUG] OrderArgs token_id: %s | len: %d", sell_args.token_id, len(str(sell_args.token_id)))
            signed = clob.create_order(sell_args)
            return clob.post_order(signed, OrderType.GTC)

        resp = await asyncio.wait_for(
            loop.run_in_executor(None, _place),
            timeout=10.0,
        )

        order_id = resp.get('orderID') or resp.get('id') if isinstance(resp, dict) else None
        if order_id:
            await db.update_stop_loss_order(trade_id, order_id, stop_loss_price)
            log.info("[STOP-LOSS] GTC order placed for trade %d @ %.2f | order: %s", trade_id, stop_loss_price, order_id[:16])
        else:
            log.warning("[STOP-LOSS] No order ID returned for trade %d — no stop-loss active", trade_id)

    except asyncio.TimeoutError:
        log.error("[STOP-LOSS] Timeout placing stop-loss for trade %d — continuing without stop-loss", trade_id)
    except Exception as e:
        log.error("[STOP-LOSS] Full error for trade %d: %s: %s", trade_id, type(e).__name__, e)
        log.error("[STOP-LOSS] Failed order args — token: %s | size: %s | price: %s | side: SELL",
                  token_id[:16], shares, stop_loss_price)


async def cancel_stop_loss_order(clob, trade_id: int, stop_loss_order_id: str) -> None:
    """Cancel an existing GTC stop-loss order."""
    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: clob.cancel(stop_loss_order_id)),
            timeout=10.0,
        )
        await db.mark_stop_loss_cancelled(trade_id)
        log.info("[STOP-LOSS] Cancelled GTC order %s for trade %d", stop_loss_order_id[:16], trade_id)
    except asyncio.TimeoutError:
        log.error("[STOP-LOSS] Timeout cancelling stop-loss %s", stop_loss_order_id[:16])
    except Exception as e:
        log.warning("[STOP-LOSS] Could not cancel stop-loss %s: %s", stop_loss_order_id[:16], e)


async def place_take_profit_order(clob, trade_id: int, token_id: str, shares: float, take_profit_price: float) -> None:
    """Place a GTC sell order as a take-profit for a filled trade."""
    await asyncio.sleep(5)  # wait for token settlement before placing take-profit

    loop = asyncio.get_event_loop()
    balance = 0
    for attempt in range(5):
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            balance_resp = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: clob.get_balance_allowance(
                    BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
                )),
                timeout=5.0,
            )
            log.info("[TAKE-PROFIT] Full balance response: %s", balance_resp)
            balance = int(balance_resp.get('balance', '0')) if isinstance(balance_resp, dict) else 0
            log.info("[TAKE-PROFIT] Token balance check attempt %d: %d", attempt + 1, balance)
            if balance > 0:
                break
            await asyncio.sleep(3)
        except Exception as e:
            log.warning("[TAKE-PROFIT] Balance check failed attempt %d: %s", attempt + 1, e)
            await asyncio.sleep(3)

    if balance == 0:
        log.warning("[TAKE-PROFIT] Token balance is 0 after 5 attempts - skipping take-profit for trade %d", trade_id)
        return

    actual_shares = balance / 1_000_000
    sellable_shares = math.floor(actual_shares)

    if sellable_shares <= 0:
        log.warning("[TAKE-PROFIT] Sellable shares is 0 after balance conversion - skipping")
        return

    log.info("[TAKE-PROFIT] Actual balance: %.4f shares | selling: %d shares", actual_shares, sellable_shares)

    from py_clob_client.order_builder.constants import SELL
    log.info("[TAKE-PROFIT] Attempting GTC sell - token: %s | shares: %d | price: %s | trade_id: %d",
             token_id[:16], sellable_shares, take_profit_price, trade_id)
    try:
        def _place():
            log.info("[TAKE-PROFIT-DEBUG] token_id type: %s | value: %s | len: %d", type(token_id), token_id, len(str(token_id)))
            sell_args = OrderArgs(token_id=token_id, price=round(take_profit_price, 2), size=float(sellable_shares), side=SELL)
            log.info("[TAKE-PROFIT-DEBUG] OrderArgs token_id: %s | len: %d", sell_args.token_id, len(str(sell_args.token_id)))
            signed = clob.create_order(sell_args)
            return clob.post_order(signed, OrderType.GTC)

        resp = await asyncio.wait_for(
            loop.run_in_executor(None, _place),
            timeout=10.0,
        )

        order_id = resp.get('orderID') or resp.get('id') if isinstance(resp, dict) else None
        if order_id:
            await db.update_take_profit_order(trade_id, order_id, take_profit_price)
            log.info("[TAKE-PROFIT] GTC order placed for trade %d @ %.2f | order: %s", trade_id, take_profit_price, order_id[:16])
        else:
            log.warning("[TAKE-PROFIT] No order ID returned for trade %d - no take-profit active", trade_id)

    except asyncio.TimeoutError:
        log.error("[TAKE-PROFIT] Timeout placing take-profit for trade %d - continuing without take-profit", trade_id)
    except Exception as e:
        log.error("[TAKE-PROFIT] Full error for trade %d: %s: %s", trade_id, type(e).__name__, e)
        log.error("[TAKE-PROFIT] Failed order args - token: %s | size: %s | price: %s | side: SELL",
                  token_id[:16], shares, take_profit_price)


async def cancel_take_profit_order(clob, trade_id: int, take_profit_order_id: str) -> None:
    """Cancel an existing GTC take-profit order."""
    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: clob.cancel(take_profit_order_id)),
            timeout=10.0,
        )
        await db.mark_take_profit_cancelled(trade_id)
        log.info("[TAKE-PROFIT] Cancelled GTC order %s for trade %d", take_profit_order_id[:16], trade_id)
    except asyncio.TimeoutError:
        log.error("[TAKE-PROFIT] Timeout cancelling take-profit %s", take_profit_order_id[:16])
    except Exception as e:
        log.warning("[TAKE-PROFIT] Could not cancel take-profit %s: %s", take_profit_order_id[:16], e)


async def place_stop_loss_order(
    clob,
    trade_id: int,
    token_id: str,
    shares: float,
    stop_loss_price: float,
    *,
    initial_delay: float = 5.0,
) -> str | None:
    """Place a protected stop-loss sell order after settlement."""
    share_info = await _fetch_sellable_shares(
        clob,
        token_id,
        log_prefix="STOP-LOSS",
        trade_id=trade_id,
        initial_delay=initial_delay,
    )
    if share_info is None:
        return None

    _, sellable_shares = share_info
    loop = asyncio.get_event_loop()
    from py_clob_client.order_builder.constants import SELL

    log.info(
        "[STOP-LOSS] Attempting GTC sell - token: %s | shares: %d | price: %s | trade_id: %d",
        token_id[:16],
        sellable_shares,
        stop_loss_price,
        trade_id,
    )
    try:
        def _place():
            sell_args = OrderArgs(
                token_id=token_id,
                price=round(stop_loss_price, 2),
                size=float(sellable_shares),
                side=SELL,
            )
            signed = clob.create_order(sell_args)
            return clob.post_order(signed, OrderType.GTC)

        resp = await asyncio.wait_for(
            loop.run_in_executor(None, _place),
            timeout=10.0,
        )
        debug_log.info(
            "[STOP-LOSS] Placement response for trade %d | keys=%s",
            trade_id,
            sorted(resp.keys()) if isinstance(resp, dict) else type(resp).__name__,
        )

        order_id = resp.get("orderID") or resp.get("id") if isinstance(resp, dict) else None
        if order_id:
            await db.update_stop_loss_order(trade_id, order_id, stop_loss_price)
            log.info(
                "[STOP-LOSS] GTC order placed for trade %d @ %.2f | order: %s",
                trade_id,
                stop_loss_price,
                order_id[:16],
            )
            return order_id

        log.warning("[STOP-LOSS] No order ID returned for trade %d - no stop-loss active", trade_id)
    except asyncio.TimeoutError:
        log.error("[STOP-LOSS] Timeout placing stop-loss for trade %d - continuing without stop-loss", trade_id)
    except Exception as exc:
        log.error("[STOP-LOSS] Full error for trade %d: %s: %s", trade_id, type(exc).__name__, exc)
        log.error(
            "[STOP-LOSS] Failed order args - token: %s | size: %s | price: %s | side: SELL",
            token_id[:16],
            shares,
            stop_loss_price,
        )
    return None


async def execute_limit_exit_order(
    clob: ClobClient,
    token_id: str,
    target_price: float,
    *,
    log_prefix: str,
    trade_id: int | None = None,
    initial_delay: float = 0.0,
    timeout: float = 3.0,
) -> dict | None:
    share_info = await _fetch_sellable_shares(
        clob,
        token_id,
        log_prefix=log_prefix,
        trade_id=trade_id,
        initial_delay=initial_delay,
    )
    if share_info is None:
        return None

    _, sellable_shares = share_info
    loop = asyncio.get_event_loop()
    from py_clob_client.order_builder.constants import SELL

    try:
        log.info(
            "[%s] Attempting limit exit for trade %s | target: %.4f | shares: %d",
            log_prefix,
            trade_id if trade_id is not None else "?",
            target_price,
            sellable_shares,
        )

        def _place():
            sell_args = OrderArgs(
                token_id=token_id,
                price=round(target_price, 2),
                size=float(sellable_shares),
                side=SELL,
            )
            signed = clob.create_order(sell_args)
            return clob.post_order(signed, OrderType.GTC)

        resp = await asyncio.wait_for(
            loop.run_in_executor(None, _place),
            timeout=10.0,
        )
        order_id = resp.get("orderID") or resp.get("id") if isinstance(resp, dict) else None
        status = (resp.get("status") or "").upper() if isinstance(resp, dict) else ""

        if status in ("MATCHED", "FILLED"):
            fill_shares, fill_price = _parse_fill_from_resp(resp, sellable_shares, round(target_price, 2))
            log.info(
                "[%s] Limit exit filled immediately for trade %s | %d shares @ %.4f",
                log_prefix,
                trade_id if trade_id is not None else "?",
                fill_shares,
                fill_price,
            )
            return {
                "order_id": order_id,
                "fill_price": fill_price,
                "fill_shares": fill_shares,
            }

        if not order_id:
            log.warning("[%s] No order ID returned for limit exit", log_prefix)
            return None

        filled, order_detail = await _wait_for_fill(clob, order_id, timeout)
        if filled:
            fill_shares, fill_price = _parse_fill_from_resp(
                order_detail,
                sellable_shares,
                round(target_price, 2),
            )
            log.info(
                "[%s] Limit exit filled for trade %s | %d shares @ %.4f | order=%s",
                log_prefix,
                trade_id if trade_id is not None else "?",
                fill_shares,
                fill_price,
                order_id[:16],
            )
            return {
                "order_id": order_id,
                "fill_price": fill_price,
                "fill_shares": fill_shares,
            }

        await _cancel_open_order(clob, order_id)
        log.warning("[%s] Limit exit order %s did not fill in time", log_prefix, order_id[:16])
    except asyncio.TimeoutError:
        log.error("[%s] Timeout placing limit exit order", log_prefix)
    except Exception as exc:
        log.error("[%s] Failed to place limit exit order: %s", log_prefix, exc)
    return None


def get_best_sell_price(clob: ClobClient, token_id: str) -> float | None:
    return _get_best_price(clob, token_id, "SELL")


async def force_close_position(
    clob: ClobClient,
    token_id: str,
    *,
    trade_id: int | None = None,
    preferred_price: float | None = None,
    reason: str = "",
) -> dict | None:
    exit_price = preferred_price if preferred_price is not None else get_best_sell_price(clob, token_id)
    if exit_price is None:
        log.error("[FORCED-EXIT] No executable sell price available for trade %s (%s)", trade_id, reason)
        return None

    log.warning(
        "[FORCED-EXIT] Closing trade %s immediately at %.4f (%s)",
        trade_id,
        exit_price,
        reason,
    )
    return await execute_limit_exit_order(
        clob,
        token_id,
        exit_price,
        log_prefix="FORCED-EXIT",
        trade_id=trade_id,
        timeout=3.0,
    )


async def _resolve_forced_exit(
    *,
    trade_id: int,
    market: db.MarketInfo,
    signal: Signal,
    entry_price: float,
    shares: float,
    exit_fill: dict,
    reason: str,
) -> None:
    exit_price = float(exit_fill["fill_price"])
    resolved_shares = float(shares or 0.0)
    pnl = (exit_price - entry_price) * resolved_shares
    outcome = "take_profit" if pnl >= 0 else "stop_loss"

    if outcome == "take_profit":
        await db.mark_take_profit_triggered(trade_id, exit_price)
    else:
        await db.mark_stop_loss_triggered(trade_id, exit_price)

    record_trade_outcome(pnl)
    log.warning(
        "[FORCED-EXIT] Trade %d closed immediately | %s %s on %s | exit @ %.4f | pnl: %+.2f | reason: %s",
        trade_id,
        signal.strategy_name,
        signal.direction,
        market.market_type,
        exit_price,
        pnl,
        reason,
    )
    await db.log_event(
        "trade_forced_exit",
        f"Forced exit for {signal.strategy_name} {signal.direction} on {market.market_type} | "
        f"exit {exit_price:.4f} | pnl {pnl:+.2f} | reason: {reason}",
        {
            "trade_id": trade_id,
            "market_id": market.market_id,
            "market_type": market.market_type,
            "strategy_name": signal.strategy_name,
            "direction": signal.direction,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "shares": round(resolved_shares, 4),
            "pnl": round(pnl, 2),
            "reason": reason,
            "order_id": exit_fill.get("order_id"),
        },
    )


async def _wait_for_fill(clob: ClobClient, order_id: str, timeout: float) -> tuple[bool, dict | None]:
    """Poll order status until filled or timeout. Returns (filled, order_details)."""
    loop = asyncio.get_event_loop()
    start = time.time()
    while time.time() - start < timeout:
        try:
            order = await asyncio.wait_for(
                loop.run_in_executor(None, lambda oid=order_id: clob.get_order(oid)),
                timeout=3.0,
            )
            if isinstance(order, dict):
                status = (order.get("status") or "").upper()
                if status in ("MATCHED", "FILLED"):
                    return True, order
                if status in ("CANCELLED", "EXPIRED"):
                    return False, order
        except Exception:
            pass
        await asyncio.sleep(0.15)
    return False, None


async def _cancel_open_order(clob: ClobClient, order_id: str) -> bool:
    """Cancel an open GTC order. Returns True on success."""
    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda oid=order_id: clob.cancel(oid)),
            timeout=5.0,
        )
        return True
    except Exception as e:
        log.warning("[EXEC] Failed to cancel order %s: %s", order_id[:16] if order_id else "?", e)
        return False


def _parse_fill_from_resp(resp: dict | None, fallback_shares: int, fallback_price: float) -> tuple[int, float]:
    """Extract fill shares and price from an order response dict."""
    fill_shares = fallback_shares
    fill_price = fallback_price
    if isinstance(resp, dict):
        raw_shares = resp.get("size_matched") or resp.get("matched_size") or resp.get("filled")
        raw_price = resp.get("average_price") or resp.get("price")
        if raw_shares is not None:
            try:
                parsed_shares = math.floor(float(raw_shares))
            except (TypeError, ValueError):
                parsed_shares = 0
            if parsed_shares > 0:
                fill_shares = parsed_shares
            elif fill_shares > 0:
                log.warning(
                    "[EXEC] Filled response reported non-positive matched size (%s); using fallback %d shares",
                    raw_shares,
                    fill_shares,
                )
        if raw_price is not None:
            try:
                parsed_price = float(raw_price)
            except (TypeError, ValueError):
                parsed_price = 0.0
            if parsed_price > 0:
                fill_price = parsed_price
    return fill_shares, fill_price


async def _execute_hybrid(
    clob: ClobClient,
    token_id: str,
    ideal_price: float,
    shares: int,
    *,
    allow_stage_3: bool = True,
) -> dict:
    """Execute order using 3-stage hybrid strategy.

    Stage 1: GTC limit at ideal price   (1.0s poll timeout)
    Stage 2: GTC limit at ideal + $0.01 (1.0s poll timeout)
    Stage 3: FOK at ideal + $0.02       (immediate fill-or-kill)

    Returns dict with: filled, order_id, fill_price, fill_shares, stage,
                       slippage, elapsed, error_status, error_notes
    """
    start_time = time.time()
    loop = asyncio.get_event_loop()

    result: dict = {
        "filled": False,
        "order_id": None,
        "fill_price": None,
        "fill_shares": None,
        "stage": ExecutionStage.FAILED,
        "slippage": 0.0,
        "elapsed": 0.0,
        "error_status": "hybrid_no_fill",
        "error_notes": None,
    }

    # (stage_name, price_offset, poll_timeout, order_type)
    stages = [
        (ExecutionStage.IDEAL_LIMIT, EXECUTION_CONFIG["stage_1_offset"], EXECUTION_CONFIG["stage_1_timeout"], OrderType.GTC),
        (ExecutionStage.RELAXED_LIMIT, EXECUTION_CONFIG["stage_2_offset"], EXECUTION_CONFIG["stage_2_timeout"], OrderType.GTC),
    ]
    if allow_stage_3:
        stages.append(
            (ExecutionStage.MARKET_FOK, EXECUTION_CONFIG["stage_3_offset"], None, OrderType.FOK)
        )

    for stage_name, offset, poll_timeout, order_type in stages:
        if time.time() - start_time >= EXECUTION_CONFIG['max_total_execution_seconds']:
            log.info("[EXEC] Total execution budget exhausted before %s", _STAGE_LABELS.get(stage_name, stage_name))
            break

        price = round(ideal_price + offset, 2)
        if price <= 0 or price >= 1:
            continue
        label = _STAGE_LABELS.get(stage_name, stage_name)
        slippage_cents = round(offset * 100)

        log.info(
            "[EXEC] %s | BUY %d shares @ $%.2f (+%d¢) | %s | timeout: %s",
            label, shares, price, slippage_cents,
            "GTC" if order_type == OrderType.GTC else "FOK",
            f"{poll_timeout}s" if poll_timeout else "immediate",
        )

        # FOK retry loop: keep retrying if price hasn't moved, up to max time
        fok_deadline = time.time() + EXECUTION_CONFIG['fok_retry_max_seconds'] if order_type == OrderType.FOK else 0
        fok_attempt = 0

        while True:
            if time.time() - start_time >= EXECUTION_CONFIG['max_total_execution_seconds']:
                log.info("[EXEC] %s — stopping: total execution budget exhausted", label)
                break

            fok_attempt += 1

            try:
                def _place(p=price, s=shares, ot=order_type):
                    order_args = OrderArgs(token_id=token_id, price=p, size=s, side="BUY")
                    signed = clob.create_order(order_args)
                    return clob.post_order(signed, ot)

                resp = await asyncio.wait_for(
                    loop.run_in_executor(None, _place),
                    timeout=5.0,
                )

                order_id = (resp.get("orderID") or resp.get("order_id")) if isinstance(resp, dict) else None
                order_status = (resp.get("status") or "").upper() if isinstance(resp, dict) else ""

                if order_type == OrderType.FOK:
                    # FOK: check immediate fill from response
                    if order_status in ("CANCELLED", "EXPIRED", ""):
                        # Check if we should retry
                        if time.time() < fok_deadline:
                            # Check if price has moved — if so, stop retrying
                            current_best = _get_best_price(clob, token_id, "BUY")
                            if current_best is not None and current_best > price:
                                log.info("[EXEC] %s — FOK no fill, price moved ($%.4f > $%.2f), stopping retries",
                                         label, current_best, price)
                                break  # price moved, exit retry loop
                            log.info("[EXEC] %s — FOK no fill (attempt %d), price stable, retrying...",
                                     label, fok_attempt)
                            await asyncio.sleep(EXECUTION_CONFIG['fok_retry_interval'])
                            continue  # retry FOK
                        else:
                            log.info("[EXEC] %s — FOK no fill after %d attempts (%.0fs), giving up",
                                     label, fok_attempt, EXECUTION_CONFIG['fok_retry_max_seconds'])
                            break  # deadline reached, exit retry loop

                    fill_shares, fill_price = _parse_fill_from_resp(resp, shares, price)
                    elapsed = time.time() - start_time
                    slippage = (fill_price - ideal_price) * fill_shares

                    _exec_metrics.record(stage_name, True, slippage, elapsed)
                    log.info(
                        "[EXEC] ✅ %s filled (attempt %d) | %d shares @ $%.4f | slippage: $%.3f | time: %.2fs",
                        label, fok_attempt, fill_shares, fill_price, slippage, elapsed,
                    )
                    result.update({
                        "filled": True, "order_id": order_id,
                        "fill_price": fill_price, "fill_shares": fill_shares,
                        "stage": stage_name, "slippage": slippage, "elapsed": elapsed,
                    })
                    return result

                else:
                    # GTC: check if immediately matched, otherwise poll
                    if order_status in ("MATCHED", "FILLED"):
                        fill_shares, fill_price = _parse_fill_from_resp(resp, shares, price)
                        elapsed = time.time() - start_time
                        slippage = (fill_price - ideal_price) * fill_shares

                        _exec_metrics.record(stage_name, True, slippage, elapsed)
                        log.info(
                            "[EXEC] ✅ %s filled (immediate) | %d shares @ $%.4f | slippage: $%.3f | time: %.2fs",
                            label, fill_shares, fill_price, slippage, elapsed,
                        )
                        result.update({
                            "filled": True, "order_id": order_id,
                            "fill_price": fill_price, "fill_shares": fill_shares,
                            "stage": stage_name, "slippage": slippage, "elapsed": elapsed,
                        })
                        return result

                    if not order_id:
                        log.warning("[EXEC] %s — no order ID returned, skipping stage", label)
                        break  # exit retry loop, move to next stage

                    # Poll for fill
                    filled, order_detail = await _wait_for_fill(clob, order_id, poll_timeout)
                    if filled:
                        fill_shares, fill_price = _parse_fill_from_resp(order_detail, shares, price)
                        elapsed = time.time() - start_time
                        slippage = (fill_price - ideal_price) * fill_shares

                        _exec_metrics.record(stage_name, True, slippage, elapsed)
                        log.info(
                            "[EXEC] ✅ %s filled | %d shares @ $%.4f | slippage: $%.3f | time: %.2fs",
                            label, fill_shares, fill_price, slippage, elapsed,
                        )
                        result.update({
                            "filled": True, "order_id": order_id,
                            "fill_price": fill_price, "fill_shares": fill_shares,
                            "stage": stage_name, "slippage": slippage, "elapsed": elapsed,
                        })
                        return result

                    # Not filled — cancel and move to next stage
                    log.info("[EXEC] ⏱️ %s timeout after %.1fs — cancelling", label, poll_timeout)
                    await _cancel_open_order(clob, order_id)
                    break  # exit retry loop, move to next stage

            except asyncio.TimeoutError:
                log.warning("[EXEC] %s — API timeout, continuing to next stage", label)
                break  # exit retry loop

            except Exception as exc:
                exc_msg = str(exc).lower()
                # Fatal errors — stop all stages
                if "min size" in exc_msg or "invalid amount" in exc_msg:
                    result["error_status"] = "error"
                    result["error_notes"] = str(exc)[:500]
                    log.warning("[EXEC] %s — order too small: %s", label, exc)
                    return result  # fatal, exit entirely
                elif "insufficient" in exc_msg or "balance" in exc_msg:
                    result["error_status"] = "error"
                    result["error_notes"] = str(exc)[:500]
                    log.error("[EXEC] %s — insufficient funds: %s", label, exc)
                    return result  # fatal, exit entirely
                elif "closed" in exc_msg or "resolved" in exc_msg:
                    result["error_status"] = "error"
                    result["error_notes"] = str(exc)[:500]
                    log.warning("[EXEC] %s — market closed/resolved", label)
                    return result  # fatal, exit entirely
                # Non-fatal — for FOK, retry if within deadline; for GTC, move to next stage
                elif "couldn't be fully filled" in exc_msg or "fully filled or killed" in exc_msg:
                    if order_type == OrderType.FOK and time.time() < fok_deadline and fok_attempt < EXECUTION_CONFIG['fok_max_attempts']:
                        current_best = _get_best_price(clob, token_id, "BUY")
                        if current_best is not None and current_best > price:
                            log.info("[EXEC] %s — FOK exception, price moved ($%.4f > $%.2f), stopping retries",
                                     label, current_best, price)
                            break
                        log.info("[EXEC] %s — FOK exception (attempt %d), retrying...", label, fok_attempt)
                        await asyncio.sleep(EXECUTION_CONFIG['fok_retry_interval'])
                        continue  # retry
                    log.info("[EXEC] %s — no fill (FOK exception after %d attempt%s)",
                             label, fok_attempt, "" if fok_attempt == 1 else "s")
                    break  # exit retry loop
                else:
                    log.warning("[EXEC] %s — error: %s, continuing", label, exc)
                    break  # exit retry loop

    # All stages exhausted or fatal error
    elapsed = time.time() - start_time
    result["elapsed"] = elapsed
    if result["error_status"] == "hybrid_no_fill":
        _exec_metrics.record(ExecutionStage.FAILED, False, 0.0, elapsed)
        log.error("[EXEC] ❌ All stages exhausted after %.2fs — order not filled", elapsed)
    return result


async def execute_trade(
    clob: ClobClient,
    market: db.MarketInfo,
    signal: Signal,
    live_config: dict | None = None,
) -> None:
    """Place a trade based on a strategy signal. Records result to bot_trades."""
    _reset_daily_if_needed()
    if live_config is None:
        live_config = {}

    market_label = f"{market.market_type}:{market.market_id[:12]}"

    # ── Use locked parameters from signal (never recalculate) ──────────
    ideal_price = round(signal.entry_price, 2)
    locked_shares = signal.locked_shares if signal.locked_shares > 0 else max(
        1, math.floor(float(signal.signal_data.get('bet_cost', config.BET_SIZE_USD)) / signal.entry_price)
    ) if signal.entry_price > 0 else 1
    bet_size = signal.locked_cost if signal.locked_cost > 0 else round(
        float(signal.signal_data.get('bet_cost', config.BET_SIZE_USD)), 2
    )
    bet_size = max(
        bet_size,
        MIN_DOLLAR_SIZE,
        round(ideal_price * config.MIN_ENTRY_SHARES, 2) if ideal_price > 0 else MIN_DOLLAR_SIZE,
    )
    tag = strategy_log_tag(signal.strategy_name)
    log.info(
        "[BET] %s on %s — $%.2f (%d shares @ $%.4f) [LOCKED]",
        signal.strategy_name, market.market_type,
        bet_size, locked_shares, ideal_price,
    )

    # ── Dry-run mode ────────────────────────────────────────────────────
    if config.DRY_RUN:
        log.info(
            "[DRY RUN] Would place BUY %s on %s at %.4f — strategy: %s ($%.2f)",
            signal.direction, market_label, signal.entry_price,
            signal.strategy_name, bet_size,
        )
        await db.insert_bot_trade(
            market_id=market.market_id, market_type=market.market_type,
            strategy_name=signal.strategy_name, direction=signal.direction,
            entry_price=signal.entry_price, bet_size_usd=bet_size,
            status="dry_run", condition_id=market.market_id,
            signal_data=signal.signal_data,
        )
        await db.log_event("trade_dry_run",
            f"[DRY RUN] Would place {signal.direction} on {market.market_type} — strategy: {signal.strategy_name}", {
                "market_id": market.market_id,
                "market_type": market.market_type,
                "strategy_name": signal.strategy_name,
                "direction": signal.direction,
                "entry_price": signal.entry_price,
                "signal_data": signal.signal_data,
            })
        return

    # ── Guard: daily loss limit ────────────────────────────────────────
    await sync_daily_net_loss_from_db()
    daily_limit = float(live_config.get('daily_loss_limit', str(config.DAILY_LOSS_LIMIT)))
    if is_daily_limit_reached(daily_limit):
        log.warning("Daily loss limit reached — net loss today: $%.2f / $%.2f", _daily_net_loss, daily_limit)
        await db.insert_bot_trade(
            market_id=market.market_id, market_type=market.market_type,
            strategy_name=signal.strategy_name, direction=signal.direction,
            entry_price=signal.entry_price, bet_size_usd=bet_size,
            status="skipped_daily_limit", condition_id=market.market_id,
            signal_data=signal.signal_data,
        )
        await db.log_event("trade_skipped",
            f"Daily loss limit reached — net loss today: ${_daily_net_loss:.2f} / ${daily_limit:.2f}", {
                "market_id": market.market_id,
                "market_type": market.market_type,
                "strategy_name": signal.strategy_name,
                "direction": signal.direction,
                "reason": "daily_limit",
                "daily_net_loss": _daily_net_loss,
                "daily_loss_limit": daily_limit,
            })
        return

    # ── Guard: bankroll ─────────────────────────────────────────────────
    balance = await get_usdc_balance()
    if balance >= 0:
        min_runway = bet_size * 2
        if balance < min_runway:
            log.critical("Bankroll critically low ($%.2f < $%.2f) — bot paused", balance, min_runway)
            await db.insert_bot_trade(
                market_id=market.market_id, market_type=market.market_type,
                strategy_name=signal.strategy_name, direction=signal.direction,
                entry_price=signal.entry_price, bet_size_usd=bet_size,
                status="skipped_bankroll", condition_id=market.market_id,
                signal_data=signal.signal_data,
            )
            await db.log_event("trade_skipped",
                f"Signal skipped — bankroll (${balance:.2f} < ${min_runway:.2f})", {
                    "market_id": market.market_id,
                    "market_type": market.market_type,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "reason": "bankroll",
                    "balance": balance,
                    "min_runway": min_runway,
                })
            return

    # ── Resolve token IDs ───────────────────────────────────────────────
    up_token_id = market.up_token_id
    down_token_id = market.down_token_id
    stop_loss_enabled = True

    if not up_token_id or not down_token_id:
        ids = _fetch_token_ids(clob, market.market_id)
        if ids is None:
            log.warning("[TOKENS] Could not resolve token IDs for %s — placing trade WITHOUT stop-loss", market_label)
            stop_loss_enabled = False
            # Cannot place trade without token IDs — still need them for the order
            await db.insert_bot_trade(
                market_id=market.market_id, market_type=market.market_type,
                strategy_name=signal.strategy_name, direction=signal.direction,
                entry_price=signal.entry_price, bet_size_usd=bet_size,
                status="error", condition_id=market.market_id,
                notes="Failed to resolve token IDs",
                signal_data=signal.signal_data,
            )
            await db.log_event("bot_error",
                f"Failed to resolve token IDs for {market_label}", {
                    "market_id": market.market_id,
                })
            return
        up_token_id, down_token_id = ids
        market.up_token_id = up_token_id
        market.down_token_id = down_token_id

    token_id = up_token_id if signal.direction == "Up" else down_token_id

    # ── Validate locked price ──────────────────────────────────────────
    status = "error"
    order_id = None
    my_shares: float | None = locked_shares
    actual_price: float | None = None
    error_notes: str | None = None
    protection_notes: str | None = None
    price_variance: float | None = None
    price_variance_pct: float | None = None
    shares_variance: int | None = None
    signal_age_s: float | None = None

    if ideal_price <= 0 or ideal_price >= 1:
        log.warning("Locked price %.2f out of range — skipping %s", ideal_price, market_label)
        await db.insert_bot_trade(
            market_id=market.market_id, market_type=market.market_type,
            strategy_name=signal.strategy_name, direction=signal.direction,
            entry_price=signal.entry_price, bet_size_usd=bet_size,
            token_id=token_id, condition_id=market.market_id,
            status="error", notes=f"Locked price out of range: {ideal_price}",
            signal_data=signal.signal_data,
        )
        return

    # ── Pre-order price validation against strategy range ──────────────
    pre_price_min = float(signal.signal_data.get('price_min', live_config.get('price_min', '0.01')))
    pre_price_max = float(signal.signal_data.get('price_max', live_config.get('price_max', '0.99')))
    if ideal_price < pre_price_min or ideal_price > pre_price_max:
        log.warning(
            "Locked price %.4f outside strategy range [%.2f, %.2f] — skipping %s",
            ideal_price, pre_price_min, pre_price_max, market_label,
        )
        await db.insert_bot_trade(
            market_id=market.market_id, market_type=market.market_type,
            strategy_name=signal.strategy_name, direction=signal.direction,
            entry_price=signal.entry_price, bet_size_usd=bet_size,
            token_id=token_id, condition_id=market.market_id,
            status="skipped_price_range",
            notes=f"Locked price {ideal_price:.4f} outside [{pre_price_min:.2f}, {pre_price_max:.2f}]",
            signal_data=signal.signal_data,
        )
        return

    # ── Minimum shares check ──────────────────────────────────────────
    min_shares = max(config.MIN_ENTRY_SHARES, math.ceil(MIN_DOLLAR_SIZE / ideal_price)) if ideal_price > 0 else config.MIN_ENTRY_SHARES
    if locked_shares < min_shares:
        locked_shares = min_shares
        my_shares = locked_shares

    if locked_shares < config.MIN_ENTRY_SHARES:
        log.warning("Cannot meet $1 minimum at price %.2f — skipping", ideal_price)
        await db.insert_bot_trade(
            market_id=market.market_id, market_type=market.market_type,
            strategy_name=signal.strategy_name, direction=signal.direction,
            entry_price=signal.entry_price, bet_size_usd=bet_size,
            token_id=token_id, condition_id=market.market_id,
            status="error", notes="Order too small",
            signal_data=signal.signal_data,
        )
        return

    # Log time elapsed since signal was generated
    signal_age_ms = (datetime.now(timezone.utc) - signal.created_at).total_seconds() * 1000
    log.info("[TIMING] Signal age at order submission: %.0fms — %s %s on %s",
             signal_age_ms, signal.strategy_name, signal.direction, market_label)

    # ── Execute with hybrid strategy using LOCKED parameters ─────────
    hybrid = await _execute_hybrid(clob, token_id, ideal_price, locked_shares)

    order_id = hybrid["order_id"]
    error_notes = hybrid.get("error_notes")
    execution_stage = hybrid["stage"]

    if hybrid["filled"]:
        actual_shares = hybrid["fill_shares"]
        actual_price = hybrid["fill_price"]
        actual_cost = actual_shares * actual_price

        # ── Variance tracking (locked vs actual) ──────────────────────
        price_variance = round(actual_price - ideal_price, 6)
        price_variance_pct = round((price_variance / ideal_price) * 100, 4) if ideal_price > 0 else 0.0
        shares_variance = actual_shares - locked_shares
        signal_age_s = round((datetime.now(timezone.utc) - signal.created_at).total_seconds(), 2)
        _variance_metrics.add_execution(price_variance_pct, shares_variance, signal_age_s)

        log.info(
            "[%s] LOCKED: $%.4f x %dsh = $%.2f | ACTUAL: $%.4f x %dsh = $%.2f | "
            "Variance: %+.2f%% (%+dsh) | Age: %.2fs",
            tag, ideal_price, locked_shares, bet_size,
            actual_price, actual_shares, actual_cost,
            price_variance_pct, shares_variance, signal_age_s,
        )
        if abs(price_variance_pct) > 1.0:
            log.warning("[%s] High price variance: %+.2f%% (locked: $%.4f, actual: $%.4f)",
                        tag, price_variance_pct, ideal_price, actual_price)
        if shares_variance != 0:
            log.warning("[%s] Share variance: %+d shares (locked: %d, actual: %d)",
                        tag, shares_variance, locked_shares, actual_shares)

        # Post-fill price validation against strategy range
        fill_price_min = float(signal.signal_data.get('price_min', live_config.get('price_min', '0.01')))
        fill_price_max = float(signal.signal_data.get('price_max', live_config.get('price_max', '0.99')))
        if actual_price < fill_price_min or actual_price > fill_price_max:
            status = "filled_price_rejected"
            my_shares = actual_shares
            bet_size = round(actual_cost, 2)
            log.warning(
                "FILL PRICE REJECTED — %s %s on %s | filled @ %.4f outside [%.2f, %.2f] | locked was %.4f | stage: %s",
                signal.strategy_name, signal.direction, market_label,
                actual_price, fill_price_min, fill_price_max,
                ideal_price, execution_stage,
            )
            await db.log_event("trade_fill_price_rejected",
                f"Fill price {actual_price:.4f} outside [{fill_price_min:.2f}, {fill_price_max:.2f}] on {market.market_type}", {
                    "market_id": market.market_id,
                    "market_type": market.market_type,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "actual_price": actual_price,
                    "locked_price": ideal_price,
                    "price_variance": price_variance,
                    "price_variance_pct": price_variance_pct,
                    "price_min": fill_price_min,
                    "price_max": fill_price_max,
                    "shares": actual_shares,
                    "order_id": order_id,
                    "execution_stage": execution_stage,
                    "signal_data": signal.signal_data,
                })
        else:
            status = "filled"
            my_shares = actual_shares
            bet_size = round(actual_cost, 2)

            log.info(
                "TRADE FILLED — %s %s on %s | %d shares @ %.4f ($%.2f) | stage: %s | slippage: $%.3f | time: %.2fs | order=%s",
                signal.strategy_name, signal.direction, market_label,
                actual_shares, actual_price, actual_cost,
                execution_stage, hybrid["slippage"], hybrid["elapsed"],
                order_id,
            )
            new_balance = await get_usdc_balance()

            await db.log_event("trade_placed",
                f"Placed {signal.direction} on {market.market_type} — strategy: {signal.strategy_name}", {
                    "market_id": market.market_id,
                    "market_type": market.market_type,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "entry_price": actual_price,
                    "locked_entry_price": ideal_price,
                    "bet_size_usd": actual_cost,
                    "shares": actual_shares,
                    "locked_shares": locked_shares,
                    "price_variance": price_variance,
                    "price_variance_pct": price_variance_pct,
                    "shares_variance": shares_variance,
                    "signal_age_seconds": signal_age_s,
                    "execution_stage": execution_stage,
                    "slippage": round(hybrid["slippage"], 4),
                    "execution_time": round(hybrid["elapsed"], 2),
                    "token_id": token_id,
                    "order_id": order_id,
                    "balance_after": new_balance if new_balance >= 0 else None,
                    "signal_data": signal.signal_data,
                })
    else:
        status = hybrid.get("error_status", "hybrid_no_fill")
        actual_price = None

        if status == "hybrid_no_fill":
            log.info("Hybrid no fill — %s %s on %s at %.4f [LOCKED] (all stages exhausted in %.2fs)",
                     signal.strategy_name, signal.direction, market_label,
                     ideal_price, hybrid["elapsed"])
            await db.log_event("trade_hybrid_no_fill",
                f"Hybrid no fill — {signal.strategy_name} {signal.direction} on {market.market_type} at {ideal_price:.4f} [LOCKED]", {
                    "market_id": market.market_id,
                    "market_type": market.market_type,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "locked_entry_price": ideal_price,
                    "locked_shares": locked_shares,
                    "execution_time": round(hybrid["elapsed"], 2),
                    "signal_data": signal.signal_data,
                })

    # ── Record trade in database ─────────────────────────────────────
    trade_id = await db.insert_bot_trade(
        market_id=market.market_id,
        market_type=market.market_type,
        strategy_name=signal.strategy_name,
        direction=signal.direction,
        entry_price=actual_price if status == "filled" and actual_price is not None else signal.entry_price,
        bet_size_usd=bet_size,
        shares=my_shares,
        token_id=token_id,
        condition_id=market.market_id,
        status=status,
        order_id=order_id,
        notes=error_notes if status == "error" else None,
        signal_data=signal.signal_data,
        execution_stage=execution_stage if hybrid["filled"] else None,
        locked_entry_price=ideal_price,
        locked_shares_count=locked_shares,
        locked_cost=signal.locked_cost,
        locked_balance=signal.locked_balance,
        price_variance_val=price_variance,
        price_variance_pct_val=price_variance_pct,
        shares_variance_count=shares_variance,
        signal_generated_at=signal.created_at,
        signal_age_seconds=signal_age_s,
    )

    # Place exit orders after confirmed fill
    if status == "filled" and my_shares and trade_id and stop_loss_enabled:
        exit_tasks = []

        sl_price = signal.signal_data.get('stop_loss_price')
        if sl_price is not None:
            sl_exit = float(sl_price)
            if 0 < sl_exit < 1:
                log.info("[STOP-LOSS] Placing stop-loss @ %.2f | token: %s | direction: %s",
                         sl_exit, token_id[:16], signal.direction)
                exit_tasks.append(place_stop_loss_order(
                    clob=clob,
                    trade_id=trade_id,
                    token_id=token_id,
                    shares=my_shares,
                    stop_loss_price=sl_exit,
                ))

        tp_price = signal.signal_data.get('take_profit_price')
        if tp_price is not None:
            tp_exit = float(tp_price)
            if 0 < tp_exit < 1:
                log.info("[TAKE-PROFIT] Placing take-profit @ %.2f | token: %s | direction: %s",
                         tp_exit, token_id[:16], signal.direction)
                exit_tasks.append(place_take_profit_order(
                    clob=clob,
                    trade_id=trade_id,
                    token_id=token_id,
                    shares=my_shares,
                    take_profit_price=tp_exit,
                ))

        if exit_tasks:
            await asyncio.gather(*exit_tasks, return_exceptions=True)


async def execute_trade(
    clob: ClobClient,
    market: db.MarketInfo,
    signal: Signal,
    live_config: dict | None = None,
) -> None:
    """Place a live trade only if the resulting position can be protected."""
    _reset_daily_if_needed()
    if live_config is None:
        live_config = {}

    signal_data = dict(signal.signal_data or {})
    market_label = f"{market.market_type}:{market.market_id[:12]}"

    ideal_price = round(signal.entry_price, 2)
    locked_shares = signal.locked_shares if signal.locked_shares > 0 else max(
        config.MIN_ENTRY_SHARES,
        math.floor(float(signal_data.get("bet_cost", config.BET_SIZE_USD)) / signal.entry_price),
    ) if signal.entry_price > 0 else config.MIN_ENTRY_SHARES
    bet_size = signal.locked_cost if signal.locked_cost > 0 else round(
        float(signal_data.get("bet_cost", config.BET_SIZE_USD)),
        2,
    )
    bet_size = max(
        bet_size,
        MIN_DOLLAR_SIZE,
        round(ideal_price * config.MIN_ENTRY_SHARES, 2) if ideal_price > 0 else MIN_DOLLAR_SIZE,
    )
    tag = strategy_log_tag(signal.strategy_name)
    log.info(
        "[BET] %s on %s - $%.2f (%d shares @ $%.4f) [LOCKED]",
        signal.strategy_name,
        market.market_type,
        bet_size,
        locked_shares,
        ideal_price,
    )

    if config.DRY_RUN:
        log.info(
            "[DRY RUN] Would place BUY %s on %s at %.4f - strategy: %s ($%.2f)",
            signal.direction,
            market_label,
            signal.entry_price,
            signal.strategy_name,
            bet_size,
        )
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            status="dry_run",
            condition_id=market.market_id,
            signal_data=signal_data,
        )
        await db.log_event(
            "trade_dry_run",
            f"[DRY RUN] Would place {signal.direction} on {market.market_type} - strategy: {signal.strategy_name}",
            {
                "market_id": market.market_id,
                "market_type": market.market_type,
                "strategy_name": signal.strategy_name,
                "direction": signal.direction,
                "entry_price": signal.entry_price,
                "signal_data": signal_data,
            },
        )
        return

    await sync_daily_net_loss_from_db()
    daily_limit = float(live_config.get("daily_loss_limit", str(config.DAILY_LOSS_LIMIT)))
    if is_daily_limit_reached(daily_limit):
        log.warning("Daily loss limit reached - net loss today: $%.2f / $%.2f", _daily_net_loss, daily_limit)
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            status="skipped_daily_limit",
            condition_id=market.market_id,
            signal_data=signal_data,
        )
        await db.log_event(
            "trade_skipped",
            f"Daily loss limit reached - net loss today: ${_daily_net_loss:.2f} / ${daily_limit:.2f}",
            {
                "market_id": market.market_id,
                "market_type": market.market_type,
                "strategy_name": signal.strategy_name,
                "direction": signal.direction,
                "reason": "daily_limit",
                "daily_net_loss": _daily_net_loss,
                "daily_loss_limit": daily_limit,
            },
        )
        return

    balance = await get_usdc_balance()
    if balance >= 0:
        min_runway = bet_size * 2
        if balance < min_runway:
            log.critical("Bankroll critically low ($%.2f < $%.2f) - bot paused", balance, min_runway)
            await db.insert_bot_trade(
                market_id=market.market_id,
                market_type=market.market_type,
                strategy_name=signal.strategy_name,
                direction=signal.direction,
                entry_price=signal.entry_price,
                bet_size_usd=bet_size,
                status="skipped_bankroll",
                condition_id=market.market_id,
                signal_data=signal_data,
            )
            await db.log_event(
                "trade_skipped",
                f"Signal skipped - bankroll (${balance:.2f} < ${min_runway:.2f})",
                {
                    "market_id": market.market_id,
                    "market_type": market.market_type,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "reason": "bankroll",
                    "balance": balance,
                    "min_runway": min_runway,
                },
            )
            return

    up_token_id = market.up_token_id
    down_token_id = market.down_token_id
    if not up_token_id or not down_token_id:
        ids = _fetch_token_ids(clob, market.market_id)
        if ids is None:
            log.warning("[TOKENS] Could not resolve token IDs for %s", market_label)
            await db.insert_bot_trade(
                market_id=market.market_id,
                market_type=market.market_type,
                strategy_name=signal.strategy_name,
                direction=signal.direction,
                entry_price=signal.entry_price,
                bet_size_usd=bet_size,
                status="error",
                condition_id=market.market_id,
                notes="Failed to resolve token IDs",
                signal_data=signal_data,
            )
            await db.log_event(
                "bot_error",
                f"Failed to resolve token IDs for {market_label}",
                {"market_id": market.market_id},
            )
            return
        up_token_id, down_token_id = ids
        market.up_token_id = up_token_id
        market.down_token_id = down_token_id

    token_id = up_token_id if signal.direction == "Up" else down_token_id

    if ideal_price <= 0 or ideal_price >= 1:
        log.warning("Locked price %.2f out of range - skipping %s", ideal_price, market_label)
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            token_id=token_id,
            condition_id=market.market_id,
            status="error",
            notes=f"Locked price out of range: {ideal_price}",
            signal_data=signal_data,
        )
        return

    pre_price_min = float(signal_data.get("price_min", live_config.get("price_min", "0.01")))
    pre_price_max = float(signal_data.get("price_max", live_config.get("price_max", "0.99")))
    if ideal_price < pre_price_min or ideal_price > pre_price_max:
        log.warning(
            "Locked price %.4f outside strategy range [%.2f, %.2f] - skipping %s",
            ideal_price,
            pre_price_min,
            pre_price_max,
            market_label,
        )
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            token_id=token_id,
            condition_id=market.market_id,
            status="skipped_price_range",
            notes=f"Locked price {ideal_price:.4f} outside [{pre_price_min:.2f}, {pre_price_max:.2f}]",
            signal_data=signal_data,
        )
        return

    raw_stop_loss = signal_data.get("stop_loss_price")
    raw_take_profit = signal_data.get("take_profit_price")
    try:
        locked_stop_loss = float(raw_stop_loss) if raw_stop_loss is not None else None
        locked_take_profit = float(raw_take_profit) if raw_take_profit is not None else None
    except (TypeError, ValueError):
        locked_stop_loss = None
        locked_take_profit = None

    if locked_stop_loss is None or locked_take_profit is None:
        log.warning("Missing exit targets for %s - skipping unprotected entry", market_label)
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            token_id=token_id,
            condition_id=market.market_id,
            status="skipped_unprotected",
            notes="Missing stop-loss or take-profit target",
            signal_data=signal_data,
        )
        return

    locked_sl_distance = abs(ideal_price - locked_stop_loss)
    locked_tp_distance = abs(locked_take_profit - ideal_price)
    if locked_sl_distance <= 0 or locked_tp_distance <= 0:
        log.warning(
            "Non-viable exit distances for %s - sl distance %.4f | tp distance %.4f",
            market_label,
            locked_sl_distance,
            locked_tp_distance,
        )
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            token_id=token_id,
            condition_id=market.market_id,
            status="skipped_unprotected",
            notes="Exit distances are zero",
            signal_data=signal_data,
        )
        return

    min_shares = max(
        config.MIN_ENTRY_SHARES,
        math.ceil(MIN_DOLLAR_SIZE / ideal_price),
    ) if ideal_price > 0 else config.MIN_ENTRY_SHARES
    if locked_shares < min_shares:
        previous_shares = locked_shares
        previous_bet_size = bet_size
        locked_shares = min_shares
        bet_size = round(max(bet_size, locked_shares * ideal_price), 2)
        log.info(
            "[BET] Raised live order size for %s on %s | shares: %d -> %d | notional: $%.2f -> $%.2f",
            signal.strategy_name,
            market.market_type,
            previous_shares,
            locked_shares,
            previous_bet_size,
            bet_size,
        )

    if locked_shares < config.MIN_ENTRY_SHARES:
        log.warning(
            "Cannot meet live minimums at price %.2f - need at least %d shares",
            ideal_price,
            config.MIN_ENTRY_SHARES,
        )
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            token_id=token_id,
            condition_id=market.market_id,
            status="error",
            notes="Order too small for live minimums",
            signal_data=signal_data,
        )
        return

    signal_age_ms = (datetime.now(timezone.utc) - signal.created_at).total_seconds() * 1000
    log.info(
        "[TIMING] Signal age at order submission: %.0fms - %s %s on %s",
        signal_age_ms,
        signal.strategy_name,
        signal.direction,
        market_label,
    )

    hybrid = await _execute_hybrid(
        clob,
        token_id,
        ideal_price,
        locked_shares,
        allow_stage_3=bool(signal_data.get("allow_stage_3", True)),
    )

    order_id = hybrid["order_id"]
    error_notes = hybrid.get("error_notes")
    execution_stage = hybrid["stage"]

    if not hybrid["filled"]:
        status = hybrid.get("error_status", "hybrid_no_fill")
        if status == "hybrid_no_fill":
            log.info(
                "Hybrid no fill - %s %s on %s at %.4f [LOCKED] (all stages exhausted in %.2fs)",
                signal.strategy_name,
                signal.direction,
                market_label,
                ideal_price,
                hybrid["elapsed"],
            )
            await db.log_event(
                "trade_hybrid_no_fill",
                f"Hybrid no fill - {signal.strategy_name} {signal.direction} on {market.market_type} at {ideal_price:.4f} [LOCKED]",
                {
                    "market_id": market.market_id,
                    "market_type": market.market_type,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "locked_entry_price": ideal_price,
                    "locked_shares": locked_shares,
                    "execution_time": round(hybrid["elapsed"], 2),
                    "signal_data": signal_data,
                },
            )
        await db.insert_bot_trade(
            market_id=market.market_id,
            market_type=market.market_type,
            strategy_name=signal.strategy_name,
            direction=signal.direction,
            entry_price=signal.entry_price,
            bet_size_usd=bet_size,
            shares=locked_shares,
            token_id=token_id,
            condition_id=market.market_id,
            status=status,
            order_id=order_id,
            notes=error_notes,
            signal_data=signal_data,
            locked_entry_price=ideal_price,
            locked_shares_count=locked_shares,
            locked_cost=signal.locked_cost,
            locked_balance=signal.locked_balance,
            signal_generated_at=signal.created_at,
        )
        return

    actual_shares = hybrid["fill_shares"]
    actual_price = hybrid["fill_price"]
    actual_cost = actual_shares * actual_price
    price_variance = round(actual_price - ideal_price, 6)
    price_variance_pct = round((price_variance / ideal_price) * 100, 4) if ideal_price > 0 else 0.0
    shares_variance = actual_shares - locked_shares
    signal_age_s = round((datetime.now(timezone.utc) - signal.created_at).total_seconds(), 2)
    _variance_metrics.add_execution(price_variance_pct, shares_variance, signal_age_s)

    log.info(
        "[%s] LOCKED: $%.4f x %dsh = $%.2f | ACTUAL: $%.4f x %dsh = $%.2f | Variance: %+.2f%% (%+dsh) | Age: %.2fs",
        tag,
        ideal_price,
        locked_shares,
        bet_size,
        actual_price,
        actual_shares,
        actual_cost,
        price_variance_pct,
        shares_variance,
        signal_age_s,
    )
    if abs(price_variance_pct) > 1.0:
        log.warning(
            "[%s] High price variance: %+.2f%% (locked: $%.4f, actual: $%.4f)",
            tag,
            price_variance_pct,
            ideal_price,
            actual_price,
        )
    if shares_variance != 0:
        log.warning(
            "[%s] Share variance: %+d shares (locked: %d, actual: %d)",
            tag,
            shares_variance,
            locked_shares,
            actual_shares,
        )

    fill_price_min = float(signal_data.get("price_min", live_config.get("price_min", "0.01")))
    fill_price_max = float(signal_data.get("price_max", live_config.get("price_max", "0.99")))
    stop_loss_price, take_profit_price = _derive_exit_targets(
        locked_entry_price=ideal_price,
        actual_entry_price=actual_price,
        raw_stop_loss=locked_stop_loss,
        raw_take_profit=locked_take_profit,
    )
    log.info(
        "[PROTECTION] Derived exits for %s %s on %s | entry: %.4f | stop: %s | target: %s",
        signal.strategy_name,
        signal.direction,
        market.market_type,
        actual_price,
        f"{stop_loss_price:.4f}" if stop_loss_price is not None else "n/a",
        f"{take_profit_price:.4f}" if take_profit_price is not None else "n/a",
    )
    protection_reasons: list[str] = []
    if actual_price < fill_price_min or actual_price > fill_price_max:
        protection_reasons.append(
            f"fill price {actual_price:.4f} outside [{fill_price_min:.2f}, {fill_price_max:.2f}]"
        )
    if actual_shares < config.MIN_ENTRY_SHARES:
        protection_reasons.append(
            f"filled shares {actual_shares} below minimum entry {config.MIN_ENTRY_SHARES}"
        )
    if actual_cost + 1e-9 < MIN_DOLLAR_SIZE:
        protection_reasons.append(
            f"filled notional ${actual_cost:.2f} below minimum ${MIN_DOLLAR_SIZE:.2f}"
        )
    invalid_exit_reason = _validate_exit_targets(
        actual_entry_price=actual_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
    )
    if invalid_exit_reason:
        protection_reasons.append(invalid_exit_reason)

    protection_notes = "; ".join(protection_reasons) if protection_reasons else None

    log.info(
        "TRADE FILLED - %s %s on %s | %d shares @ %.4f ($%.2f) | stage: %s | slippage: $%.3f | time: %.2fs | order=%s",
        signal.strategy_name,
        signal.direction,
        market_label,
        actual_shares,
        actual_price,
        actual_cost,
        execution_stage,
        hybrid["slippage"],
        hybrid["elapsed"],
        order_id,
    )
    new_balance = await get_usdc_balance()
    await db.log_event(
        "trade_placed",
        f"Placed {signal.direction} on {market.market_type} - strategy: {signal.strategy_name}",
        {
            "market_id": market.market_id,
            "market_type": market.market_type,
            "strategy_name": signal.strategy_name,
            "direction": signal.direction,
            "entry_price": actual_price,
            "locked_entry_price": ideal_price,
            "bet_size_usd": actual_cost,
            "shares": actual_shares,
            "locked_shares": locked_shares,
            "price_variance": price_variance,
            "price_variance_pct": price_variance_pct,
            "shares_variance": shares_variance,
            "signal_age_seconds": signal_age_s,
            "execution_stage": execution_stage,
            "slippage": round(hybrid["slippage"], 4),
            "execution_time": round(hybrid["elapsed"], 2),
            "token_id": token_id,
            "order_id": order_id,
            "balance_after": new_balance if new_balance >= 0 else None,
            "derived_stop_loss_price": stop_loss_price,
            "derived_take_profit_price": take_profit_price,
            "protection_notes": protection_notes,
            "signal_data": signal_data,
        },
    )
    if protection_notes:
        await db.log_event(
            "trade_fill_rejected",
            f"Filled trade requires immediate exit on {market.market_type}: {protection_notes}",
            {
                "market_id": market.market_id,
                "market_type": market.market_type,
                "strategy_name": signal.strategy_name,
                "direction": signal.direction,
                "actual_price": actual_price,
                "locked_price": ideal_price,
                "price_variance": price_variance,
                "price_variance_pct": price_variance_pct,
                "price_min": fill_price_min,
                "price_max": fill_price_max,
                "shares": actual_shares,
                "order_id": order_id,
                "execution_stage": execution_stage,
                "derived_stop_loss_price": stop_loss_price,
                "derived_take_profit_price": take_profit_price,
                "reason": protection_notes,
                "signal_data": signal_data,
            },
        )

    trade_id = await db.insert_bot_trade(
        market_id=market.market_id,
        market_type=market.market_type,
        strategy_name=signal.strategy_name,
        direction=signal.direction,
        entry_price=actual_price,
        bet_size_usd=round(actual_cost, 2),
        shares=actual_shares,
        token_id=token_id,
        condition_id=market.market_id,
        status="filled",
        order_id=order_id,
        notes=protection_notes,
        signal_data=signal_data,
        execution_stage=execution_stage,
        locked_entry_price=ideal_price,
        locked_shares_count=locked_shares,
        locked_cost=signal.locked_cost,
        locked_balance=signal.locked_balance,
        price_variance_val=price_variance,
        price_variance_pct_val=price_variance_pct,
        shares_variance_count=shares_variance,
        signal_generated_at=signal.created_at,
        signal_age_seconds=signal_age_s,
    )

    await db.update_exit_targets(
        trade_id,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
    )

    if protection_notes:
        forced_exit = await force_close_position(
            clob,
            token_id,
            trade_id=trade_id,
            reason=protection_notes,
        )
        if forced_exit:
            await _resolve_forced_exit(
                trade_id=trade_id,
                market=market,
                signal=signal,
                entry_price=actual_price,
                shares=actual_shares,
                exit_fill=forced_exit,
                reason=protection_notes,
            )
        else:
            log.error("[FORCED-EXIT] Failed to close trade %d after protection failure", trade_id)
            await db.log_event(
                "trade_unprotected",
                f"Trade {trade_id} could not be force-closed after protection failure",
                {
                    "trade_id": trade_id,
                    "market_id": market.market_id,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "reason": protection_notes,
                },
            )
        return

    stop_loss_order_id = await place_stop_loss_order(
        clob=clob,
        trade_id=trade_id,
        token_id=token_id,
        shares=actual_shares,
        stop_loss_price=stop_loss_price,
    )
    if stop_loss_order_id is None:
        forced_exit = await force_close_position(
            clob,
            token_id,
            trade_id=trade_id,
            reason="stop-loss order could not be placed",
        )
        if forced_exit:
            await _resolve_forced_exit(
                trade_id=trade_id,
                market=market,
                signal=signal,
                entry_price=actual_price,
                shares=actual_shares,
                exit_fill=forced_exit,
                reason="stop-loss order could not be placed",
            )
        else:
            log.error("[STOP-LOSS] Trade %d remains open without protective stop-loss", trade_id)
            await db.log_event(
                "trade_unprotected",
                f"Trade {trade_id} remains open because stop-loss could not be placed",
                {
                    "trade_id": trade_id,
                    "market_id": market.market_id,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
                },
            )
        return

    log.info(
        "[TAKE-PROFIT] Software-managed take-profit armed for trade %d @ %.4f",
        trade_id,
        take_profit_price,
    )
    await db.log_event(
        "trade_protected",
        f"Trade {trade_id} protected with stop-loss on book and software take-profit",
        {
            "trade_id": trade_id,
            "market_id": market.market_id,
            "strategy_name": signal.strategy_name,
            "direction": signal.direction,
            "stop_loss_order_id": stop_loss_order_id,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
        },
    )
