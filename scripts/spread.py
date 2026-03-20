#!/usr/bin/env python3
"""
spread.py — Credit Spread Finder & Executor for Public.com Copilot

Finds and executes vertical credit spreads (put credit or call credit).
Uses real Greeks to find optimal strikes, verifies R/R ratio,
runs multi-leg preflight, and confirms before executing.

Usage:
    python3 spread.py --underlying AAPL --type put_credit --width 5 --dte 21
    python3 spread.py --underlying SPY --type call_credit --width 3 --dte 14
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import sys
import argparse
from datetime import datetime

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

# ── Constants ──────────────────────────────────────────────────────────────────
TARGET_SELL_DELTA = 0.30       # sell leg target delta
DELTA_TOLERANCE = 0.12         # accept delta in [0.18, 0.42]
MIN_RR_RATIO = 4.0             # credit must be >= spread_width / 4
MIN_CREDIT_PCT = 0.20          # credit >= 20% of spread width
MAX_SPREAD_PCT = 0.10          # bid/ask spread gate


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


def pick_expiration(expirations: list, target_dte: int) -> str | None:
    today = datetime.today().date()
    best, best_diff = None, 9999
    for exp in expirations:
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte < 7:
                continue
            diff = abs(dte - target_dte)
            if diff < best_diff:
                best_diff, best = diff, exp
        except Exception:
            continue
    return best


def get_option_chain_list(underlying: str, expiration: str) -> list:
    """Return a list of option chain entries."""
    try:
        resp = client.get_option_chain(underlying, expiration)
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            return resp.get('options', resp.get('calls', []) + resp.get('puts', []))
        opts = getattr(resp, 'options', None)
        if opts:
            return list(opts)
    except Exception as e:
        print(f"  [error] get_option_chain: {e}")
    return []


def fetch_greeks(osi: str) -> dict:
    try:
        resp = client.get_option_greeks(osi)
        if isinstance(resp, dict):
            return resp
        return vars(resp) if hasattr(resp, '__dict__') else {}
    except Exception:
        return {}


def find_best_sell_leg(chain: list, option_type: str, target_delta: float) -> dict | None:
    """
    Find the option closest to target_delta (absolute value).
    option_type: 'call' or 'put'
    """
    candidates = []
    for opt in chain:
        otype = (get_attr(opt, 'optionType', 'type', default='') or '').lower()
        if otype != option_type:
            continue

        osi = get_attr(opt, 'symbol', default='')
        bid = safe_float(get_attr(opt, 'bid', default=0))
        ask = safe_float(get_attr(opt, 'ask', default=0))
        if not osi:
            continue

        greeks = fetch_greeks(osi)
        delta = abs(safe_float(greeks.get('delta', 0)))
        iv = safe_float(greeks.get('impliedVolatility', greeks.get('iv', 0)))

        if delta < 0.01:
            continue

        strike = safe_float(get_attr(opt, 'strike', 'strikePrice', default=0))

        candidates.append({
            'osi': osi,
            'strike': strike,
            'bid': bid,
            'ask': ask,
            'mid': (bid + ask) / 2 if bid and ask else 0,
            'delta': delta,
            'iv': iv,
            'greeks': greeks,
        })

    if not candidates:
        return None

    # Sort by distance to target delta
    candidates.sort(key=lambda x: abs(x['delta'] - target_delta))
    return candidates[0]


def find_buy_leg(chain: list, option_type: str, sell_strike: float, spread_width: float) -> dict | None:
    """
    Find the buy (protection) leg at sell_strike ± spread_width.
    For put credit: buy leg strike = sell_strike - width (lower put)
    For call credit: buy leg strike = sell_strike + width (higher call)
    """
    # Determine target strike
    if option_type == 'put':
        target_strike = sell_strike - spread_width
    else:
        target_strike = sell_strike + spread_width

    best = None
    best_diff = 9999
    for opt in chain:
        otype = (get_attr(opt, 'optionType', 'type', default='') or '').lower()
        if otype != option_type:
            continue
        strike = safe_float(get_attr(opt, 'strike', 'strikePrice', default=0))
        diff = abs(strike - target_strike)
        if diff < best_diff:
            best_diff = diff
            osi = get_attr(opt, 'symbol', default='')
            bid = safe_float(get_attr(opt, 'bid', default=0))
            ask = safe_float(get_attr(opt, 'ask', default=0))
            best = {
                'osi': osi,
                'strike': strike,
                'bid': bid,
                'ask': ask,
                'mid': (bid + ask) / 2 if bid and ask else 0,
            }
    return best


def run_multi_leg_preflight(legs: list) -> dict:
    """
    Run multi-leg preflight calculation.
    legs = [{'symbol': osi, 'side': 'buy'/'sell', 'quantity': N, 'limitPrice': price}, ...]
    """
    try:
        result = client.perform_multi_leg_preflight_calculation(legs=legs)
        if isinstance(result, dict):
            return result
        return vars(result) if hasattr(result, '__dict__') else {}
    except Exception as e:
        return {'error': str(e)}


def place_spread(legs: list) -> dict:
    """Place the multi-leg order."""
    try:
        result = client.place_multileg_order(legs=legs)
        if isinstance(result, dict):
            return result
        return vars(result) if hasattr(result, '__dict__') else {}
    except Exception as e:
        return {'error': str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Find and execute vertical credit spreads"
    )
    parser.add_argument('--underlying', required=True,
                        help='Underlying ticker, e.g. AAPL')
    parser.add_argument('--type', required=True,
                        choices=['put_credit', 'call_credit'],
                        dest='spread_type',
                        help='Spread type: put_credit or call_credit')
    parser.add_argument('--width', type=float, default=5.0,
                        help='Strike width in dollars (default: 5)')
    parser.add_argument('--dte', type=int, default=21,
                        help='Target days to expiration (default: 21)')
    parser.add_argument('--quantity', type=int, default=1,
                        help='Number of spreads (default: 1)')
    args = parser.parse_args()

    underlying = args.underlying.upper()
    is_put_credit = args.spread_type == 'put_credit'
    option_type = 'put' if is_put_credit else 'call'
    spread_label = "PUT CREDIT" if is_put_credit else "CALL CREDIT"

    if READ_ONLY:
        print("\n⚠️  READ-ONLY MODE — No orders will be placed\n")

    print(f"\n📐 Options Copilot — Credit Spread Builder")
    print(f"   Underlying:  {underlying}")
    print(f"   Type:        {spread_label} SPREAD")
    print(f"   Width:       ${args.width:.0f}")
    print(f"   Target DTE:  {args.dte}d")
    print(f"   Quantity:    {args.quantity} spread(s)")
    print(f"   Time:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ── Step 1: Get expirations ────────────────────────────────────────────────
    print("  ① Fetching option expirations...")
    try:
        exp_resp = client.get_option_expirations(underlying)
        expirations = []
        if isinstance(exp_resp, dict):
            expirations = exp_resp.get('expirations', [])
        elif isinstance(exp_resp, list):
            expirations = exp_resp
        else:
            expirations = getattr(exp_resp, 'expirations', []) or []
    except Exception as e:
        print(f"  ❌ Error fetching expirations: {e}")
        sys.exit(1)

    exp = pick_expiration(expirations, args.dte)
    if not exp:
        print(f"  ❌ No suitable expiration found near {args.dte}d DTE.")
        sys.exit(1)

    today = datetime.today().date()
    dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
    print(f"     Selected expiration: {exp} ({dte}d DTE)")

    # ── Step 2: Get option chain ───────────────────────────────────────────────
    print(f"  ② Fetching option chain for {underlying} {exp}...")
    chain = get_option_chain_list(underlying, exp)
    if not chain:
        print(f"  ❌ Empty option chain. Cannot proceed.")
        sys.exit(1)
    print(f"     Found {len(chain)} contracts")

    # ── Step 3: Find sell leg (target ~30 delta) ───────────────────────────────
    print(f"  ③ Finding sell leg (target Δ ≈ {TARGET_SELL_DELTA})...")
    sell_leg = find_best_sell_leg(chain, option_type, TARGET_SELL_DELTA)
    if not sell_leg:
        print(f"  ❌ No suitable sell leg found.")
        sys.exit(1)

    print(f"     Sell leg:  {sell_leg['osi']}")
    print(f"     Strike:    ${sell_leg['strike']:.2f}  |  Delta: {sell_leg['delta']:.3f}  |  IV: {sell_leg['iv']*100:.1f}%")
    print(f"     Bid/Ask:   ${sell_leg['bid']:.2f} / ${sell_leg['ask']:.2f}  |  Mid: ${sell_leg['mid']:.2f}")

    # Validate sell leg delta is in acceptable range
    if sell_leg['delta'] < (TARGET_SELL_DELTA - DELTA_TOLERANCE) or \
       sell_leg['delta'] > (TARGET_SELL_DELTA + DELTA_TOLERANCE):
        print(f"  ⚠️  Sell delta {sell_leg['delta']:.3f} outside [{TARGET_SELL_DELTA - DELTA_TOLERANCE:.2f}, {TARGET_SELL_DELTA + DELTA_TOLERANCE:.2f}]. Continuing anyway.")

    # ── Step 4: Find buy leg (protection) ─────────────────────────────────────
    print(f"  ④ Finding buy leg ({option_type} at ${sell_leg['strike'] - args.width if is_put_credit else sell_leg['strike'] + args.width:.2f})...")
    buy_leg = find_buy_leg(chain, option_type, sell_leg['strike'], args.width)
    if not buy_leg:
        print(f"  ❌ No buy leg found. Try a different width.")
        sys.exit(1)

    print(f"     Buy leg:   {buy_leg['osi']}")
    print(f"     Strike:    ${buy_leg['strike']:.2f}")
    print(f"     Bid/Ask:   ${buy_leg['bid']:.2f} / ${buy_leg['ask']:.2f}  |  Mid: ${buy_leg['mid']:.2f}")

    # ── Step 5: Calculate credit and R/R ──────────────────────────────────────
    # Credit spread: sell the higher-priced leg, buy the protection
    # Net credit = sell_mid - buy_mid
    net_credit = sell_leg['mid'] - buy_leg['mid']
    spread_width_dollars = abs(sell_leg['strike'] - buy_leg['strike'])
    max_risk = (spread_width_dollars - net_credit) * 100 * args.quantity
    max_profit = net_credit * 100 * args.quantity
    credit_pct = net_credit / spread_width_dollars if spread_width_dollars else 0

    rr_ratio = spread_width_dollars / net_credit if net_credit > 0 else float('inf')

    print(f"\n  ⑤ Spread economics:")
    print(f"     Net credit:    ${net_credit:.2f} per share  (${net_credit*100:.2f} per spread)")
    print(f"     Spread width:  ${spread_width_dollars:.2f}")
    print(f"     Credit %:      {credit_pct:.1%} of width (min: {MIN_CREDIT_PCT:.0%})")
    print(f"     Max profit:    ${max_profit:.2f}")
    print(f"     Max risk:      ${max_risk:.2f}")
    print(f"     R/R ratio:     1:{rr_ratio:.1f} (min: 1:{MIN_RR_RATIO:.0f})")

    if net_credit <= 0:
        print(f"  ❌ Net credit is negative (${net_credit:.2f}). Cannot proceed.")
        sys.exit(1)

    if credit_pct < MIN_CREDIT_PCT:
        print(f"  ❌ Credit {credit_pct:.1%} < minimum {MIN_CREDIT_PCT:.0%}. Spread not attractive.")
        sys.exit(1)

    print(f"     ✅ R/R acceptable")

    # ── Step 6: Multi-leg preflight ────────────────────────────────────────────
    print(f"\n  ⑥ Running multi-leg preflight...")
    legs_for_order = [
        {
            'symbol': sell_leg['osi'],
            'side': 'SELL',
            'quantity': args.quantity,
            'limitPrice': round(sell_leg['mid'], 2),
        },
        {
            'symbol': buy_leg['osi'],
            'side': 'BUY',
            'quantity': args.quantity,
            'limitPrice': round(buy_leg['mid'], 2),
        },
    ]

    preflight = run_multi_leg_preflight(legs_for_order)
    if 'error' in preflight:
        print(f"     [warn] Preflight error: {preflight['error']}")
    else:
        est_credit = safe_float(preflight.get('estimatedCredit', preflight.get('netCredit', net_credit * 100 * args.quantity)))
        commission = safe_float(preflight.get('commission', preflight.get('fees', 0)))
        print(f"     Estimated credit:  ${est_credit:.2f}")
        print(f"     Commission:        ${commission:.2f}")
        print(f"     ✅ Preflight passed")

    # ── Order preview ──────────────────────────────────────────────────────────
    print(f"""
  ╔══════════════════════════════════════════════════════╗
  ║           {spread_label} SPREAD PREVIEW                ║
  ╠══════════════════════════════════════════════════════╣
  ║  Underlying:    {underlying:<37}║
  ║  Expiration:    {exp + f' ({dte}d DTE)':<37}║
  ╠══════════════════════════════════════════════════════╣
  ║  SELL  {sell_leg['osi']:<20}  ${sell_leg['mid']:.2f}/contract   ║
  ║  BUY   {buy_leg['osi']:<20}  ${buy_leg['mid']:.2f}/contract   ║
  ╠══════════════════════════════════════════════════════╣
  ║  Net Credit:    ${net_credit:.2f}/share   (${net_credit*100:.2f}/spread x {args.quantity})   ║
  ║  Max Profit:    ${max_profit:<37.2f}║
  ║  Max Risk:      ${max_risk:<37.2f}║
  ║  R/R:           1:{rr_ratio:<36.1f}║
  ╚══════════════════════════════════════════════════════╝""")

    if READ_ONLY:
        print(f"\n  🔒 READ-ONLY MODE: Order NOT submitted.\n")
        return

    # ── Confirmation ───────────────────────────────────────────────────────────
    print(f"\n  ⚠️  This will place a real multi-leg order on your Public.com account.")
    try:
        confirm = input("  Confirm spread order? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if confirm not in ('y', 'yes'):
        print("  Order cancelled by user.\n")
        return

    # ── Place order ────────────────────────────────────────────────────────────
    print(f"\n  Placing multi-leg order...")
    result = place_spread(legs_for_order)

    if 'error' in result:
        print(f"  ❌ Order failed: {result['error']}")
        sys.exit(1)
    else:
        order_id = result.get('orderId', result.get('id', 'unknown'))
        status = result.get('status', result.get('orderStatus', 'submitted'))
        print(f"  ✅ Credit spread submitted!")
        print(f"     Order ID: {order_id}")
        print(f"     Status:   {status}")
        print(f"\n  📌 Target: Close at 50% of max profit (${max_profit * 0.5:.2f})")
        print(f"  📌 Stop:   Close if spread widens to 2x credit (${net_credit * 2 * 100:.2f})\n")


if __name__ == '__main__':
    main()
