# Options Copilot for Public.com

> ⚠️ **Not financial advice.** For educational and informational purposes only. Options involve significant risk. Do your own research.

An AI-powered options trading copilot that chains **12 Public.com API capabilities** into a complete workflow:

```
scan → score → size → execute → monitor → exit
```

Uses **real Greeks** (delta, IV, theta) from the Public.com API for every decision — no estimates or third-party data for options analysis.

---

## Quick Start

### 🌐 Web UI (Recommended — No Terminal Required)

```bash
# 1. Install dependencies
pip install publicdotcom-py yfinance numpy flask flask-cors

# 2. Set your credentials
export PUBLIC_COM_SECRET=your_secret_key_here
export PUBLIC_COM_ACCOUNT_ID=your_account_id_here

# 3. Launch the web dashboard
python3 app.py

# 4. Open your browser
# → http://localhost:8080
```

The web UI provides a full browser-based command center with:
- 📊 **Portfolio Panel** — live positions, P/L, Greeks
- 🔍 **Scanner Panel** — 12-factor scoring with presets (Tech, S&P, Healthcare)
- 📐 **Spread Builder** — find & execute put/call credit spreads
- 🔭 **Monitor Panel** — real-time P/L with auto-exit triggers
- 📈 **History Panel** — trade history, win rate, P/L stats

---

### 💻 CLI (Terminal Power Users)

```bash
# 1. Install dependencies
pip install publicdotcom-py yfinance numpy

# 2. Set your credentials
export PUBLIC_COM_SECRET=your_secret_key_here
export PUBLIC_COM_ACCOUNT_ID=your_account_id_here

# 3. Scan for opportunities
python3 scripts/scan.py --symbols AAPL,NVDA,TSLA,META --min-score 72

# 4. Check your portfolio
python3 scripts/portfolio.py

# 5. Execute a trade (with confirmation prompt)
python3 scripts/trade.py --symbol NVDA260327P00180000 --side buy

# 6. Monitor positions continuously
python3 scripts/monitor.py --continuous
```

---

## Installation

```bash
pip install publicdotcom-py yfinance numpy
```

Get your API key at: https://public.com/settings/v2/api

---

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `PUBLIC_COM_SECRET` | ✅ | API secret key from Public.com settings |
| `PUBLIC_COM_ACCOUNT_ID` | ✅ | Your brokerage account ID |
| `COPILOT_READ_ONLY` | Optional | Set to `true` to disable order execution |

```bash
export PUBLIC_COM_SECRET=sk-...
export PUBLIC_COM_ACCOUNT_ID=5OG12345
export COPILOT_READ_ONLY=true   # safe mode — shows orders but doesn't place them
```

---

## Scripts

### `scan.py` — Opportunity Scanner

Scans option chains and scores each contract using a 12-factor composite system with **real Greeks**.

```bash
python3 scripts/scan.py --symbols AAPL,NVDA,TSLA,META,SPY,QQQ --min-score 72 --limit 10

# Options only
python3 scripts/scan.py --symbols NVDA --type call --min-score 75
```

**Example output:**
```
────────────────────────────────────────────────────────────────────────────────
 #  Symbol  Type  OSI Symbol                Score   Delta     IV%   Entry  DTE  Trend     RSI
────────────────────────────────────────────────────────────────────────────────
 1  NVDA    call  NVDA260327C00850000        82.0   0.412   38.5%   $2.15  21d  up        58.3
 2  AAPL    put   AAPL260417P00195000        77.5  -0.386   29.2%   $1.85  28d  down      43.1
 3  META    call  META260327C00560000        74.0   0.445   42.1%   $3.40  21d  up        52.7
────────────────────────────────────────────────────────────────────────────────

✅ 3 signal(s) found | Threshold: 72+ | 2026-03-20 09:31:05
```

**12-Factor Scoring Engine:**

