#!/usr/bin/env python3
"""
portfolio.py — Portfolio Viewer for Public.com Options Copilot

Shows current positions with real-time P/L and Greeks exposure.

Usage:
    python3 portfolio.py
    python3 portfolio.py --account-id 5OG12345
"""

import os
import sys
import argparse
from datetime import datetime

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


def make_client(account_id: str) -> PublicApiClient:
    auth = ApiKeyAuthConfig(api_secret_key=API_SECRET)
    config = PublicApiClientConfiguration(default_account_number=account_id)
    return PublicApiClient(auth_config=auth, config=config)


# ── Helpers ────────────────────────────────────────────────────────────────────

def safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def get_attr(obj, *keys, default=None):
    """Get attribute from object or dict, trying multiple key names."""
    for key in keys:
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
        else:
            val = getattr(obj, key, None)
            if val is not None:
                return val
    return default


def is_option(symbol: str) -> bool:
    """Heuristic: OSI symbols are 15+ chars or contain a date pattern."""
    return len(symbol) > 10 and any(c.isdigit() for c in symbol[6:])


def parse_osi(osi: str) -> dict:
    """Parse an OSI option symbol into components."""
    try:
        # OSI format: AAPL  260327C00150000
        # First 6 chars: underlying (right-padded with spaces)
        underlying = osi[:6].strip()
        date_str = osi[6:12]
        call_put = osi[12]
        strike_raw = osi[13:]
        strike = int(strike_raw) / 1000
        exp_date = datetime.strptime(date_str, "%y%m%d").strftime("%Y-%m-%d")
        today = datetime.today()
        dte = (datetime.strptime(exp_date, "%Y-%m-%d") - today).days
        return {
            'underlying': underlying,
            'expiration': exp_date,
            'dte': dte,
            'option_type': 'call' if call_put == 'C' else 'put',
            'strike': strike,
        }
    except Exception:
        return {}


