"""
Market Data Service - yfinance-based market data provider.
Primary data source that works without API keys.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import json

try:
    import yfinance as yf
    import pandas as pd
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    yf = None
    pd = None


class MarketDataService:
    """Provides market data via yfinance (free, no API key required)."""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=1)
    
    def _is_cached(self, key: str) -> bool:
        """Check if data is in cache and still valid."""
        if key not in self._cache:
            return False
        if datetime.now() - self._cache_times.get(key, datetime.min) > self._cache_duration:
            return False
        return True
    
    def _set_cache(self, key: str, value: Any):
        """Store value in cache."""
        self._cache[key] = value
        self._cache_times[key] = datetime.now()
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get current quote for a symbol."""
        if not HAS_YFINANCE:
            return None
        
        cache_key = f"quote:{symbol}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            quote = {
                'symbol': symbol,
                'price': info.get('regularMarketPrice') or info.get('currentPrice'),
                'previous_close': info.get('previousClose'),
                'open': info.get('open'),
                'high': info.get('dayHigh'),
                'low': info.get('dayLow'),
                'volume': info.get('volume'),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
                'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
                'name': info.get('shortName') or info.get('longName'),
                'sector': info.get('sector'),
                'industry': info.get('industry')
            }
            
            # Calculate change
            if quote['price'] and quote['previous_close']:
                quote['change'] = quote['price'] - quote['previous_close']
                quote['change_percent'] = (quote['change'] / quote['previous_close']) * 100
            else:
                quote['change'] = 0
                quote['change_percent'] = 0
            
            self._set_cache(cache_key, quote)
            return quote
        except Exception as e:
            print(f"Error getting quote for {symbol}: {e}")
            return None
    
    def get_history(self, symbol: str, period: str = "60d", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Get historical price data."""
        if not HAS_YFINANCE:
            return None
        
        cache_key = f"history:{symbol}:{period}:{interval}"
        if self._is_cached(cache_key):
            return self._cache[cache_key]
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            
            if not hist.empty:
                self._set_cache(cache_key, hist)
            return hist
        except Exception as e:
            print(f"Error getting history for {symbol}: {e}")
            return None
    
    def get_intraday(self, symbol: str, period: str = "1d", interval: str = "5m") -> Optional[pd.DataFrame]:
        """Get intraday price data."""
        if not HAS_YFINANCE:
            return None
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            return hist if not hist.empty else None
        except Exception as e:
            print(f"Error getting intraday for {symbol}: {e}")
            return None
    
    def get_option_chain(self, symbol: str, expiration: Optional[str] = None) -> Optional[Dict]:
        """Get option chain for a symbol."""
        if not HAS_YFINANCE:
            return None
        
        try:
            ticker = yf.Ticker(symbol)
            
            # Get available expirations
            expirations = list(ticker.options) if ticker.options else []
            
            if not expirations:
                return None
            
            # Use provided expiration or first available
            target_exp = expiration if expiration in expirations else expirations[0]
            
            chain = ticker.option_chain(target_exp)
            
            # Convert to serializable format
            calls = []
            for _, row in chain.calls.iterrows():
                calls.append({
                    'strike': float(row['strike']),
                    'last': float(row['lastPrice']) if not pd.isna(row['lastPrice']) else None,
                    'bid': float(row['bid']) if not pd.isna(row['bid']) else None,
                    'ask': float(row['ask']) if not pd.isna(row['ask']) else None,
                    'volume': int(row['volume']) if not pd.isna(row['volume']) else 0,
                    'open_interest': int(row['openInterest']) if not pd.isna(row['openInterest']) else 0,
                    'implied_volatility': float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else None,
                    'in_the_money': bool(row['inTheMoney']) if 'inTheMoney' in row else None
                })
            
            puts = []
            for _, row in chain.puts.iterrows():
                puts.append({
                    'strike': float(row['strike']),
                    'last': float(row['lastPrice']) if not pd.isna(row['lastPrice']) else None,
                    'bid': float(row['bid']) if not pd.isna(row['bid']) else None,
                    'ask': float(row['ask']) if not pd.isna(row['ask']) else None,
                    'volume': int(row['volume']) if not pd.isna(row['volume']) else 0,
                    'open_interest': int(row['openInterest']) if not pd.isna(row['openInterest']) else 0,
                    'implied_volatility': float(row['impliedVolatility']) if not pd.isna(row['impliedVolatility']) else None,
                    'in_the_money': bool(row['inTheMoney']) if 'inTheMoney' in row else None
                })
            
            return {
                'symbol': symbol,
                'expiration': target_exp,
                'expirations': expirations,
                'calls': calls,
                'puts': puts,
                'underlying_price': self.get_quote(symbol).get('price') if self.get_quote(symbol) else None
            }
        except Exception as e:
            print(f"Error getting option chain for {symbol}: {e}")
            return None
    
    def get_option_expirations(self, symbol: str, include_dte: bool = False) -> List:
        """Get available option expiration dates."""
        if not HAS_YFINANCE:
            return []
        
        try:
            ticker = yf.Ticker(symbol)
            expirations = list(ticker.options) if ticker.options else []
            
            if not include_dte:
                return expirations
            
            # Return with days_to_expiry
            today = datetime.now().date()
            result = []
            for exp in expirations:
                exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
                dte = (exp_date - today).days
                result.append({
                    'date': exp,
                    'days_to_expiry': dte
                })
            return result
        except Exception as e:
            print(f"Error getting expirations for {symbol}: {e}")
            return []
    
    def get_nearest_expiration(self, symbol: str, target_dte: int) -> Optional[Dict]:
        """Find the closest expiration to a target DTE."""
        if not HAS_YFINANCE:
            return None
        
        try:
            expirations = self.get_option_expirations(symbol, include_dte=True)
            if not expirations:
                return None
            
            # Find closest expiration to target_dte
            closest = min(expirations, key=lambda x: abs(x['days_to_expiry'] - target_dte))
            return closest
        except Exception as e:
            print(f"Error getting nearest expiration for {symbol}: {e}")
            return None
    
    def get_spy_price(self) -> Optional[float]:
        """Get current SPY price (for scalper game)."""
        quote = self.get_quote('SPY')
        return quote.get('price') if quote else None
    
    def get_vix(self) -> Optional[Dict]:
        """Get VIX data for sentiment analysis."""
        quote = self.get_quote('^VIX')
        if not quote:
            return None
        
        # Interpret VIX levels
        vix_level = quote.get('price', 0)
        if vix_level < 12:
            interpretation = 'Extremely Low (Complacency)'
        elif vix_level < 18:
            interpretation = 'Low (Calm)'
        elif vix_level < 25:
            interpretation = 'Moderate (Normal)'
        elif vix_level < 35:
            interpretation = 'Elevated (Concern)'
        else:
            interpretation = 'High (Fear)'
        
        return {
            'value': vix_level,
            'change': quote.get('change'),
            'change_percent': quote.get('change_percent'),
            'interpretation': interpretation
        }


# Singleton instance
_market_data_service = None

def get_market_data_service() -> MarketDataService:
    """Get the singleton market data service instance."""
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = MarketDataService()
    return _market_data_service