| # | Factor | Max Pts | Data Source |
|---|--------|---------|-------------|
| 1 | Directional Alignment | 25 | Trend (SMA20/50) |
| 2 | Trend Strength | 12 | Price vs SMAs |
| 3 | IV Analysis | 15 | **Real IV from Greeks API** |
| 4 | RSI Confirmation | 8 | 14-period RSI |
| 5 | Delta Band | 12 | **Real delta from Greeks API** |
| 6 | Unusual Volume | 10 | Volume vs 20-day avg |
| 7 | Liquidity | 6 | Bid/ask spread |
| 8 | Optimal DTE | 6 | Days to expiration |
| 9 | Affordability | 6 | Option price vs account |
| 10 | Regime Check | Gate | Trend vs chop detection |
| 11 | Range Position | −15 to 0 | Daily/weekly high-low |
| 12 | Spread Gate | Gate | Bid/ask > 10% = reject |

Signals at **72+** are flagged as actionable opportunities.

---

### `portfolio.py` — Portfolio Viewer

Shows current positions with live P/L and Greeks exposure.

```bash
python3 scripts/portfolio.py
python3 scripts/portfolio.py --no-greeks   # faster, skip Greeks fetch
```

**Example output:**
```
📊 Public.com Options Copilot — Portfolio
   Account: 5OG12345
   Time:    2026-03-20 09:45:00

  💰 Portfolio Value: $4,820.50
  💵 Buying Power:    $2,150.00
  🏦 Cash Balance:    $1,980.25

  🎯 OPTIONS
  OSI Symbol               Qty   Avg   Last      P/L   Delta   IV%    Theta  DTE
  ──────────────────────────────────────────────────────────────────────────────────
  NVDA260327P00180000        2  $1.70  $2.04  +$68.00   0.412  38.5%  $-0.045  7d

  Greeks Exposure:   Δ-dollars: $4,120   θ/day: $-9.00

  ──────────────────────────────────────────────────────
  Total Unrealized P/L:  +$68.00
  Open Positions:        1
  Options Positions:     1
```

---

### `trade.py` — Single-Leg Order Execution

Places a single-leg options order with full safety pipeline.

```bash
# Auto-size position ($300-500 range)
python3 scripts/trade.py --symbol NVDA260327P00180000 --side buy

# Specify quantity manually
python3 scripts/trade.py --symbol AAPL260417C00195000 --side buy --quantity 2

# Sell to close
python3 scripts/trade.py --symbol NVDA260327P00180000 --side sell --quantity 2

# Preview only (no order placed)
COPILOT_READ_ONLY=true python3 scripts/trade.py --symbol NVDA260327P00180000 --side buy
```

**Safety pipeline:**
1. Real-time quote fetch (bid/ask)
2. Spread check — rejects if bid/ask > 10%
3. Midpoint limit pricing (never pays the ask)
4. Auto-sizes to $300–$500 position
5. Validates max $75 risk at 15% stop
6. Checks concurrent position limit (max 3)
7. Preflight calculation (buying power, fees)
8. Preview with stop/target prices
9. **Confirmation prompt before execution**

---

### `spread.py` — Credit Spread Builder

Finds optimal strikes and executes vertical credit spreads.

```bash
# Put credit spread (bullish / neutral)
python3 scripts/spread.py --underlying AAPL --type put_credit --width 5 --dte 21

# Call credit spread (bearish / neutral)
python3 scripts/spread.py --underlying SPY --type call_credit --width 3 --dte 14

# Wider spread
python3 scripts/spread.py --underlying NVDA --type put_credit --width 10 --dte 30
```

**What it does:**
1. Fetches real option chain + Greeks
2. Finds sell leg nearest to Δ0.30
3. Finds buy leg at `strike ± width`
4. Calculates net credit from real bid/ask
5. Validates R/R: credit ≥ 20% of spread width
6. Multi-leg preflight (buying power check)
7. **Confirmation prompt before executing**

---

### `monitor.py` — Position Monitor & Auto-Exit

Watches open positions and triggers limit-order exits automatically.

```bash
# Single check
python3 scripts/monitor.py --check

# Continuous (every 30 seconds)
python3 scripts/monitor.py --continuous
```