def color_pnl(pnl: float) -> str:
    """Return colored P/L string (ANSI)."""
    sign = "+" if pnl >= 0 else ""
    colored = f"\033[92m{sign}${pnl:.2f}\033[0m" if pnl >= 0 else f"\033[91m${pnl:.2f}\033[0m"
    return colored


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Show portfolio with real-time P/L and Greeks exposure"
    )
    parser.add_argument(
        '--account-id',
        help='Account ID (overrides PUBLIC_COM_ACCOUNT_ID env var)'
    )
    parser.add_argument(
        '--no-greeks', action='store_true',
        help='Skip fetching Greeks (faster)'
    )
    args = parser.parse_args()

    account_id = args.account_id or ACCOUNT_ID
    client = make_client(account_id)

    print(f"\n📊 Public.com Options Copilot — Portfolio")
    print(f"   Account: {account_id or '(default)'}")
    print(f"   Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ── Fetch portfolio ────────────────────────────────────────────────────────
    try:
        portfolio = client.get_portfolio()
    except Exception as e:
        print(f"Error fetching portfolio: {e}")
        sys.exit(1)

    # Extract positions list
    positions = []
    if isinstance(portfolio, dict):
        positions = portfolio.get('positions', portfolio.get('holdings', []))
        buying_power = safe_float(portfolio.get('buyingPower', portfolio.get('buying_power', 0)))
        portfolio_value = safe_float(portfolio.get('portfolioValue', portfolio.get('portfolio_value', portfolio.get('totalValue', 0))))
        cash = safe_float(portfolio.get('cashBalance', portfolio.get('cash', 0)))
    else:
        positions = getattr(portfolio, 'positions', None) or getattr(portfolio, 'holdings', []) or []
        buying_power = safe_float(get_attr(portfolio, 'buyingPower', 'buying_power', default=0))
        portfolio_value = safe_float(get_attr(portfolio, 'portfolioValue', 'portfolio_value', 'totalValue', default=0))
        cash = safe_float(get_attr(portfolio, 'cashBalance', 'cash', default=0))

    print(f"  💰 Portfolio Value: ${portfolio_value:,.2f}")
    print(f"  💵 Buying Power:    ${buying_power:,.2f}")
    print(f"  🏦 Cash Balance:    ${cash:,.2f}\n")

    if not positions:
        print("  No open positions found.\n")
        return

    # ── Collect all symbols for a batch quote call ─────────────────────────────
    all_symbols = []
    parsed_positions = []
    for pos in positions:
        sym = get_attr(pos, 'symbol', 'ticker', default='')
        qty = safe_float(get_attr(pos, 'quantity', 'qty', 'shares', default=0))
        avg_cost = safe_float(get_attr(pos, 'averageCost', 'average_cost', 'costBasis', 'cost_basis', default=0))
        market_val = safe_float(get_attr(pos, 'marketValue', 'market_value', 'currentValue', default=0))
        unrealized = safe_float(get_attr(pos, 'unrealizedPnl', 'unrealized_pnl', 'unrealizedGainLoss', default=0))
        parsed_positions.append({
            'symbol': sym,
            'qty': qty,
            'avg_cost': avg_cost,
            'market_val': market_val,
            'unrealized': unrealized,
        })
        if sym:
            all_symbols.append(sym)

    # ── Batch quote fetch ──────────────────────────────────────────────────────
    live_prices = {}
    if all_symbols:
        try:
            quotes_resp = client.get_quotes(all_symbols)
            quotes = []
            if isinstance(quotes_resp, dict):
                quotes = quotes_resp.get('quotes', list(quotes_resp.values()))
            elif isinstance(quotes_resp, list):
                quotes = quotes_resp
            for q in quotes:
                qsym = get_attr(q, 'symbol', 'ticker', default='')
                last = safe_float(get_attr(q, 'lastTradePrice', 'last', 'price', default=0))
                bid = safe_float(get_attr(q, 'bid', default=0))
                ask = safe_float(get_attr(q, 'ask', default=0))
                if qsym:
                    live_prices[qsym] = {'last': last, 'bid': bid, 'ask': ask}
        except Exception as e:
            print(f"  [warn] Could not fetch live prices: {e}")

    # ── Print positions table ──────────────────────────────────────────────────
    options_positions = []
    equity_positions = []

    for pos in parsed_positions:
        if is_option(pos['symbol']):
            options_positions.append(pos)
        else:
            equity_positions.append(pos)

    total_unrealized = 0.0
    total_day_pnl = 0.0

    # ── Equity Positions ───────────────────────────────────────────────────────
    if equity_positions:
        print("  📈 EQUITIES")
        print(f"  {'Symbol':<8}  {'Qty':>6}  {'Avg Cost':>9}  {'Last':>8}  {'Mkt Val':>10}  {'Unreal P/L':>12}")
        print("  " + "─" * 72)
        for pos in equity_positions:
            sym = pos['symbol']
            live = live_prices.get(sym, {})
            live_last = live.get('last', 0) or pos['avg_cost']
            live_mkt_val = live_last * pos['qty']
            live_unreal = (live_last - pos['avg_cost']) * pos['qty']
            total_unrealized += live_unreal
            pnl_str = color_pnl(live_unreal)
            print(
                f"  {sym:<8}  {pos['qty']:>6.0f}  ${pos['avg_cost']:>8.2f}  "
                f"${live_last:>7.2f}  ${live_mkt_val:>9.2f}  {pnl_str}"
            )
        print()

    # ── Options Positions ──────────────────────────────────────────────────────
    if options_positions:
        print("  🎯 OPTIONS")
        print(f"  {'OSI Symbol':<24}  {'Qty':>4}  {'Avg':>6}  {'Last':>6}  {'P/L':>10}  {'Delta':>6}  {'IV%':>5}  {'Theta':>7}  {'DTE':>3}")
        print("  " + "─" * 90)

        total_delta = 0.0
        total_theta = 0.0

        for pos in options_positions:
            sym = pos['symbol']
            osi_info = parse_osi(sym)

            live = live_prices.get(sym, {})
            live_last = live.get('last', 0) or (pos['market_val'] / (pos['qty'] * 100) if pos['qty'] else 0)
            live_unreal = (live_last - pos['avg_cost']) * pos['qty'] * 100
            pnl_str = color_pnl(live_unreal)
            total_unrealized += live_unreal

            # Fetch Greeks
            delta, iv, theta, gamma = 0.0, 0.0, 0.0, 0.0
            if not args.no_greeks:
                try:
                    greeks_resp = client.get_option_greeks(sym)
                    if isinstance(greeks_resp, dict):
                        delta = safe_float(greeks_resp.get('delta', 0))
                        iv = safe_float(greeks_resp.get('impliedVolatility', greeks_resp.get('iv', 0)))
                        theta = safe_float(greeks_resp.get('theta', 0))
                        gamma = safe_float(greeks_resp.get('gamma', 0))
                    else:
                        delta = safe_float(get_attr(greeks_resp, 'delta', default=0))
                        iv = safe_float(get_attr(greeks_resp, 'impliedVolatility', 'iv', default=0))
                        theta = safe_float(get_attr(greeks_resp, 'theta', default=0))
                except Exception:
                    pass

            total_delta += delta * pos['qty'] * 100
            total_theta += theta * pos['qty'] * 100

            dte_str = f"{osi_info.get('dte', '?')}d" if osi_info else "?"
            iv_pct = f"{iv * 100:.1f}%" if iv else "   -"

            print(
                f"  {sym:<24}  {pos['qty']:>4.0f}  ${pos['avg_cost']:>5.2f}  "
                f"${live_last:>5.2f}  {pnl_str:>10}  "
                f"{delta:>6.3f}  {iv_pct:>5}  ${theta:>6.3f}  {dte_str:>3}"
            )

        print("  " + "─" * 90)
        print(f"  {'Greeks Exposure:':<30}  Δ-dollars: ${total_delta:,.0f}   θ/day: ${total_theta:.2f}")
        print()

    # ── Summary ────────────────────────────────────────────────────────────────
    pnl_symbol = "+" if total_unrealized >= 0 else ""
    color = "\033[92m" if total_unrealized >= 0 else "\033[91m"
    reset = "\033[0m"
    print(f"  {'─' * 50}")
    print(f"  Total Unrealized P/L:  {color}{pnl_symbol}${total_unrealized:,.2f}{reset}")
    print(f"  Open Positions:        {len(positions)}")
    if options_positions:
        print(f"  Options Positions:     {len(options_positions)}")
    print()


if __name__ == '__main__':
    main()
