# Options Copilot — Public.com Trading Dashboard

A powerful options trading dashboard built for the Public.com Options Competition. Features real-time portfolio tracking, options trading, strategy backtesting, paper trading, and a gamified SPY scalping game.

![Dashboard Preview](https://img.shields.io/badge/Status-Competition%20Ready-brightgreen)

## Features

### 💼 Portfolio View
- Real-time positions with P/L tracking
- Account equity and buying power
- Visual allocation charts
- Open orders management

### 📊 Trading Interface
- Ticker search with live quotes
- Interactive price charts
- Option chain browser (calls/puts grid)
- One-click order placement
- Stock and options trading

### 🧪 Strategy Backtester
- Pre-built strategies: SMA Crossover, RSI Mean Reversion, Breakout
- Custom parameter tuning
- Performance metrics: Sharpe ratio, max drawdown, win rate, profit factor
- Visual equity curves
- Trade history analysis

### 📝 Paper Trading
- Virtual $10,000 portfolio
- Simulated trades using real market data
- P/L tracking and win/loss statistics
- Forward test strategies risk-free

### ⚡ SPY Scalper Game
- Real-time SPY price tracking
- Gamified trading practice
- Session P/L and trade statistics
- High score leaderboard

### 🎯 Strategy Manager
- Save and manage backtested strategies
- Toggle between paper and live modes
- Push winning strategies to production

## Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/stevenartzt/public-options-copilot.git
cd public-options-copilot
```

### 2. Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API credentials
```bash
cp .env.example .env
# Edit .env with your Public.com API credentials
```

Get your API key from [Public.com Settings](https://public.com/settings/api).

### 5. Run the dashboard
```bash
python app.py
```

Open your browser to: **http://localhost:5006**

## Configuration

Create a `.env` file in the project root:

```env
PUBLIC_COM_SECRET=your_api_secret_here
PUBLIC_COM_ACCOUNT_ID=your_account_id_here
```

**Without API credentials**, the dashboard will still work with:
- Paper trading (simulated)
- Strategy backtesting (yfinance data)
- SPY Scalper game
- Option chains via yfinance

**With API credentials**, you get:
- Real portfolio data
- Live order placement
- Real-time positions and P/L
- Full option chain data

## Architecture

```
public-options-copilot/
├── app.py              # Flask application (all-in-one)
├── requirements.txt    # Python dependencies
├── .env               # API credentials (git-ignored)
├── .env.example       # Template for credentials
├── data/              # Persistent data (git-ignored)
│   ├── paper_portfolio.json
│   ├── paper_trades.json
│   ├── strategies.json
│   └── scalper_scores.json
└── README.md
```

## Tech Stack

- **Backend**: Flask (Python)
- **Frontend**: Vanilla JS + Plotly.js
- **Market Data**: yfinance
- **Trading API**: Public.com SDK (publicdotcom-py)
- **Charts**: Plotly.js

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/portfolio` | GET | Get live portfolio |
| `/api/quote/<ticker>` | GET | Get stock quote |
| `/api/chart/<ticker>` | GET | Get price history |
| `/api/expirations/<ticker>` | GET | Get option expirations |
| `/api/chain/<ticker>/<exp>` | GET | Get option chain |
| `/api/order/stock` | POST | Place stock order |
| `/api/order/option` | POST | Place option order |
| `/api/backtest` | POST | Run backtest |
| `/api/paper/portfolio` | GET | Get paper portfolio |
| `/api/paper/trade` | POST | Execute paper trade |
| `/api/paper/reset` | POST | Reset paper portfolio |
| `/api/scalper/scores` | GET | Get scalper scores |
| `/api/strategies` | GET | Get saved strategies |

## Usage Tips

### Backtesting
1. Select a strategy type (SMA Crossover, RSI, Breakout)
2. Adjust parameters for your hypothesis
3. Click "Run" to see results
4. Review equity curve and trade history
5. Save promising strategies

### Paper Trading
1. Enter a ticker and quantity
2. Click BUY or SELL
3. Monitor positions in the table
4. Close positions when ready
5. Track your win/loss ratio

### SPY Scalper
1. Watch the real-time SPY price
2. Click BUY to go long, SELL to go short
3. Click the opposite button to close and realize P/L
4. Try to beat your high score!

## License

MIT License — Built for the Public.com Options Competition 2026

## Author

Created by [stevenartzt](https://github.com/stevenartzt)
