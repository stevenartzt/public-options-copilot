"""
Configuration for Options Copilot
All settings, defaults, and feature flags in one place.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration."""
    
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    # Public.com API
    PUBLIC_API_KEY = os.getenv('PUBLIC_COM_SECRET', '')
    PUBLIC_ACCOUNT_ID = os.getenv('PUBLIC_COM_ACCOUNT_ID', '')
    
    # Feature flags
    ENABLE_REAL_TRADING = bool(PUBLIC_API_KEY and PUBLIC_ACCOUNT_ID)
    ENABLE_PAPER_TRADING = True  # Always available
    ENABLE_SENTIMENT = True
    ENABLE_SPY_GAME = True
    
    # Paper trading defaults
    PAPER_STARTING_BALANCE = 10000.00
    
    # Market data settings
    PRICE_REFRESH_INTERVAL = 5  # seconds
    CACHE_DURATION_MINUTES = 5
    
    # Scanner defaults
    DEFAULT_MIN_VOLUME = 50
    DEFAULT_MIN_OI = 100
    DEFAULT_MAX_DTE = 45
    DEFAULT_SCAN_LIMIT = 10
    
    # Technical analysis settings
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    ADX_PERIOD = 14
    ATR_PERIOD = 14
    
    # Data paths
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    PAPER_STATE_FILE = os.path.join(DATA_DIR, 'paper_state.json')
    
    # Sector ETFs for sentiment analysis
    SECTOR_ETFS = {
        'Technology': 'XLK',
        'Financials': 'XLF',
        'Healthcare': 'XLV',
        'Energy': 'XLE',
        'Consumer Discretionary': 'XLY',
        'Industrials': 'XLI',
        'Materials': 'XLB',
        'Utilities': 'XLU',
        'Real Estate': 'XLRE',
        'Consumer Staples': 'XLP',
        'Communication': 'XLC'
    }
    
    # Watchlist presets
    WATCHLIST_PRESETS = {
        'default': ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'AMD', 'AMZN', 'META', 'MSFT', 'GOOGL'],
        'bluechip': [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'JPM', 'V', 'JNJ',
            'UNH', 'WMT', 'PG', 'XOM', 'CVX', 'HD', 'MA', 'BAC', 'PFE', 'KO'
        ],
        'tech': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'AMD', 'TSLA', 'CRM', 'ORCL', 'ADBE', 'INTC'],
        'finance': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'V', 'MA', 'BLK', 'SCHW'],
        'healthcare': ['UNH', 'JNJ', 'PFE', 'ABBV', 'LLY', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY'],
        'energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO'],
        'volatile': ['TSLA', 'NVDA', 'AMD', 'COIN', 'MARA', 'RIOT', 'PLTR', 'SOFI', 'GME', 'AMC']
    }


def get_api_key():
    """Get Public.com API key."""
    return Config.PUBLIC_API_KEY


def get_account_id():
    """Get Public.com account ID."""
    return Config.PUBLIC_ACCOUNT_ID


def has_api_credentials():
    """Check if API credentials are configured."""
    return bool(Config.PUBLIC_API_KEY and Config.PUBLIC_ACCOUNT_ID)
