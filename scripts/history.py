#!/usr/bin/env python3
"""
history.py — Trade History & Performance Stats for Public.com Options Copilot

Fetches trade history and computes performance metrics:
win rate, total P/L, avg win/loss, best/worst trade.

Usage:
    python3 history.py
    python3 history.py --days 60
    python3 history.py --days 7 --show-all
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import sys
import argparse
from datetime import datetime, timedelta

# ── Auth from environment ──────────────────────────────────────────────────────
API_SECRET = os.environ.get('PUBLIC_COM_SECRET', '')
ACCOUNT_ID = os.environ.get('PUBLIC_COM_ACCOUNT_ID', '')

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


def is_option_symbol(symbol: str) -> bool:
    return len(symbol) > 10 and any(c.isdigit() for c in symbol[6:])


def parse_trade_date(raw_date) -> datetime | None:
    """Parse various date formats from the API."""
    if not raw_date:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(raw_date)[:26], fmt)
        except ValueError:
            continue
    return None


def fetch_history(days: int) -> list:
    """Fetch trade history for the past N days."""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        resp = client.get_history(start_date=start_date, end_date=end_date)

        trades = []
        if isinstance(resp, dict):
            trades = resp.get('trades', resp.get('history', resp.get('orders', [])))
        elif isinstance(resp, list):
            trades = resp
        else:
            trades = getattr(resp, 'trades', None) or getattr(resp, 'history', []) or []

        return trades
    except Exception as e:
        print(f"  [error] get_history: {e}")
        return []


def parse_trade(trade) -> dict | None:
    """Parse a raw trade into a normalised dict."""
    try:
        symbol = get_attr(trade, 'symbol', 'ticker', default='')
        side = (get_attr(trade, 'side', 'action', 'orderSide', default='') or '').upper()
        qty = safe_float(get_attr(trade, 'quantity', 'qty', 'filledQuantity', default=0))
        price = safe_float(get_attr(trade, 'price', 'averageFillPrice', 'fillPrice', 'avgFillPrice', default=0))
        status = (get_attr(trade, 'status', 'orderStatus', default='') or '').upper()
        raw_date = get_attr(trade, 'timestamp', 'createdAt', 'date', 'executedAt', default=None)
        trade_date = parse_trade_date(raw_date)
        order_id = get_attr(trade, 'orderId', 'id', default='')

        # Only count filled trades
        if status not in ('FILLED', 'PARTIALLY_FILLED', ''):
            return None
        if qty <= 0 or price <= 0:
            return None

        return {
            'order_id': order_id,
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'price': price,
            'status': status,
            'date': trade_date,
            'is_option': is_option_symbol(symbol),
        }
    except Exception:
        return None


def match_trades(trades: list) -> list:
    """
    Pair BUY and SELL trades by symbol to compute P/L per round-trip.
    Returns list of completed trade pairs.
    """
    # Group by symbol
    by_symbol: dict[str, list] = {}
    for t in trades:
        sym = t['symbol']
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(t)

    completed = []
    for sym, sym_trades in by_symbol.items():
        buys = sorted([t for t in sym_trades if t['side'] in ('BUY', 'B')], key=lambda x: x['date'] or datetime.min)
        sells = sorted([t for t in sym_trades if t['side'] in ('SELL', 'S')], key=lambda x: x['date'] or datetime.min)

        # Match buys to sells (FIFO)
        while buys and sells:
            buy = buys.pop(0)
            sell = sells.pop(0)
            matched_qty = min(buy['qty'], sell['qty'])
            pnl = (sell['price'] - buy['price']) * matched_qty
            if buy.get('is_option'):
                pnl *= 100  # options = 100 shares per contract

            completed.append({
                'symbol': sym,
                'buy_date': buy['date'],
                'sell_date': sell['date'],
                'buy_price': buy['price'],
                'sell_price': sell['price'],
                'qty': matched_qty,
                'pnl': pnl,
                'is_option': buy.get('is_option', False),
                'pnl_pct': (sell['price'] - buy['price']) / buy['price'] if buy['price'] else 0,
            })

    return completed


def compute_stats(trades: list) -> dict:
    """Compute aggregate performance statistics."""
    if not trades:
        return {}

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]

    total_pnl = sum(t['pnl'] for t in trades)
    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
    best = max(trades, key=lambda t: t['pnl']) if trades else None
    worst = min(trades, key=lambda t: t['pnl']) if trades else None
    profit_factor = abs(sum(t['pnl'] for t in wins)) / abs(sum(t['pnl'] for t in losses) or 1)

    return {
        'total_trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'best': best,
        'worst': worst,
    }


def color_pnl(pnl: float) -> str:
    sign = "+" if pnl >= 0 else ""
    color = "\033[92m" if pnl >= 0 else "\033[91m"
    return f"{color}{sign}${pnl:.2f}\033[0m"


def color_pct(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    color = "\033[92m" if pct >= 0 else "\033[91m"
    return f"{color}{sign}{pct:.1%}\033[0m"


def main():
    parser = argparse.ArgumentParser(
        description="Trade history and performance statistics"
    )
    parser.add_argument('--days', type=int, default=30,
                        help='Lookback period in days (default: 30)')
    parser.add_argument('--show-all', action='store_true',
                        help='Show all trades including equities (default: options only)')
    parser.add_argument('--raw', action='store_true',
                        help='Show raw order list (no pairing)')
    args = parser.parse_args()

    print(f"\n📈 Options Copilot — Trade History & Performance")
    print(f"   Account: {ACCOUNT_ID or '(default)'}")
    print(f"   Period:  Last {args.days} days")
    print(f"   Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ── Fetch history ──────────────────────────────────────────────────────────
    print("  Fetching trade history...")
    raw_trades = fetch_history(args.days)
    print(f"  Found {len(raw_trades)} raw order(s)")

    if not raw_trades:
        print("\n  No trades found for this period.\n")
        return

    # ── Parse trades ───────────────────────────────────────────────────────────
    parsed = [t for t in [parse_trade(r) for r in raw_trades] if t]

    if not args.show_all:
        parsed = [t for t in parsed if t.get('is_option')]
        print(f"  {len(parsed)} option trade(s) (use --show-all to include equities)")

    if not parsed:
        print("\n  No trades to display after filtering.\n")
        return

    # ── Raw mode: just list orders ─────────────────────────────────────────────
    if args.raw:
        print(f"\n  {'Date':<20}  {'Side':<4}  {'Symbol':<24}  {'Qty':>4}  {'Price':>7}  {'Type'}")
        print("  " + "─" * 75)
        for t in sorted(parsed, key=lambda x: x['date'] or datetime.min, reverse=True):
            date_str = t['date'].strftime("%Y-%m-%d %H:%M") if t['date'] else "unknown"
            type_flag = "opt" if t['is_option'] else "eq "
            print(
                f"  {date_str:<20}  {t['side']:<4}  {t['symbol']:<24}  "
                f"{t['qty']:>4.0f}  ${t['price']:>6.2f}  {type_flag}"
            )
        print()
        return

    # ── Match round-trip trades ────────────────────────────────────────────────
    completed = match_trades(parsed)
    completed.sort(key=lambda x: x.get('sell_date') or datetime.min, reverse=True)

    if completed:
        print(f"\n  📋 COMPLETED TRADES ({len(completed)})")
        print(f"  {'Date':<12}  {'Symbol':<24}  {'Qty':>3}  {'Buy':>6}  {'Sell':>6}  {'P/L':>10}  {'P/L%':>8}")
        print("  " + "─" * 80)
        for t in completed:
            date_str = t['sell_date'].strftime("%Y-%m-%d") if t['sell_date'] else "open"
            pnl_str = color_pnl(t['pnl'])
            pct_str = color_pct(t['pnl_pct'])
            print(
                f"  {date_str:<12}  {t['symbol']:<24}  {t['qty']:>3.0f}  "
                f"${t['buy_price']:>5.2f}  ${t['sell_price']:>5.2f}  "
                f"{pnl_str:>10}  {pct_str}"
            )

    # ── Performance stats ──────────────────────────────────────────────────────
    if completed:
        stats = compute_stats(completed)

        total_color = "\033[92m" if stats['total_pnl'] >= 0 else "\033[91m"
        reset = "\033[0m"

        print(f"""
  ╔══════════════════════════════════════════════════╗
  ║         PERFORMANCE SUMMARY ({args.days}d)              ║
  ╠══════════════════════════════════════════════════╣
  ║  Total Trades:    {stats['total_trades']:<31}║
  ║  Wins / Losses:   {stats['wins']} / {stats['losses']:<27}║
  ║  Win Rate:        {stats['win_rate']:.1%:<30}║
  ╠══════════════════════════════════════════════════╣
  ║  Total P/L:       {total_color}{'+' if stats['total_pnl'] >= 0 else ''}${stats['total_pnl']:.2f}{reset:<29}║
  ║  Avg Win:         +${stats['avg_win']:.2f}{'':<29}║
  ║  Avg Loss:        ${stats['avg_loss']:.2f}{'':<29}║
  ║  Profit Factor:   {stats['profit_factor']:.2f}x{'':<29}║""")

        if stats['best']:
            b = stats['best']
            date_str = b['sell_date'].strftime("%Y-%m-%d") if b.get('sell_date') else "?"
            print(f"  ╠══════════════════════════════════════════════════╣")
            print(f"  ║  Best Trade:      {b['symbol']} +${b['pnl']:.2f} ({date_str}){'':<5}║")
        if stats['worst']:
            w = stats['worst']
            date_str = w['sell_date'].strftime("%Y-%m-%d") if w.get('sell_date') else "?"
            print(f"  ║  Worst Trade:     {w['symbol']} ${w['pnl']:.2f} ({date_str}){'':<5}║")

        print(f"  ╚══════════════════════════════════════════════════╝")

    else:
        print("\n  No completed round-trip trades found.")
        print("  (Open positions or unmatched orders aren't included in P/L calculation)")
        print(f"\n  Raw orders: {len(parsed)} | Use --raw to see all orders\n")


if __name__ == '__main__':
    main()
