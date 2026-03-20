#!/usr/bin/env python3
"""
scan.py — Options Opportunity Scanner for Public.com Copilot

Scans option chains for opportunities using a 12-factor composite scoring
system with real Greeks from the Public.com API.

Usage:
    python3 scan.py --symbols AAPL,NVDA,TSLA --min-score 72 --limit 10
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import sys
import argparse
import math
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

try:
    import yfinance as yf
    import numpy as np
except ImportError:
    print("Error: Required packages missing.")
    print("  pip install yfinance numpy")
    sys.exit(1)

# ── Client setup ───────────────────────────────────────────────────────────────
auth = ApiKeyAuthConfig(api_secret_key=API_SECRET)
config = PublicApiClientConfiguration(default_account_number=ACCOUNT_ID)
client = PublicApiClient(auth_config=auth, config=config)


# ── Technical helpers ──────────────────────────────────────────────────────────

def get_technicals(symbol: str) -> dict:
    """Fetch OHLCV + compute SMA20/50, RSI, MACD, ADX, volume ratio."""
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 20:
            return {}

        closes = hist['Close'].values
        volumes = hist['Volume'].values
        highs = hist['High'].values
        lows = hist['Low'].values

        # SMAs
        sma20 = np.mean(closes[-20:])
        sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else np.mean(closes)
        last = closes[-1]

        # RSI (14)
        deltas = np.diff(closes[-15:])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.mean(gains) if len(gains) else 0
        avg_loss = np.mean(losses) if len(losses) else 1e-9
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))

        # MACD (12/26/9)
        def ema(arr, n):
            k = 2 / (n + 1)
            e = arr[0]
            for v in arr[1:]:
                e = v * k + e * (1 - k)
            return e
        ema12 = ema(closes[-30:], 12)
        ema26 = ema(closes[-30:], 26) if len(closes) >= 26 else ema12
        macd = ema12 - ema26

        # Volume ratio (today vs 20-day avg)
        vol_avg = np.mean(volumes[-21:-1]) if len(volumes) > 21 else np.mean(volumes)
        vol_ratio = volumes[-1] / (vol_avg + 1) if vol_avg else 1.0

        # Daily/weekly range position
        day_range = highs[-1] - lows[-1]
        day_pos = (last - lows[-1]) / (day_range + 1e-9)
        week_high = np.max(highs[-5:])
        week_low = np.min(lows[-5:])
        week_range = week_high - week_low
        week_pos = (last - week_low) / (week_range + 1e-9)

        # ADX approximation (simplified)
        tr_list = []
        for i in range(-14, 0):
            h, l, pc = highs[i], lows[i], closes[i - 1]
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        adx_proxy = np.mean(tr_list) / (last + 1e-9) * 100  # volatility proxy

        # Trend direction
        if last > sma20 > sma50:
            trend = 'up'
        elif last < sma20 < sma50:
            trend = 'down'
        else:
            trend = 'neutral'

        return {
            'last': last,
            'sma20': sma20,
            'sma50': sma50,
            'rsi': rsi,
            'macd': macd,
            'vol_ratio': vol_ratio,
            'day_pos': day_pos,
            'week_pos': week_pos,
            'adx_proxy': adx_proxy,
            'trend': trend,
        }
    except Exception as e:
        print(f"    [warn] Technicals failed for {symbol}: {e}")
        return {}


def pick_expiration(expirations: list, target_dte: int = 21) -> str | None:
    """Choose the expiration closest to target_dte days out."""
    today = datetime.today().date()
    best = None
    best_diff = 9999
    for exp in expirations:
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte < 7:
                continue
            diff = abs(dte - target_dte)
            if diff < best_diff:
                best_diff = diff
                best = exp
        except Exception:
            continue
    return best


# ── 12-Factor Scoring ──────────────────────────────────────────────────────────

def score_option(
    option_type: str,
    greeks: dict,
    tech: dict,
    entry_price: float,
    bid: float,
    ask: float,
    dte: int,
    account_size: float = 5000.0,
) -> tuple[float, dict]:
    """
    12-factor composite score (0-100).
    Returns (score, breakdown_dict).
    """
    breakdown = {}
    score = 0.0

    # ── Gate: Spread Check (Factor 12) ────────────────────────────────────────
    mid = (bid + ask) / 2 if bid and ask else entry_price
    spread_pct = (ask - bid) / (mid + 1e-9) if mid else 1.0
    if spread_pct > 0.10:
        return 0.0, {'reject': f'spread too wide ({spread_pct:.1%})'}

    # ── Gate: Regime Check (Factor 10) ────────────────────────────────────────
    adx_proxy = tech.get('adx_proxy', 5)
    if adx_proxy < 1.5:
        return 0.0, {'reject': 'choppy/no-trend regime (ADX proxy low)'}
    breakdown['regime'] = 'trending'

    # ── Factor 1: Directional Alignment (25 pts) ──────────────────────────────
    trend = tech.get('trend', 'neutral')
    if (option_type == 'call' and trend == 'up') or \
       (option_type == 'put' and trend == 'down'):
        pts = 25
    elif trend == 'neutral':
        pts = 10
    else:
        pts = 0
    score += pts
    breakdown['directional_alignment'] = pts

    # ── Factor 2: Trend Strength (12 pts) ─────────────────────────────────────
    last = tech.get('last', 1)
    sma20 = tech.get('sma20', last)
    sma50 = tech.get('sma50', last)
    trend_gap = abs(last - sma20) / (last + 1e-9)
    pts = min(12, int(trend_gap * 300))
    score += pts
    breakdown['trend_strength'] = pts

    # ── Factor 3: IV Analysis (15 pts) ────────────────────────────────────────
    iv = greeks.get('impliedVolatility', greeks.get('iv', 0.0)) or 0.0
    # Sweet spot: IV 25-60% for directional plays
    if 0.25 <= iv <= 0.60:
        pts = 15
    elif 0.20 <= iv < 0.25 or 0.60 < iv <= 0.80:
        pts = 8
    elif iv > 0.80:
        pts = 3  # IV crush risk
    else:
        pts = 5  # too low IV = expensive relative moves
    score += pts
    breakdown['iv_analysis'] = pts
    breakdown['iv'] = iv

    # ── Factor 4: RSI Confirmation (8 pts) ────────────────────────────────────
    rsi = tech.get('rsi', 50)
    if option_type == 'call' and 45 <= rsi <= 70:
        pts = 8
    elif option_type == 'put' and 30 <= rsi <= 55:
        pts = 8
    elif option_type == 'call' and rsi > 70:
        pts = 2  # overbought
    elif option_type == 'put' and rsi < 30:
        pts = 2  # oversold bounce risk
    else:
        pts = 4
    score += pts
    breakdown['rsi'] = pts

    # ── Factor 5: Delta Band (12 pts) ─────────────────────────────────────────
    delta = abs(greeks.get('delta', 0.0) or 0.0)
    # Sweet spot: 0.35-0.55 (not too OTM, not too ITM)
    if 0.35 <= delta <= 0.55:
        pts = 12
    elif 0.25 <= delta < 0.35 or 0.55 < delta <= 0.65:
        pts = 8
    elif 0.65 < delta <= 0.80:
        pts = 4
    else:
        pts = 1
    score += pts
    breakdown['delta_band'] = pts
    breakdown['delta'] = greeks.get('delta', 0.0)

    # ── Factor 6: Unusual Volume (10 pts) ─────────────────────────────────────
    vol_ratio = tech.get('vol_ratio', 1.0)
    if vol_ratio >= 2.0:
        pts = 10
    elif vol_ratio >= 1.5:
        pts = 7
    elif vol_ratio >= 1.2:
        pts = 4
    else:
        pts = 0
    score += pts
    breakdown['volume'] = pts

    # ── Factor 7: Liquidity / Spread (6 pts) ──────────────────────────────────
    if spread_pct <= 0.02:
        pts = 6
    elif spread_pct <= 0.05:
        pts = 4
    elif spread_pct <= 0.10:
        pts = 2
    else:
        pts = 0
    score += pts
    breakdown['liquidity'] = pts

    # ── Factor 8: Optimal DTE (6 pts) ─────────────────────────────────────────
    if 15 <= dte <= 35:
        pts = 6
    elif 10 <= dte < 15 or 35 < dte <= 50:
        pts = 4
    elif 7 <= dte < 10:
        pts = 2
    else:
        pts = 1
    score += pts
    breakdown['dte'] = pts

    # ── Factor 9: Affordability (6 pts) ───────────────────────────────────────
    cost_1_contract = entry_price * 100
    cost_pct = cost_1_contract / (account_size + 1e-9)
    if 0.03 <= cost_pct <= 0.12:
        pts = 6
    elif cost_pct < 0.03:
        pts = 3  # very cheap = likely far OTM
    else:
        pts = 2  # expensive
    score += pts
    breakdown['affordability'] = pts

    # ── Factor 11: Range Position (−15 to 0 penalty) ──────────────────────────
    day_pos = tech.get('day_pos', 0.5)
    week_pos = tech.get('week_pos', 0.5)
    penalty = 0
    if option_type == 'call':
        # Penalise buying calls at daily/weekly highs
        if day_pos > 0.85:
            penalty -= 10
        elif day_pos > 0.75:
            penalty -= 5
        if week_pos > 0.85:
            penalty -= 5
    else:
        # Penalise buying puts at daily/weekly lows
        if day_pos < 0.15:
            penalty -= 10
        elif day_pos < 0.25:
            penalty -= 5
        if week_pos < 0.15:
            penalty -= 5
    score += penalty
    breakdown['range_penalty'] = penalty

    return max(0.0, min(100.0, score)), breakdown


# ── Main scanner ───────────────────────────────────────────────────────────────

def scan_symbol(symbol: str, min_score: float) -> list[dict]:
    """Scan a single symbol and return scored opportunities."""
    results = []
    print(f"  Scanning {symbol}...")

    tech = get_technicals(symbol)
    if not tech:
        print(f"    [skip] No technical data for {symbol}")
        return []

    # Get option expirations
    try:
        expirations_resp = client.get_option_expirations(symbol)
        expirations = []
        if hasattr(expirations_resp, 'expirations'):
            expirations = expirations_resp.expirations or []
        elif isinstance(expirations_resp, dict):
            expirations = expirations_resp.get('expirations', [])
        elif isinstance(expirations_resp, list):
            expirations = expirations_resp
    except Exception as e:
        print(f"    [skip] No expirations for {symbol}: {e}")
        return []

    if not expirations:
        print(f"    [skip] No expirations found for {symbol}")
        return []

    exp = pick_expiration(expirations, target_dte=21)
    if not exp:
        return []

    today = datetime.today().date()
    dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days

    # Get option chain
    try:
        chain_resp = client.get_option_chain(symbol, exp)
        chain = []
        if hasattr(chain_resp, 'options'):
            chain = chain_resp.options or []
        elif isinstance(chain_resp, dict):
            chain = chain_resp.get('options', [])
        elif isinstance(chain_resp, list):
            chain = chain_resp
    except Exception as e:
        print(f"    [skip] No chain for {symbol} {exp}: {e}")
        return []

    if not chain:
        return []

    # Score each option
    for opt in chain:
        try:
            # Extract fields (SDK may return objects or dicts)
            if isinstance(opt, dict):
                osi = opt.get('symbol', '')
                option_type = opt.get('optionType', opt.get('type', '')).lower()
                bid = float(opt.get('bid', 0) or 0)
                ask = float(opt.get('ask', 0) or 0)
                last_price = float(opt.get('lastTradePrice', opt.get('last', 0)) or 0)
            else:
                osi = getattr(opt, 'symbol', '')
                option_type = (getattr(opt, 'optionType', '') or getattr(opt, 'type', '') or '').lower()
                bid = float(getattr(opt, 'bid', 0) or 0)
                ask = float(getattr(opt, 'ask', 0) or 0)
                last_price = float(getattr(opt, 'lastTradePrice', None) or getattr(opt, 'last', 0) or 0)

            if not osi or option_type not in ('call', 'put'):
                continue

            entry = (bid + ask) / 2 if bid and ask else last_price
            if entry <= 0:
                continue

            # Get real Greeks
            try:
                greeks_resp = client.get_option_greeks(osi)
                if isinstance(greeks_resp, dict):
                    greeks = greeks_resp
                elif hasattr(greeks_resp, '__dict__'):
                    greeks = vars(greeks_resp)
                else:
                    greeks = {}
            except Exception:
                greeks = {}

            score, breakdown = score_option(
                option_type=option_type,
                greeks=greeks,
                tech=tech,
                entry_price=entry,
                bid=bid,
                ask=ask,
                dte=dte,
            )

            if score >= min_score:
                results.append({
                    'symbol': symbol,
                    'osi': osi,
                    'type': option_type,
                    'expiration': exp,
                    'dte': dte,
                    'bid': bid,
                    'ask': ask,
                    'entry': round(entry, 2),
                    'score': round(score, 1),
                    'delta': round(breakdown.get('delta', 0.0), 3),
                    'iv': round(breakdown.get('iv', 0.0) * 100, 1),
                    'trend': tech.get('trend', 'neutral'),
                    'rsi': round(tech.get('rsi', 50), 1),
                    'breakdown': breakdown,
                })
        except Exception as e:
            continue

    return results


def print_table(signals: list[dict]) -> None:
    """Print a formatted table of signals."""
    if not signals:
        print("\nNo signals found above threshold.")
        return

    header = (
        f"\n{'#':>2}  {'Symbol':<6}  {'Type':<4}  {'OSI Symbol':<24}  "
        f"{'Score':>5}  {'Delta':>6}  {'IV%':>6}  {'Entry':>6}  "
        f"{'DTE':>3}  {'Trend':<8}  {'RSI':>5}"
    )
    sep = "─" * len(header)
    print(sep)
    print(header)
    print(sep)

    for i, s in enumerate(signals, 1):
        print(
            f"{i:>2}  {s['symbol']:<6}  {s['type']:<4}  {s['osi']:<24}  "
            f"{s['score']:>5.1f}  {s['delta']:>6.3f}  {s['iv']:>5.1f}%  "
            f"${s['entry']:>5.2f}  {s['dte']:>3}d  {s['trend']:<8}  {s['rsi']:>5.1f}"
        )

    print(sep)
    print(f"\n✅ {len(signals)} signal(s) found | Threshold: {signals[0].get('_min_score', '72+')} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scan option chains for opportunities (12-factor scoring)"
    )
    parser.add_argument(
        '--symbols', required=True,
        help='Comma-separated ticker symbols, e.g. AAPL,NVDA,TSLA'
    )
    parser.add_argument(
        '--min-score', type=float, default=72.0,
        help='Minimum composite score to include (default: 72)'
    )
    parser.add_argument(
        '--limit', type=int, default=10,
        help='Max number of results to show (default: 10)'
    )
    parser.add_argument(
        '--type', choices=['call', 'put', 'both'], default='both',
        help='Filter by option type (default: both)'
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    print(f"\n🔍 Options Copilot — Scanning {len(symbols)} symbol(s) for opportunities...")
    print(f"   Min score: {args.min_score} | Limit: {args.limit}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    all_signals = []
    for sym in symbols:
        try:
            sigs = scan_symbol(sym, min_score=args.min_score)
            # Filter by type if requested
            if args.type != 'both':
                sigs = [s for s in sigs if s['type'] == args.type]
            all_signals.extend(sigs)
        except Exception as e:
            print(f"  [error] {sym}: {e}")

    # Sort by score descending, take top N
    all_signals.sort(key=lambda x: x['score'], reverse=True)
    top_signals = all_signals[:args.limit]
    for s in top_signals:
        s['_min_score'] = f"{args.min_score}+"

    print_table(top_signals)

    # Detailed breakdown for top signal
    if top_signals:
        best = top_signals[0]
        print(f"\n📊 Top signal breakdown: {best['osi']}")
        bd = best['breakdown']
        for k, v in bd.items():
            if k not in ('reject',):
                print(f"   {k:<25} {v}")


if __name__ == '__main__':
    main()
