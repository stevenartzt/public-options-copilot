# Options Copilot

**Public.com Options Trading Competition Entry**

A comprehensive options trading assistant featuring real-time analysis, paper trading, and live trading integration with Public.com.

![Dashboard](https://via.placeholder.com/800x400?text=Options+Copilot+Dashboard)

## Features

### 📊 Dashboard
- Real-time VIX and SPY monitoring
- Per-sector market sentiment analysis
- Market breadth indicators
- No API key required - uses free yfinance data

### 💼 Portfolio Management
- **Real Portfolio**: View your Public.com positions with live P/L
- **Paper Portfolio**: Practice trading with $10,000 virtual funds
- Position tracking with Greeks and key metrics

### 📈 Trading
- Ticker search with full technical analysis
- Interactive price charts with indicators (SMA, EMA, Bollinger Bands, MACD, RSI)
- Option chain viewer with bid/ask, volume, and open interest
- One-click order placement

### 🔍 Options Scanner
- Edge-based signal generation (STRONG_BUY, BUY)
- Directional alignment (calls on uptrend, puts on downtrend)
- IV rank scoring (buy low IV)
- Win probability estimation
- Preset watchlists (Tech, Finance, Healthcare, Energy, etc.)

### 📝 Paper Trading
- Virtual portfolio starting at $10,000
- Full trade history with P/L tracking
- Win/loss statistics
- Reset capability for fresh starts

### ⚡ SPY Scalper Game
- Real-time SPY price tracking
- Buy/Sell with immediate feedback
- Session P/L and high score tracking
- Fun gamification element

### ⚙️ Settings
- API credential management
- Toggleable chart indicators

## Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/stevenartzt/public-options-copilot.git
cd public-options-copilot
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment (Optional)
For live trading, copy `.env.example` to `.env` and add your credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```
PUBLIC_COM_SECRET=your_api_secret_here
PUBLIC_COM_ACCOUNT_ID=your_account_id_here
```

**Note**: The app works without API credentials - paper trading, sentiment, and charts are fully functional using yfinance.

### 5. Run the Application
```bash
python app.py
```

Or with host binding for LAN access:
```bash
python app.py --host 0.0.0.0 --port 5006
```

### 6. Open in Browser
Navigate to: `http://127.0.0.1:5006`

## Project Structure

```
public-options-copilot/
├── app.py                    # Flask entry point
├── config.py                 # Configuration and feature flags
├── requirements.txt          # Dependencies
├── README.md                 # This file
├── .env.example              # Environment template
├── .gitignore
├── services/
│   ├── __init__.py
│   ├── portfolio.py          # Public SDK portfolio management
│   ├── trading.py            # Order placement
│   ├── scanner.py            # Options scanner with edge scoring
│   ├── paper_trading.py      # Virtual portfolio engine
│   ├── market_data.py        # yfinance data provider
│   ├── sentiment.py          # Sector sentiment analysis
│   ├── analysis.py           # Technical analysis (RSI, MACD, etc.)
│   └── indicators.py         # Chart indicator computation
├── static/
│   ├── css/
│   │   └── style.css         # Dark theme styling
│   └── js/
│       └── app.js            # Frontend logic
├── templates/
│   └── index.html            # Single page app
└── data/
    └── paper_state.json      # Paper trading state (auto-created)
```

## Technical Details

### Scanner Algorithm
The options scanner uses edge-based scoring:
- **Directional Alignment**: Only CALLS on uptrend, PUTS on downtrend
- **IV Rank**: Prefer low IV (buy cheap options)
- **Trend Strength**: Weight signals by trend confidence
- **Delta Targeting**: Optimal delta range (0.30-0.50)
- **Liquidity Filters**: Minimum volume, OI, and spread requirements
- **Regime Detection**: Skip choppy markets (low ADX)

### Sentiment Analysis
Free data sources (no paid APIs):
- VIX level and interpretation
- Sector ETF performance (XLK, XLF, XLV, etc.)
- Put/call ratio estimation from SPY options
- Advance/decline breadth

### Technical Indicators
- RSI (14-period)
- MACD (12/26/9)
- Bollinger Bands (20-period, 2 std)
- SMA (20, 50)
- EMA (9)
- ATR (14-period)
- ADX (14-period)

## API Endpoints

### Market Data
- `GET /api/quote/<symbol>` - Get quote
- `GET /api/chart/<symbol>` - Get chart data with indicators
- `GET /api/options/<symbol>/expirations` - Get expiration dates
- `GET /api/options/<symbol>/chain` - Get option chain

### Analysis
- `GET /api/analysis/<symbol>` - Get technical analysis
- `GET /api/sentiment` - Get market sentiment

### Scanner
- `POST /api/scanner/scan` - Scan for options
- `GET /api/scanner/watchlist` - Get watchlist
- `POST /api/scanner/preset/<name>` - Use preset watchlist

### Paper Trading
- `GET /api/paper/portfolio` - Get paper portfolio
- `POST /api/paper/buy` - Paper buy
- `POST /api/paper/sell` - Paper sell
- `POST /api/paper/reset` - Reset portfolio

### Real Trading (requires API key)
- `GET /api/portfolio` - Get real portfolio
- `POST /api/order/preflight` - Preview order
- `POST /api/order/place` - Place order
- `GET /api/orders/open` - Get open orders

### SPY Scalper
- `GET /api/game/spy` - Get game state
- `POST /api/game/spy/buy` - Buy SPY
- `POST /api/game/spy/sell` - Sell SPY
- `POST /api/game/spy/reset` - Reset game

## Requirements
- Python 3.9+
- Flask 2.0+
- yfinance 0.2+
- publicdotcom-py (for live trading)

## License
MIT

## Acknowledgments
Built for the Public.com Options Trading Competition, March 2026.
