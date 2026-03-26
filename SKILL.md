---
id: options-copilot
name: Options Copilot
description: AI-powered options trading dashboard with portfolio management, edge-based scanning, algo backtesting, paper trading, and market sentiment analysis — all built on the Public.com API. Includes a local web dashboard and agent commands for portfolio queries, trade execution, and market analysis.
env: ['PUBLIC_COM_SECRET', 'PUBLIC_COM_ACCOUNT_ID']
license: Apache-2.0
metadata:
  author: stevenartzt
  category: "Finance"
  tags: ["options", "trading", "portfolio", "scanner", "backtesting", "paper-trading", "sentiment", "public-dot-com"]
  version: "1.0.0"
---

# Options Copilot — Public.com Trading Dashboard
> **Disclaimer:** For illustrative and informational purposes only. Not investment advice or recommendations.

A comprehensive options trading copilot that combines real-time portfolio management, edge-based options scanning, algorithmic strategy backtesting, paper trading, and market sentiment analysis — all powered by the Public.com API.

## Features

- **📊 Dashboard** — Market overview with per-sector sentiment (11 sectors via ETF data), VIX monitoring, and SPY tracking
- **💼 Portfolio** — Real-time positions, P/L tracking, Greeks, allocation via Public.com SDK
- **📈 Trading** — Ticker analysis with technical indicators, option chain browser with DTE quick-picks, order placement
- **🔍 Scanner** — Edge-based options signal generator scoring on directional alignment, IV rank, delta, volume, and win probability
- **📝 Paper Trading** — Virtual $10,000 portfolio for risk-free practice with full P/L tracking
- **🤖 Algo Trading** — Define entry/exit strategies, backtest on historical data, compare multiple strategies side by side
- **⚡ SPY Scalper** — Gamified 0DTE options practice with nearest-strike call/put buttons
- **❓ Help** — In-app documentation for every feature

## Prerequisites

The `publicdotcom-py` SDK is required for live trading features:
```bash
pip install publicdotcom-py==0.1.10
```

**Note:** The dashboard works WITHOUT API credentials. Paper trading, backtesting, sentiment analysis, and the SPY scalper all function using free yfinance market data.

## Configuration

### API Secret (Required for live trading)
If the environment variable `PUBLIC_COM_SECRET` is not set:
- Tell the user: "I need your Public.com API Secret. You can find this at https://public.com/settings/v2/api"
- Once provided, save it: `openclaw config set skills.options-copilot.PUBLIC_COM_SECRET [VALUE]`

### Account ID (Required for live trading)
- Save it: `openclaw config set skills.options-copilot.PUBLIC_COM_ACCOUNT_ID [VALUE]`
- Find your account ID at https://public.com/settings/v2/api

### Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `PUBLIC_COM_SECRET` | For live trading | Public.com API secret key |
| `PUBLIC_COM_ACCOUNT_ID` | For live trading | Public.com account ID |

Both can be set in a `.env` file in the project root (see `.env.example`).

## Setup & Running

```bash
# Clone the repository
git clone https://github.com/stevenartzt/public-options-copilot.git
cd public-options-copilot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials (optional — for live trading only)
cp .env.example .env
# Edit .env with your Public.com API credentials

# Launch the dashboard
python app.py
```

Open **http://localhost:5006** in your browser.

## Available Agent Commands

### Portfolio Queries
When the user asks "show my portfolio", "what are my positions", or "how's my account":
```bash
python scripts/get_portfolio.py
```
Returns: account value, buying power, cash, all positions with P/L.

### Stock Analysis
When the user asks "analyze AAPL", "what's the trend on NVDA", or "should I buy TSLA":
```bash
python -c "from services.analysis import TechnicalAnalyzer; a = TechnicalAnalyzer(); print(a.analyze('AAPL'))"
```
Returns: RSI, MACD, ATR%, ADX, trend direction, regime, support/resistance.

### Market Sentiment
When the user asks "how's the market", "sector sentiment", or "what's the VIX":
```bash
python -c "from services.sentiment import SentimentService; s = SentimentService(); print(s.get_sentiment().to_dict())"
```
Returns: per-sector sentiment (11 sectors), VIX level, market breadth.

### Options Scanning
When the user asks "find options", "scan for plays", or "what's the best setup":
```bash
python -c "from services.scanner import OptionsScanner; s = OptionsScanner(); print(s.scan_options(['AAPL','NVDA','SPY']))"
```
Returns: ranked options by edge score, directional alignment, IV rank, win probability.

### Paper Trading
When the user asks "paper trade AAPL", "buy 10 shares of MSFT in paper":
```bash
python -c "from services.paper_trading import PaperTradingService; p = PaperTradingService(); p.buy('AAPL', 10)"
```
Returns: updated paper portfolio with P/L tracking.

### Algo Backtesting
When the user asks "backtest RSI strategy on SPY", "compare strategies":
```bash
python -c "from services.algo_trading import AlgoTradingService; a = AlgoTradingService(); print(a.get_strategies())"
```
Returns: strategy list, backtest results with equity curves and metrics.

### Place Order (Live Trading)
When the user asks "buy 1 AAPL call" or "sell my NVDA position":
- **ALWAYS** confirm with the user before placing any order
- Use `perform_preflight_calculation()` to preview order first
- Show estimated cost, fees, and confirm
- Only then execute via `place_order()`

⚠️ **Safety:** Never place orders without explicit user confirmation. Always show the preflight preview first.

