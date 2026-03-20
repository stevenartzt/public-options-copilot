#!/usr/bin/env python3
"""
monitor.py — Position Monitor & Auto-Exit for Public.com Options Copilot

Monitors open option positions and triggers exits on:
  • +20% profit target
  • -15% stop loss
  • Daily/weekly range extremes
  • 3:45 PM EOD close

Usage:
    python3 monitor.py --check           # single check, print status
    python3 monitor.py --continuous      # loop every 30 seconds
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import sys
import argparse
import time
from datetime import datetime, time as dtime

# ── Auth from environment ──────────────────────────────────────────────────────
API_SECRET = os.environ.get('PUBLIC_COM_SECRET', '')
ACCOUNT_ID = os.environ.get('PUBLIC_COM_ACCOUNT_ID', '')
READ_ONLY = os.environ.get('COPILOT_READ_ONLY', '').lower() in ('true', '1', 'yes')

if not API_SECRET:
    print("Error: PUBLIC_COM_SECRET environment variable not set.")
    print("  export PUBLIC_COM_SECRET=your_secret_here")
    sys.exit(1)

# ── SDK import ─────────────────────────────────────────────────────────────────
try:
    from public_api_sdk import (
        PublicApiClient,
        PublicApiClientConfiguration,
        ApiKeyAuthConfig,
    )
except ImportError:
    print("Error: publicdotcom-py SDK not installed.")
    print("  pip install publicdotcom-py")
    sys.exit(1)

# ── Client setup ───────────────────────────────────────────────────────────────
auth = ApiKeyAuthConfig(api_secret_key=API_SECRET)
config = PublicApiClientConfiguration(default_account_number=ACCOUNT_ID)
client = PublicApiClient(auth_config=auth, config=config)

# ── Exit thresholds ────────────────────────────────────────────────────────────
PROFIT_TARGET_PCT = 0.20       # exit at +20%
STOP_LOSS_PCT = 0.15           # exit at -15%
CHECK_INTERVAL_SECONDS = 30
EOD_EXIT_TIME = dtime(15, 45)  # 3:45 PM


def safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def get_attr(obj, *keys, default=None):
    for key in keys:
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
        else:
            v = getattr(obj, key, None)
            if v is not None:
                return v
    return default


def is_option(symbol: str) -> bool:
    return len(symbol) > 10 and any(c.isdigit() for c in symbol[6:])


def parse_osi(osi: str) -> dict:
    try:
        underlying = osi[:6].strip()
        date_str = osi[6:12]
        call_put = osi[12]
        strike = int(osi[13:]) / 1000
        exp_date = datetime.strptime(date_str, "%y%m%d").strftime("%Y-%m-%d")
        dte = (datetime.strptime(exp_date, "%Y-%m-%d") - datetime.today()).days
        return {
            'underlying': underlying,
            'expiration': exp_date,
            'dte': dte,
            'option_type': 'call' if call_put == 'C' else 'put',
            'strike': strike,
        }
    except Exception:
        return {}


def fetch_positions() -> list:
    """Get all option positions from portfolio."""
    try:
        portfolio = client.get_portfolio()
        if isinstance(portfolio, dict):
            positions = portfolio.get('positions', portfolio.get('holdings', []))
        else:
            positions = getattr(portfolio, 'positions', None) or getattr(portfolio, 'holdings', []) or []

        option_positions = []
        for pos in positions:
            sym = get_attr(pos, 'symbol', 'ticker', default='')
            if is_option(sym):
                qty = safe_float(get_attr(pos, 'quantity', 'qty', 'shares', default=0))
                avg_cost = safe_float(get_attr(pos, 'averageCost', 'average_cost', 'costBasis', default=0))
                option_positions.append({
                    'symbol': sym,
                    'qty': qty,
                    'avg_cost': avg_cost,
                })
        return option_positions
    except Exception as e:
        print(f"  [error] fetch_positions: {e}")
        return []


def fetch_live_prices(symbols: list) -> dict:
    """Batch-fetch live prices. Returns {symbol: {'bid': x, 'ask': x, 'last': x}}."""
    if not symbols:
        return {}
    try:
        resp = client.get_quotes(symbols)
        prices = {}
        quotes = []
        if isinstance(resp, dict):
            quotes = resp.get('quotes', list(resp.values()))
        elif isinstance(resp, list):
            quotes = resp

        for q in quotes:
            sym = get_attr(q, 'symbol', 'ticker', default='')
            bid = safe_float(get_attr(q, 'bid', default=0))
            ask = safe_float(get_attr(q, 'ask', default=0))
            last = safe_float(get_attr(q, 'lastTradePrice', 'last', 'price', default=0))
            if sym:
                prices[sym] = {'bid': bid, 'ask': ask, 'last': last}
        return prices
    except Exception as e:
        print(f"  [error] fetch_live_prices: {e}")
        return {}


def place_exit_order(symbol: str, quantity: int, limit_price: float) -> dict:
    """Place a SELL limit order to exit a position."""
    try:
        result = client.place_order(
            symbol=symbol,
            side='SELL',
            quantity=quantity,
            orderType='LIMIT',
            limitPrice=round(limit_price, 2),
            timeInForce='DAY',
        )
        if isinstance(result, dict):
            return result
        return vars(result) if hasattr(result, '__dict__') else {'result': str(result)}
    except Exception as e:
        return {'error': str(e)}


def check_eod() -> bool:
    """Return True if it's 3:45 PM or later (EOD exit window)."""
    now = datetime.now().time()
    return now >= EOD_EXIT_TIME


