"""
Market Sentiment Service
Per-sector sentiment using FREE data (yfinance only, no LLMs, no paid APIs).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    import yfinance as yf
    import pandas as pd
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


@dataclass
class SectorSentiment:
    """Sentiment data for a single sector."""
    sector: str
    etf: str
    price: float
    change_pct: float
    week_change_pct: float
    month_change_pct: float
    sentiment: str  # BULLISH, BEARISH, NEUTRAL
    strength: int  # 1-5 scale
    icon: str
    reasons: List[str]
    
    def to_dict(self) -> dict:
        return {
            'sector': self.sector,
            'etf': self.etf,
            'price': round(self.price, 2),
            'change_pct': round(self.change_pct, 2),
            'week_change_pct': round(self.week_change_pct, 2),
            'month_change_pct': round(self.month_change_pct, 2),
            'sentiment': self.sentiment,
            'strength': self.strength,
            'icon': self.icon,
            'reasons': self.reasons
        }


@dataclass
class MarketSentiment:
    """Overall market sentiment."""
    overall_sentiment: str
    overall_strength: int
    vix: Dict[str, Any]
    sectors: List[SectorSentiment]
    market_breadth: Dict[str, Any]
    put_call_ratio: Optional[float]
    timestamp: str
    
    def to_dict(self) -> dict:
        return {
            'overall_sentiment': self.overall_sentiment,
            'overall_strength': self.overall_strength,
            'vix': self.vix,
            'sectors': [s.to_dict() for s in self.sectors],
            'market_breadth': self.market_breadth,
            'put_call_ratio': self.put_call_ratio,
            'timestamp': self.timestamp
        }


class SentimentService:
    """Analyzes market sentiment using free data sources."""
    
    # Sector ETF mapping
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
    
    # Sector icons
    SECTOR_ICONS = {
        'Technology': '💻',
        'Financials': '🏦',
        'Healthcare': '🏥',
        'Energy': '⛽',
        'Consumer Discretionary': '🛍️',
        'Industrials': '🏭',
        'Materials': '🧱',
        'Utilities': '💡',
        'Real Estate': '🏠',
        'Consumer Staples': '🛒',
        'Communication': '📱'
    }
    
    def __init__(self):
        self._cache: Optional[MarketSentiment] = None
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=5)
    
    def get_sentiment(self, force_refresh: bool = False) -> Optional[MarketSentiment]:
        """Get complete market sentiment analysis."""
        if not HAS_YFINANCE:
            return None
        
        # Check cache
        if not force_refresh and self._cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_duration:
                return self._cache
        
        try:
            # Get VIX data
            vix_data = self._get_vix()
            
            # Get sector data
            sectors = self._analyze_sectors()
            
            # Calculate market breadth
            breadth = self._calculate_breadth(sectors)
            
            # Estimate put/call ratio from SPY options
            put_call = self._estimate_put_call_ratio()
            
            # Calculate overall sentiment
            overall_sentiment, overall_strength = self._calculate_overall(
                vix_data, sectors, breadth, put_call
            )
            
            sentiment = MarketSentiment(
                overall_sentiment=overall_sentiment,
                overall_strength=overall_strength,
                vix=vix_data,
                sectors=sectors,
                market_breadth=breadth,
                put_call_ratio=put_call,
                timestamp=datetime.now().isoformat()
            )
            
            self._cache = sentiment
            self._cache_time = datetime.now()
            
            return sentiment
            
        except Exception as e:
            print(f"Error getting sentiment: {e}")
            return None
    
    def _get_vix(self) -> Dict[str, Any]:
        """Get VIX data and interpretation."""
        try:
            vix = yf.Ticker('^VIX')
            hist = vix.history(period='5d')
            
            if hist.empty:
                return {'value': 20, 'change': 0, 'interpretation': 'Normal', 'level': 'moderate'}
            
            current = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current
            change = current - prev
            change_pct = (change / prev) * 100 if prev else 0
            
            # Interpretation
            if current < 12:
                interpretation = 'Extremely Low (Complacency)'
                level = 'very_low'
            elif current < 18:
                interpretation = 'Low (Calm)'
                level = 'low'
            elif current < 25:
                interpretation = 'Moderate (Normal)'
                level = 'moderate'
            elif current < 35:
                interpretation = 'Elevated (Concern)'
                level = 'elevated'
            else:
                interpretation = 'High (Fear)'
                level = 'high'
            
            return {
                'value': round(current, 2),
                'change': round(change, 2),
                'change_pct': round(change_pct, 2),
                'interpretation': interpretation,
                'level': level
            }
        except Exception as e:
            print(f"Error getting VIX: {e}")
            return {'value': 20, 'change': 0, 'interpretation': 'Unknown', 'level': 'moderate'}
    
    def _analyze_sectors(self) -> List[SectorSentiment]:
        """Analyze all sectors."""
        sectors = []
        
        for sector_name, etf in self.SECTOR_ETFS.items():
            try:
                ticker = yf.Ticker(etf)
                hist = ticker.history(period='1mo')
                
                if hist.empty:
                    continue
                
                # Get prices
                current = float(hist['Close'].iloc[-1])
                prev_day = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current
                prev_week = float(hist['Close'].iloc[-5]) if len(hist) > 5 else current
                prev_month = float(hist['Close'].iloc[0])
                
                # Calculate changes
                day_change = ((current - prev_day) / prev_day) * 100 if prev_day else 0
                week_change = ((current - prev_week) / prev_week) * 100 if prev_week else 0
                month_change = ((current - prev_month) / prev_month) * 100 if prev_month else 0
                
                # Determine sentiment
                sentiment, strength, reasons = self._determine_sector_sentiment(
                    day_change, week_change, month_change
                )
                
                sectors.append(SectorSentiment(
                    sector=sector_name,
                    etf=etf,
                    price=current,
                    change_pct=day_change,
                    week_change_pct=week_change,
                    month_change_pct=month_change,
                    sentiment=sentiment,
                    strength=strength,
                    icon=self.SECTOR_ICONS.get(sector_name, '📊'),
                    reasons=reasons
                ))
                
            except Exception as e:
                print(f"Error analyzing {sector_name}: {e}")
                continue
        
        # Sort by day change
        sectors.sort(key=lambda x: x.change_pct, reverse=True)
        
        return sectors
    
    def _determine_sector_sentiment(self, day_change: float, week_change: float, month_change: float) -> tuple:
        """Determine sentiment for a sector."""
        score = 0
        reasons = []
        
        # Day change
        if day_change > 1.5:
            score += 2
            reasons.append(f"Strong today (+{day_change:.1f}%)")
        elif day_change > 0.5:
            score += 1
            reasons.append(f"Up today (+{day_change:.1f}%)")
        elif day_change < -1.5:
            score -= 2
            reasons.append(f"Weak today ({day_change:.1f}%)")
        elif day_change < -0.5:
            score -= 1
            reasons.append(f"Down today ({day_change:.1f}%)")
        
        # Week change
        if week_change > 3:
            score += 2
            reasons.append(f"Strong week (+{week_change:.1f}%)")
        elif week_change > 1:
            score += 1
        elif week_change < -3:
            score -= 2
            reasons.append(f"Weak week ({week_change:.1f}%)")
        elif week_change < -1:
            score -= 1
        
        # Month change
        if month_change > 5:
            score += 1
            reasons.append(f"Strong month (+{month_change:.1f}%)")
        elif month_change < -5:
            score -= 1
            reasons.append(f"Weak month ({month_change:.1f}%)")
        
        # Determine sentiment
        if score >= 3:
            return 'BULLISH', 5, reasons
        elif score >= 2:
            return 'BULLISH', 4, reasons
        elif score >= 1:
            return 'BULLISH', 3, reasons
        elif score <= -3:
            return 'BEARISH', 5, reasons
        elif score <= -2:
            return 'BEARISH', 4, reasons
        elif score <= -1:
            return 'BEARISH', 3, reasons
        else:
            return 'NEUTRAL', 2, reasons if reasons else ['Mixed signals']
    
    def _calculate_breadth(self, sectors: List[SectorSentiment]) -> Dict[str, Any]:
        """Calculate market breadth metrics."""
        bullish = sum(1 for s in sectors if s.sentiment == 'BULLISH')
        bearish = sum(1 for s in sectors if s.sentiment == 'BEARISH')
        neutral = sum(1 for s in sectors if s.sentiment == 'NEUTRAL')
        total = len(sectors)
        
        # Advance/decline ratio
        advancing = sum(1 for s in sectors if s.change_pct > 0)
        declining = sum(1 for s in sectors if s.change_pct < 0)
        
        return {
            'bullish_sectors': bullish,
            'bearish_sectors': bearish,
            'neutral_sectors': neutral,
            'total_sectors': total,
            'bullish_pct': round((bullish / total) * 100, 1) if total else 0,
            'advancing': advancing,
            'declining': declining,
            'advance_decline_ratio': round(advancing / declining, 2) if declining > 0 else advancing
        }
    
    def _estimate_put_call_ratio(self) -> Optional[float]:
        """Estimate put/call ratio from SPY options."""
        try:
            spy = yf.Ticker('SPY')
            expirations = spy.options
            
            if not expirations:
                return None
            
            # Use nearest expiration
            chain = spy.option_chain(expirations[0])
            
            call_volume = chain.calls['volume'].sum()
            put_volume = chain.puts['volume'].sum()
            
            if call_volume > 0:
                return round(put_volume / call_volume, 2)
            return None
            
        except Exception as e:
            print(f"Error estimating put/call ratio: {e}")
            return None
    
    def _calculate_overall(self, vix: Dict, sectors: List[SectorSentiment], 
                          breadth: Dict, put_call: Optional[float]) -> tuple:
        """Calculate overall market sentiment."""
        score = 0
        
        # VIX contribution
        vix_level = vix.get('level', 'moderate')
        if vix_level == 'very_low':
            score += 2
        elif vix_level == 'low':
            score += 1
        elif vix_level == 'elevated':
            score -= 1
        elif vix_level == 'high':
            score -= 2
        
        # Breadth contribution
        bullish_pct = breadth.get('bullish_pct', 50)
        if bullish_pct >= 70:
            score += 2
        elif bullish_pct >= 55:
            score += 1
        elif bullish_pct <= 30:
            score -= 2
        elif bullish_pct <= 45:
            score -= 1
        
        # A/D ratio
        ad_ratio = breadth.get('advance_decline_ratio', 1)
        if ad_ratio >= 2:
            score += 1
        elif ad_ratio <= 0.5:
            score -= 1
        
        # Put/call contribution
        if put_call:
            if put_call > 1.2:
                score -= 1  # High put/call = bearish
            elif put_call < 0.7:
                score += 1  # Low put/call = bullish
        
        # Determine overall
        if score >= 3:
            return 'BULLISH', 5
        elif score >= 2:
            return 'BULLISH', 4
        elif score >= 1:
            return 'BULLISH', 3
        elif score <= -3:
            return 'BEARISH', 5
        elif score <= -2:
            return 'BEARISH', 4
        elif score <= -1:
            return 'BEARISH', 3
        else:
            return 'NEUTRAL', 2


# Singleton instance
_sentiment_service = None

def get_sentiment_service() -> SentimentService:
    global _sentiment_service
    if _sentiment_service is None:
        _sentiment_service = SentimentService()
    return _sentiment_service
