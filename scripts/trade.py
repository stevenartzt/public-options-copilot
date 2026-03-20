#!/usr/bin/env python3
"""
trade.py — Single-Leg Options Order Execution for Public.com Copilot

Places a single-leg options order with safety checks, midpoint pricing,
position sizing, and a preflight calculation before executing.

Usage:
    python3 trade.py --symbol NVDA260327P00180000 --side buy
    python3 trade.py --symbol AAPL260417C00195000 --side buy --quantity 2

Read-only mode (show what WOULD happen but don't execute):
    COPILOT_READ_ONLY=true python3 trade.py --symbol ... --side buy
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

# ── Position sizing constants ──────────────────────────────────────────────────
MIN_POSITION_DOLLARS = 300
MAX_POSITION_DOLLARS = 500
MAX_RISK_DOLLARS = 75         # max acceptable loss at 15% stop
STOP_LOSS_PCT = 0.15
MAX_SPREAD_PCT = 0.10         # reject if bid/ask spread > 10%
MAX_CONCURRENT_POSITIONS = 3


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
            val = getattr(obj, key, None)
            if val is not None:
                return val
    return default


def parse_osi(osi: str) -> dict:
    """Parse OSI symbol into components."""
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


def get_quote(symbol: str) -> dict:
    """Fetch real-time quote for a symbol."""
    try:
        resp = client.get_quotes([symbol])
        quotes = []
        if isinstance(resp, dict):
            quotes = resp.get('quotes', list(resp.values()))
        elif isinstance(resp, list):
            quotes = resp

        for q in quotes:
            sym = get_attr(q, 'symbol', 'ticker', default='')
            if sym == symbol or not sym:
                bid = safe_float(get_attr(q, 'bid', default=0))
                ask = safe_float(get_attr(q, 'ask', default=0))
                last = safe_float(get_attr(q, 'lastTradePrice', 'last', 'price', default=0))
                return {'bid': bid, 'ask': ask, 'last': last}
    except Exception as e:
        print(f"[warn] Quote fetch failed: {e}")
    return {}


def auto_size_position(entry_price: float) -> tuple[int, float]:
    """
    Calculate optimal quantity for a $300-500 position.
    Each option contract = 100 shares.
    Returns (quantity, total_cost).
    """
    cost_per_contract = entry_price * 100
    if cost_per_contract <= 0:
        return 1, entry_price * 100

    # Try to fit within $300-$500 window
    for qty in range(1, 20):
        total = cost_per_contract * qty
        if MIN_POSITION_DOLLARS <= total <= MAX_POSITION_DOLLARS:
            return qty, total
        if total > MAX_POSITION_DOLLARS:
            # Try previous quantity
            prev_total = cost_per_contract * (qty - 1)
            if prev_total >= MIN_POSITION_DOLLARS:
                return qty - 1, prev_total
            # Fall through: use 1 contract even if out of range
            return 1, cost_per_contract

    return 1, cost_per_contract


def check_portfolio_limits() -> tuple[bool, str]:
    """
    Check if we can open another position.
    Returns (ok, message).
    """
    try:
        portfolio = client.get_portfolio()
        if isinstance(portfolio, dict):
            positions = portfolio.get('positions', portfolio.get('holdings', []))
        else:
            positions = getattr(portfolio, 'positions', None) or getattr(portfolio, 'holdings', []) or []

        # Count option positions
        option_count = 0
        for pos in positions:
            sym = get_attr(pos, 'symbol', 'ticker', default='')
            if len(sym) > 10 and any(c.isdigit() for c in sym[6:]):
                option_count += 1

        if option_count >= MAX_CONCURRENT_POSITIONS:
            return False, f"Max concurrent positions reached ({option_count}/{MAX_CONCURRENT_POSITIONS})"
        return True, f"OK ({option_count}/{MAX_CONCURRENT_POSITIONS} positions)"
    except Exception as e:
        return True, f"Could not check portfolio (proceeding): {e}"


def run_preflight(symbol: str, side: str, quantity: int, limit_price: float) -> dict:
    """Run preflight calculation and return results."""
    try:
        preflight_params = {
            'symbol': symbol,
            'side': side.upper(),
            'quantity': quantity,
            'orderType': 'LIMIT',
            'limitPrice': limit_price,
            'timeInForce': 'DAY',
        }
        result = client.perform_preflight_calculation(**preflight_params)
        if isinstance(result, dict):
            return result
        elif hasattr(result, '__dict__'):
            return vars(result)
        return {}
    except Exception as e:
        return {'error': str(e)}


def place_order(symbol: str, side: str, quantity: int, limit_price: float) -> dict:
    """Place a single-leg limit order."""
    try:
        order_params = {
            'symbol': symbol,
            'side': side.upper(),
            'quantity': quantity,
            'orderType': 'LIMIT',
            'limitPrice': round(limit_price, 2),
            'timeInForce': 'DAY',
        }
        result = client.place_order(**order_params)
        if isinstance(result, dict):
            return result
        elif hasattr(result, '__dict__'):
            return vars(result)
        return {'result': str(result)}
    except Exception as e:
        return {'error': str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Place a single-leg options order with safety checks"
    )
    parser.add_argument('--symbol', required=True,
                        help='OSI option symbol, e.g. NVDA260327P00180000')
    parser.add_argument('--side', required=True, choices=['buy', 'sell'],
                        help='Order side: buy or sell')
    parser.add_argument('--quantity', type=int, default=None,
                        help='Number of contracts (auto-sized if omitted)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Alias for READ_ONLY mode')
    args = parser.parse_args()

    read_only = READ_ONLY or args.dry_run
    symbol = args.symbol.upper()
    side = args.side.lower()

    if read_only:
        print("\n⚠️  READ-ONLY MODE — No orders will be placed\n")

    print(f"\n🎯 Options Copilot — Trade Execution")
    print(f"   Symbol:   {symbol}")
    print(f"   Side:     {side.upper()}")
    print(f"   Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ── Parse OSI symbol ───────────────────────────────────────────────────────
    osi_info = parse_osi(symbol)
    if osi_info:
        print(f"  📋 Contract Details:")
        print(f"     Underlying:   {osi_info['underlying']}")
        print(f"     Option Type:  {osi_info['option_type'].upper()}")
        print(f"     Strike:       ${osi_info['strike']:.2f}")
        print(f"     Expiration:   {osi_info['expiration']} ({osi_info['dte']}d DTE)")
        print()

    # ── Step 1: Get real-time quote ────────────────────────────────────────────
    print("  ① Fetching real-time quote...")
    quote = get_quote(symbol)
    if not quote:
        print("  ❌ Could not fetch quote. Aborting.")
        sys.exit(1)

    bid = quote.get('bid', 0)
    ask = quote.get('ask', 0)
    last = quote.get('last', 0)

    print(f"     Bid: ${bid:.2f}  Ask: ${ask:.2f}  Last: ${last:.2f}")

    if bid <= 0 and ask <= 0:
        print("  ❌ No valid market. Aborting.")
        sys.exit(1)

    # ── Step 2: Spread check ───────────────────────────────────────────────────
    mid = (bid + ask) / 2 if bid and ask else (ask or last)
    spread = ask - bid if bid and ask else 0
    spread_pct = spread / mid if mid else 1.0

    print(f"\n  ② Spread check: {spread_pct:.1%} (limit: {MAX_SPREAD_PCT:.0%})")
    if spread_pct > MAX_SPREAD_PCT:
        print(f"  ❌ Bid/ask spread too wide ({spread_pct:.1%} > {MAX_SPREAD_PCT:.0%}). Aborting.")
        print("     Use a more liquid contract.")
        sys.exit(1)
    print(f"     ✅ Spread OK")

    # ── Step 3: Midpoint limit price ───────────────────────────────────────────
    # For buys: use midpoint (not ask). For sells: use midpoint (not bid).
    limit_price = round(mid, 2)
    print(f"\n  ③ Limit price (midpoint): ${limit_price:.2f}")

    # ── Step 4: Position sizing ────────────────────────────────────────────────
    entry = limit_price
    if args.quantity:
        quantity = args.quantity
        total_cost = entry * 100 * quantity
    else:
        quantity, total_cost = auto_size_position(entry)

    max_risk = total_cost * STOP_LOSS_PCT
    print(f"\n  ④ Position sizing:")
    print(f"     Quantity:       {quantity} contract(s)")
    print(f"     Total cost:     ${total_cost:.2f}")
    print(f"     Max risk (15%): ${max_risk:.2f} (limit: ${MAX_RISK_DOLLARS})")

    if max_risk > MAX_RISK_DOLLARS and side == 'buy':
        print(f"  ⚠️  Max risk ${max_risk:.2f} exceeds ${MAX_RISK_DOLLARS} limit.")
        # Try reducing to 1 contract
        if quantity > 1:
            quantity = 1
            total_cost = entry * 100
            max_risk = total_cost * STOP_LOSS_PCT
            print(f"     Reducing to 1 contract → max risk: ${max_risk:.2f}")
            if max_risk > MAX_RISK_DOLLARS:
                print(f"  ❌ Even 1 contract exceeds risk limit. Consider a cheaper option.")
                sys.exit(1)
        else:
            print(f"  ❌ Risk limit exceeded. Choose a lower-priced option.")
            sys.exit(1)

    # ── Step 5: Portfolio limits check ────────────────────────────────────────
    if side == 'buy':
        print(f"\n  ⑤ Portfolio limits check...")
        ok, msg = check_portfolio_limits()
        print(f"     {msg}")
        if not ok:
            print(f"  ❌ {msg}")
            sys.exit(1)
        print(f"     ✅ Position limit OK")

    # ── Step 6: Preflight calculation ──────────────────────────────────────────
    print(f"\n  ⑥ Running preflight calculation...")
    preflight = run_preflight(symbol, side, quantity, limit_price)
    if 'error' in preflight:
        print(f"     [warn] Preflight error: {preflight['error']}")
        preflight_ok = True  # proceed anyway, warn user
    else:
        est_cost = safe_float(preflight.get('estimatedCost', preflight.get('cost', total_cost)))
        commission = safe_float(preflight.get('commission', preflight.get('fees', 0)))
        buying_power = safe_float(preflight.get('buyingPower', preflight.get('availableFunds', 0)))
        print(f"     Estimated cost:  ${est_cost:.2f}")
        print(f"     Commission:      ${commission:.2f}")
        if buying_power:
            print(f"     Buying power:    ${buying_power:,.2f}")
        preflight_ok = True
        print(f"     ✅ Preflight passed")

    # ── Step 7: Summary preview ────────────────────────────────────────────────
    stop_price = round(entry * (1 - STOP_LOSS_PCT), 2) if side == 'buy' else None
    target_price = round(entry * 1.20, 2) if side == 'buy' else None

    print(f"""
  ╔══════════════════════════════════════════╗
  ║           ORDER PREVIEW                  ║
  ╠══════════════════════════════════════════╣
  ║  Symbol:       {symbol:<26}║
  ║  Side:         {side.upper():<26}║
  ║  Quantity:     {str(quantity) + ' contract(s)':<26}║
  ║  Limit Price:  ${limit_price:<25.2f}║
  ║  Total Cost:   ${total_cost:<25.2f}║""")
    if stop_price:
        print(f"  ║  Stop Loss:    ${stop_price:<25.2f}║")
        print(f"  ║  Profit Target:${target_price:<25.2f}║")
    if osi_info:
        print(f"  ║  DTE:          {str(osi_info['dte']) + 'd':<26}║")
    print(f"  ║  Order Type:   LIMIT / DAY            ║")
    print(f"  ╚══════════════════════════════════════════╝")

    if read_only:
        print(f"\n  🔒 READ-ONLY MODE: Order NOT submitted.")
        print(f"     Remove COPILOT_READ_ONLY to enable live trading.\n")
        return

    # ── Step 8: Confirmation ───────────────────────────────────────────────────
    print(f"\n  ⚠️  This will place a real order on your Public.com account.")
    try:
        confirm = input("  Confirm order? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if confirm not in ('y', 'yes'):
        print("  Order cancelled by user.\n")
        return

    # ── Step 9: Place order ────────────────────────────────────────────────────
    print(f"\n  ⑨ Placing order...")
    result = place_order(symbol, side, quantity, limit_price)

    if 'error' in result:
        print(f"  ❌ Order failed: {result['error']}")
        sys.exit(1)
    else:
        order_id = result.get('orderId', result.get('id', 'unknown'))
        status = result.get('status', result.get('orderStatus', 'submitted'))
        print(f"  ✅ Order submitted!")
        print(f"     Order ID: {order_id}")
        print(f"     Status:   {status}")
        print(f"\n  📌 Remember: Set stop at ${stop_price:.2f} (-15%) and target at ${target_price:.2f} (+20%)\n" if stop_price else "\n")


if __name__ == '__main__':
    main()