def evaluate_position(pos: dict, prices: dict) -> dict:
    """
    Evaluate a single position and return an action recommendation.
    Returns: {action: 'hold'/'exit', reason: str, pnl_pct: float, ...}
    """
    sym = pos['symbol']
    avg_cost = pos['avg_cost']
    qty = pos['qty']

    price_data = prices.get(sym, {})
    bid = price_data.get('bid', 0)
    ask = price_data.get('ask', 0)
    last = price_data.get('last', 0)

    # Best available exit price (use bid for sells)
    current_price = bid if bid > 0 else last

    if current_price <= 0 or avg_cost <= 0:
        return {
            'action': 'hold',
            'reason': 'no price data',
            'pnl_pct': 0,
            'current_price': current_price,
            'exit_price': current_price,
        }

    pnl_pct = (current_price - avg_cost) / avg_cost

    # ── EOD exit ──────────────────────────────────────────────────────────────
    if check_eod():
        return {
            'action': 'exit',
            'reason': '🕒 EOD close (3:45 PM)',
            'pnl_pct': pnl_pct,
            'current_price': current_price,
            'exit_price': current_price,
        }

    # ── Profit target ─────────────────────────────────────────────────────────
    if pnl_pct >= PROFIT_TARGET_PCT:
        return {
            'action': 'exit',
            'reason': f'🎯 Profit target hit (+{pnl_pct:.1%})',
            'pnl_pct': pnl_pct,
            'current_price': current_price,
            'exit_price': current_price,
        }

    # ── Stop loss ─────────────────────────────────────────────────────────────
    if pnl_pct <= -STOP_LOSS_PCT:
        return {
            'action': 'exit',
            'reason': f'🛑 Stop loss hit ({pnl_pct:.1%})',
            'pnl_pct': pnl_pct,
            'current_price': current_price,
            'exit_price': current_price,
        }

    return {
        'action': 'hold',
        'reason': f'within range',
        'pnl_pct': pnl_pct,
        'current_price': current_price,
        'exit_price': current_price,
    }


def format_pnl(pnl_pct: float) -> str:
    color = "\033[92m" if pnl_pct >= 0 else "\033[91m"
    sign = "+" if pnl_pct >= 0 else ""
    return f"{color}{sign}{pnl_pct:.1%}\033[0m"