**Exit triggers:**
| Trigger | Condition | Action |
|---------|-----------|--------|
| 🎯 Profit target | Current > entry × 1.20 | Sell limit at bid |
| 🛑 Stop loss | Current < entry × 0.85 | Sell limit at bid |
| 🕒 EOD close | 3:45 PM or later | Sell limit at bid |

All exits use **limit orders** (never market orders).

---

### `history.py` — Trade History & Performance

```bash
# Last 30 days (default)
python3 scripts/history.py

# Last 7 days
python3 scripts/history.py --days 7

# Last 90 days, include equities
python3 scripts/history.py --days 90 --show-all

# Raw order list
python3 scripts/history.py --raw
```

**Example output:**
```
  ╔══════════════════════════════════════════════════╗
  ║         PERFORMANCE SUMMARY (30d)               ║
  ╠══════════════════════════════════════════════════╣
  ║  Total Trades:    12                            ║
  ║  Wins / Losses:   8 / 4                         ║
  ║  Win Rate:        66.7%                          ║
  ╠══════════════════════════════════════════════════╣
  ║  Total P/L:       +$342.50                       ║
  ║  Avg Win:         +$75.40                        ║
  ║  Avg Loss:        -$37.20                        ║
  ║  Profit Factor:   2.71x                          ║
  ╠══════════════════════════════════════════════════╣
  ║  Best Trade:      NVDA put +$180.00 (2026-03-10) ║
  ║  Worst Trade:     TSLA call -$96.00 (2026-03-05) ║
  ╚══════════════════════════════════════════════════╝
```

---

## Safety Features

| Feature | Detail |
|---------|--------|
| 🔑 Env-only auth | Credentials never hardcoded, never logged |
| 📋 Preflight always | Every order runs buying power + fee check first |
| ✅ Confirmation prompt | Interactive yes/no before executing |
| 🎯 Limit orders only | No market orders — ever |
| 📏 Spread check | Rejects illiquid options (bid/ask > 10%) |
| 💰 Position limits | Max 3 concurrent positions, $300–$500 each |
| 🛑 Risk cap | Max $75 risk per trade at 15% stop |
| 🔒 Read-only mode | `COPILOT_READ_ONLY=true` — shows preview, no execution |
| 🕒 EOD auto-close | Monitor exits all positions by 3:45 PM |

---

## Typical Workflow

### Morning Scan → Trade
```bash
# 1. Scan for opportunities
python3 scripts/scan.py --symbols AAPL,NVDA,TSLA,META,SPY --min-score 72

# 2. Review top signal — e.g. NVDA260327C00850000, score 82, delta 0.41
# 3. Execute with safety checks
python3 scripts/trade.py --symbol NVDA260327C00850000 --side buy

# 4. Start the monitor
python3 scripts/monitor.py --continuous &
```

### Theta Play (Credit Spread)
```bash
# Sell a 5-wide put credit spread on AAPL, 21 DTE
python3 scripts/spread.py --underlying AAPL --type put_credit --width 5 --dte 21

# Monitor will show credit spread P/L as well
python3 scripts/monitor.py --check
```

### End-of-Day Review
```bash
python3 scripts/portfolio.py
python3 scripts/history.py --days 7
```

---

## Public.com SDK Methods Used

| Script | SDK Methods |
|--------|-------------|
| scan.py | `get_option_expirations`, `get_option_chain`, `get_option_greeks` |
| portfolio.py | `get_portfolio`, `get_quotes`, `get_option_greeks` |
| trade.py | `get_quotes`, `get_portfolio`, `perform_preflight_calculation`, `place_order` |
| spread.py | `get_option_expirations`, `get_option_chain`, `get_option_greeks`, `perform_multi_leg_preflight_calculation`, `place_multileg_order` |
| monitor.py | `get_portfolio`, `get_quotes`, `place_order` |
| history.py | `get_history` |

---

## License

Apache License 2.0 — see [LICENSE](https://www.apache.org/licenses/LICENSE-2.0)

---

*Built for the [OpenClaw](https://openclaw.ai) skills ecosystem.*
