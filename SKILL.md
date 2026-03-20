---
id: public-options-copilot
name: Options Copilot
description: AI-powered options trading copilot for Public.com. Scans option chains, scores opportunities using real Greeks (delta, IV, theta), auto-sizes positions, executes limit orders with spread checks, and monitors exits — all through your Public.com brokerage account.
env: ['PUBLIC_COM_SECRET', 'PUBLIC_COM_ACCOUNT_ID']
license: Apache-2.0
metadata:
  author: stevenartzt
  category: "Finance"
  tags: ["options", "trading", "greeks", "scanner", "public.com", "copilot", "automation"]
  version: "1.0"
---

# Options Copilot for Public.com

> ⚠️ **Not financial advice.** For educational and informational purposes only. Options involve significant risk. Do your own research.

AI-powered options trading copilot that chains **12 Public.com API capabilities** into one intelligent workflow: scan → score → size → execute → monitor → exit.

## Prerequisites

```bash
pip install publicdotcom-py yfinance numpy
```

## Configuration

### API Secret (Required)
```
openclaw config set skills.public-options-copilot.PUBLIC_COM_SECRET [YOUR_KEY]
```
Get your API key at: https://public.com/settings/v2/api

### Account ID (Required)
```
openclaw config set skills.public-options-copilot.PUBLIC_COM_ACCOUNT_ID [YOUR_ID]
```

## Capabilities

This skill chains these Public.com SDK methods:

| Method | How It's Used |
|--------|--------------|
| `get_portfolio()` | Check positions, buying power, current exposure |
| `get_quotes()` | Real-time bid/ask/last for any stock or option |
| `get_option_chain()` | Full chain with all strikes and pricing |
| `get_option_expirations()` | Available expiration dates |
| `get_option_greeks()` | Real delta, gamma, theta, vega, IV per contract |
| `get_accounts()` | Account info and buying power |
| `get_history()` | Trade history and performance |
| `perform_preflight_calculation()` | Preview order before executing (fees, margin check) |
| `perform_multi_leg_preflight_calculation()` | Preview credit spreads before executing |
| `place_order()` | Execute single-leg options orders |
| `place_multileg_order()` | Execute credit spreads (put/call spreads) |
| `cancel_order()` | Cancel open orders |

## Commands

### Scan for Opportunities
When the user asks to "scan for options", "find trades", or "what looks good":

```bash
python3 scripts/scan.py --symbols AAPL,NVDA,TSLA,META --min-score 72
```

Scans option chains and scores each opportunity using a 12-factor composite system with **real Greeks** from the API:
- Directional alignment (trend must match option type)
- Trend strength (momentum confirmation)
- IV analysis (using real implied volatility, not estimates)
- Delta band scoring (using real delta from Greeks API)
- RSI, MACD, volume confirmation
- Bid/ask spread check (rejects illiquid options)
- Daily/weekly range position (avoids buying at extremes)

### Check Portfolio
When the user asks "what do I own", "show positions", or "portfolio status":

```bash
python3 scripts/portfolio.py
```

Shows current positions with real-time P/L, Greeks exposure, and risk metrics.

### Execute a Trade
When the user says "buy", "enter", or "trade this signal":

```bash
python3 scripts/trade.py --symbol NVDA260327P00180000 --side buy --quantity 2
```

Safety workflow:
1. Gets real-time quote (bid/ask spread check)
2. Calculates optimal limit price (midpoint, not ask)
3. Auto-sizes position ($300-500, max $75 risk at 15% stop)
4. Runs preflight calculation (buying power, fees)
5. Shows preview and asks for confirmation
6. Places limit order (never market orders)

### Execute a Credit Spread
When the user wants to "sell a spread", "credit spread", or "theta play":

```bash
python3 scripts/spread.py --underlying AAPL --type put_credit --width 5 --dte 21
```

1. Gets option chain for the underlying
2. Finds optimal strikes using real Greeks (sell ~30 delta)
3. Calculates real credit from bid/ask
4. Checks R/R ratio (minimum 1:4)
5. Runs multi-leg preflight
6. Executes via `place_multileg_order()`

### Monitor Positions
When the user says "watch my trades", "monitor", or "start exit bot":

```bash
python3 scripts/monitor.py --continuous
```

Checks every 30 seconds:
- Current price vs entry (real-time quotes)
- +20% profit target → auto-exit
- -15% stop loss → auto-exit
- Stock at daily/weekly high (calls) or low (puts) → take profit
- 3:45 PM → close all before market close
- All exits use limit orders

### Trade History & Performance
When the user asks "how am I doing", "trade history", or "performance":

```bash
python3 scripts/history.py
```

Shows win rate, total P/L, average win/loss, best/worst trades.

## Safety & Security

- **All keys in environment variables** — never hardcoded
- **Preflight before every order** — verifies buying power, shows fees
- **Limit orders only** — never market orders, avoids slippage
- **Spread check** — rejects options with bid/ask spread > 10%
- **Position limits** — max 3 concurrent positions, $300-500 each
- **Confirmation required** — shows preview before executing
- **Read-only mode** — set `COPILOT_READ_ONLY=true` to disable order placement

## 12-Factor Scoring Engine

Each option is scored 0-100 using real market data:

| # | Factor | Max Pts | Data Source |
|---|--------|---------|-------------|
| 1 | Directional Alignment | 25 | Trend analysis |
| 2 | Trend Strength | 12 | Price vs SMA20/50 |
| 3 | IV Analysis | 15 | **Real IV from Greeks API** |
| 4 | RSI Confirmation | 8 | 14-period RSI |
| 5 | Delta Band | 12 | **Real delta from Greeks API** |
| 6 | Unusual Volume | 10 | Volume/OI ratio |
| 7 | Liquidity | 6 | Bid/ask spread |
| 8 | Optimal DTE | 6 | Days to expiration |
| 9 | Affordability | 6 | Option price vs account size |
| 10 | Regime Check | Gate | ADX trend/chop detection |
| 11 | Range Position | -15 to 0 | Daily/weekly high-low |
| 12 | Spread Gate | Gate | Bid/ask > 10% = reject |

Signals scoring **72+** are flagged as opportunities.

## Example Workflows

### Morning Scan
```
User: "Scan the S&P 500 for options opportunities"
→ Scans 50+ tickers
→ Gets option chains + real Greeks
→ Scores all options
→ Returns top 5 by score with full breakdown
```

### Quick Trade
```
User: "Buy the top NVDA put signal"
→ Finds best scored NVDA put
→ Shows: $180P, score 82, delta -0.39, IV 38.5%
→ Calculates: 2 contracts, $340 cost, limit $1.70
→ Runs preflight: buying power OK, $0.65 commission
→ User confirms → order placed
```

### Hedge Portfolio
```
User: "I'm worried about a market drop, hedge my portfolio"
→ Checks portfolio (get_portfolio)
→ Identifies long equity exposure
→ Finds protective put or put spread
→ Previews cost vs protection
→ Executes on confirmation
```