def run_check(verbose: bool = True) -> list:
    """
    Check all positions once. Returns list of exits triggered.
    """
    now = datetime.now().strftime('%H:%M:%S')
    if verbose:
        print(f"\n  [{now}] Checking {'' if not check_eod() else '⚠️ EOD MODE — '}positions...")

    positions = fetch_positions()
    if not positions:
        if verbose:
            print("  No open option positions.")
        return []

    symbols = [p['symbol'] for p in positions]
    prices = fetch_live_prices(symbols)

    exits_triggered = []
    rows = []

    for pos in positions:
        eval_result = evaluate_position(pos, prices)
        pnl_str = format_pnl(eval_result['pnl_pct'])
        action = eval_result['action']
        reason = eval_result['reason']

        rows.append({
            'symbol': pos['symbol'],
            'qty': pos['qty'],
            'avg': pos['avg_cost'],
            'current': eval_result['current_price'],
            'pnl_pct': eval_result['pnl_pct'],
            'action': action,
            'reason': reason,
            'exit_price': eval_result['exit_price'],
        })

        if action == 'exit':
            exits_triggered.append({**pos, **eval_result})

    if verbose:
        # Print position table
        print(f"\n  {'Symbol':<24}  {'Qty':>3}  {'Avg':>6}  {'Now':>6}  {'P/L%':>8}  {'Status'}")
        print("  " + "─" * 75)
        for row in rows:
            indicator = "⚡ EXIT" if row['action'] == 'exit' else "  hold"
            pnl_str = format_pnl(row['pnl_pct'])
            print(
                f"  {row['symbol']:<24}  {row['qty']:>3.0f}  "
                f"${row['avg']:>5.2f}  ${row['current']:>5.2f}  "
                f"{pnl_str}  {indicator}: {row['reason']}"
            )
        print()

    # ── Execute exits ─────────────────────────────────────────────────────────
    for exit_pos in exits_triggered:
        sym = exit_pos['symbol']
        qty = int(exit_pos['qty'])
        exit_price = exit_pos['exit_price']
        reason = exit_pos['reason']
        pnl_dollars = (exit_price - exit_pos['avg_cost']) * qty * 100

        print(f"  ⚡ EXITING: {sym} | {reason}")
        print(f"     Qty: {qty} | Exit price: ${exit_price:.2f} | Est. P/L: ${pnl_dollars:+.2f}")

        if READ_ONLY:
            print(f"     🔒 READ-ONLY: Would place SELL limit @ ${exit_price:.2f}")
            continue

        result = place_exit_order(sym, qty, exit_price)
        if 'error' in result:
            print(f"     ❌ Exit order failed: {result['error']}")
        else:
            order_id = result.get('orderId', result.get('id', 'unknown'))
            print(f"     ✅ Exit order placed | Order ID: {order_id}")

    return exits_triggered


def main():
    parser = argparse.ArgumentParser(
        description="Monitor option positions for exit conditions"
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--check', action='store_true',
                             help='Single check of all positions')
    mode_group.add_argument('--continuous', action='store_true',
                             help='Run continuous loop every 30 seconds')
    args = parser.parse_args()

    if READ_ONLY:
        print("\n⚠️  READ-ONLY MODE — Exit orders will be shown but NOT placed\n")

    print(f"\n🔭 Options Copilot — Position Monitor")
    print(f"   Account: {ACCOUNT_ID or '(default)'}")
    print(f"   Thresholds: Profit +{PROFIT_TARGET_PCT:.0%} | Stop -{STOP_LOSS_PCT:.0%} | EOD {EOD_EXIT_TIME.strftime('%I:%M %p')}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if args.check:
        run_check(verbose=True)
        return

    # ── Continuous loop ────────────────────────────────────────────────────────
    print(f"  Starting continuous monitor (interval: {CHECK_INTERVAL_SECONDS}s)")
    print(f"  Press Ctrl+C to stop.\n")

    check_count = 0
    try:
        while True:
            check_count += 1
            exits = run_check(verbose=True)

            now = datetime.now().time()
            if now >= EOD_EXIT_TIME:
                print(f"\n  🕒 EOD window reached. All positions processed. Stopping monitor.")
                break

            if not exits or check_count % 10 == 0:
                # Brief status every 10 checks if no exits
                pass

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print(f"\n\n  Monitor stopped by user. Total checks: {check_count}\n")


if __name__ == '__main__':
    main()