## Dashboard Sections

| Section | Description | Requires API Key? |
|---------|-------------|-------------------|
| Dashboard | Market overview + sentiment | No |
| Portfolio | Real positions + P/L | Yes |
| Trading | Analysis + option chain + orders | Analysis: No, Orders: Yes |
| Scanner | Edge-based signal finder | No (yfinance), Yes (real Greeks) |
| Paper Trading | Virtual portfolio | No |
| Algo Trading | Strategy builder + backtester | No |
| SPY Scalper | Practice game | No |
| Settings | API config + preferences | No |

## Architecture

```
public-options-copilot/
├── app.py                     # Flask routes (minimal)
├── config.py                  # Configuration + defaults
├── services/
│   ├── analysis.py            # Technical analysis (RSI, MACD, ATR, ADX, BB)
│   ├── sentiment.py           # Sector sentiment via ETF data
│   ├── scanner.py             # Edge-based options scanner
│   ├── paper_trading.py       # Virtual portfolio engine
│   ├── portfolio.py           # Real portfolio via Public SDK
│   ├── trading.py             # Order placement via Public SDK
│   ├── market_data.py         # yfinance data provider
│   ├── algo_trading.py        # Strategy engine + backtester
│   └── indicators.py          # Chart indicator toggles
├── static/css/style.css       # Dark theme UI
├── static/js/app.js           # Frontend logic
├── templates/index.html       # Single-page app
└── data/                      # Local storage (paper trades, strategies)
```

## Security & Safety

- **API keys stored in `.env` file** — never hardcoded, never committed to git
- **`.env` is in `.gitignore`** — credentials never pushed to repository
- **Live trading requires explicit toggle** — paper mode is default
- **Order preflight** — always preview before executing
- **Works without credentials** — 6 of 8 features work with zero API access
- **No external data sharing** — all data stays local
- **Rate limiting** — respects Public.com API limits

## Public.com SDK Integration

The following SDK methods are used:

| Method | Feature | Description |
|--------|---------|-------------|
| `get_portfolio()` | Portfolio | Real-time positions and equity |
| `get_accounts()` | Portfolio | Account info and buying power |
| `get_quotes()` | Trading | Live stock prices |
| `get_option_chain()` | Trading | Full option chain by expiration |
| `get_option_expirations()` | Trading | Available expiration dates |
| `get_option_greeks()` | Scanner | Real delta, gamma, theta, vega, IV |
| `place_order()` | Trading | Execute stock and option orders |
| `perform_preflight_calculation()` | Trading | Preview order before execution |
| `get_order()` | Orders | Check order status |
| `cancel_order()` | Orders | Cancel open orders |

## Example OpenClaw Workflows

### 1. Morning Market Brief
**User:** "Give me a morning market brief"
**Agent:** Runs sentiment analysis + portfolio check
```
→ Dashboard: Sector sentiment cards load (11 sectors)
→ VIX at 25.5 — Elevated (Concern)
→ Leading sectors: Energy (+2.0%), Materials (+1.9%)
→ Lagging: Real Estate (-0.1%), Communication (+0.3%)
→ Portfolio: 3 positions, +$322 today
```

### 2. Analyze a Stock Before Trading
**User:** "Should I buy NVDA calls?"
**Agent:** Runs technical analysis + options scan
```
→ Trading tab: NVDA analysis loads
→ Trend: BEARISH (100%), RSI: 38, ADX: 29, Regime: TRENDING
→ Option chain: nearest expirations with ATM highlighted
→ Scanner: NVDA puts score 74 (bearish alignment)
→ Recommendation: "NVDA is bearish. Consider puts instead of calls."
```

### 3. Paper Trade Practice
**User:** "Paper trade 10 shares of AAPL"
**Agent:** Executes paper buy
```
→ Paper Trading: Bought 10 AAPL @ $217.50
→ Portfolio updated: $7,825 cash, 1 position
→ P/L tracking starts automatically
```

### 4. Backtest a Strategy
**User:** "Backtest RSI mean reversion on SPY for the last year"
**Agent:** Runs algo backtest
```
→ Algo Trading: RSI Mean Reversion selected
→ Backtest results: 28 trades, 50% WR, -0.2% return
→ Equity curve chart rendered
→ Trade log with entry/exit dates and P/L
```

### 5. Compare Strategies
**User:** "Which strategy works better — RSI or MACD?"
**Agent:** Runs comparison backtest
```
→ Compare tab: Both strategies selected
→ Overlaid equity curves (RSI in blue, MACD in green)
→ Comparison table: RSI 50% WR vs MACD 0% WR
→ Winner highlighted per metric
```

### 6. Quick SPY Scalp
**User:** "Let me practice SPY scalping"
**Agent:** Opens SPY Scalper game
```
→ SPY Scalper: Live price $660.50
→ Buttons: BUY $661 CALL ($1.50) / BUY $660 PUT ($1.50)
→ Click to enter, click to close
→ Session P/L tracks performance
```

### 7. Full Trading Flow
**User:** "Find me the best options play right now"
**Agent:** Runs full pipeline
```
→ Scanner: Scans blue-chip watchlist (90 tickers)
→ Results: 3 calls, 5 puts ranked by edge score
→ Top pick: AAPL $217.50 PUT, score 77, WR 58%
→ User clicks: Order modal opens with preflight preview
→ Confirms: Order placed via Public.com API
```
