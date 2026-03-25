"""
Technical Analysis Service
RSI, MACD, ATR, Bollinger Bands, ADX, regime detection, etc.
"""

import math
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


class TrendDirection(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class RegimeType(Enum):
    TRENDING = "TRENDING"
    CHOPPY = "CHOPPY"
    SQUEEZE = "SQUEEZE"
    UNKNOWN = "UNKNOWN"


@dataclass
class Evidence:
    """Unified evidence object for signal generation."""
    structure_bullish: bool = False
    structure_bearish: bool = False
    structure_score: float = 0.0
    
    momentum_bullish: bool = False
    momentum_bearish: bool = False
    momentum_score: float = 0.0
    
    regime: RegimeType = RegimeType.UNKNOWN
    adx: float = 0.0
    is_choppy: bool = False
    in_squeeze: bool = False
    
    iv_rank: float = 50.0
    atr_pct: float = 0.0
    bollinger_width: float = 0.0
    
    rsi: float = 50.0
    macd_histogram: float = 0.0
    
    reasons: List[str] = field(default_factory=list)


@dataclass
class UnderlyingAnalysis:
    """Complete technical analysis of a stock."""
    symbol: str
    price: float
    trend: TrendDirection
    trend_strength: float
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    sma_20: float
    sma_50: float
    ema_9: float
    atr: float
    atr_pct: float
    iv_rank: float
    volatility_20d: float
    reasons: List[str]
    adx: float = 25.0
    regime: RegimeType = RegimeType.UNKNOWN
    bollinger_upper: float = 0.0
    bollinger_lower: float = 0.0
    bollinger_width: float = 0.0
    sma_50_slope: float = 0.0
    support: float = 0.0
    resistance: float = 0.0
    evidence: Evidence = field(default_factory=Evidence)
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'price': self.price,
            'trend': self.trend.value,
            'trend_strength': round(self.trend_strength, 1),
            'rsi': round(self.rsi, 1),
            'macd': round(self.macd, 4),
            'macd_signal': round(self.macd_signal, 4),
            'macd_histogram': round(self.macd_histogram, 4),
            'sma_20': round(self.sma_20, 2),
            'sma_50': round(self.sma_50, 2),
            'ema_9': round(self.ema_9, 2),
            'atr': round(self.atr, 2),
            'atr_pct': round(self.atr_pct, 2),
            'iv_rank': round(self.iv_rank, 1),
            'volatility_20d': round(self.volatility_20d, 1),
            'adx': round(self.adx, 1),
            'regime': self.regime.value,
            'bollinger_upper': round(self.bollinger_upper, 2),
            'bollinger_lower': round(self.bollinger_lower, 2),
            'bollinger_width': round(self.bollinger_width, 2),
            'support': round(self.support, 2),
            'resistance': round(self.resistance, 2),
            'reasons': self.reasons,
            'evidence': {
                'structure_score': round(self.evidence.structure_score, 2),
                'momentum_score': round(self.evidence.momentum_score, 2),
                'structure_bullish': self.evidence.structure_bullish,
                'momentum_bullish': self.evidence.momentum_bullish,
                'is_choppy': self.evidence.is_choppy,
                'in_squeeze': self.evidence.in_squeeze
            }
        }


class TechnicalAnalyzer:
    """Analyzes stocks for trend, momentum, and regime."""
    
    def __init__(self):
        self.cache: dict[str, UnderlyingAnalysis] = {}
        self.cache_time: dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=5)
    
    def analyze(self, symbol: str) -> Optional[UnderlyingAnalysis]:
        """Get complete technical analysis for a symbol."""
        # Check cache
        if symbol in self.cache:
            if datetime.now() - self.cache_time[symbol] < self.cache_duration:
                return self.cache[symbol]
        
        if not HAS_YFINANCE:
            return None
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="60d", interval="1d")
            
            if hist.empty or len(hist) < 30:
                return None
            
            close = hist['Close'].values
            high = hist['High'].values
            low = hist['Low'].values
            current_price = float(close[-1])
            
            # Calculate indicators
            rsi = self._calculate_rsi(close, 14)
            macd, macd_signal, macd_hist = self._calculate_macd(close)
            sma_20 = self._calculate_sma(close, 20)
            sma_50 = self._calculate_sma(close, 50)
            ema_9 = self._calculate_ema(close, 9)
            atr = self._calculate_atr(high, low, close, 14)
            atr_pct = (atr / current_price) * 100
            
            # Bollinger Bands
            bb_width, bb_upper, bb_lower = self._calculate_bollinger(close, 20, 2.0)
            
            # ADX
            adx = self._calculate_adx(high, low, close, 14)
            
            # SMA slope
            sma_50_slope = self._calculate_sma_slope(close, 50, 5)
            
            # Regime detection
            regime = self._detect_regime(adx, sma_50_slope, bb_width)
            
            # IV rank estimation
            returns = [(close[i] - close[i-1]) / close[i-1] for i in range(1, len(close))]
            volatility_20d = self._calculate_std(returns[-20:]) * math.sqrt(252) * 100
            
            all_volatilities = []
            for i in range(20, len(returns)):
                vol = self._calculate_std(returns[i-20:i]) * math.sqrt(252) * 100
                all_volatilities.append(vol)
            
            if all_volatilities:
                min_vol = min(all_volatilities)
                max_vol = max(all_volatilities)
                iv_rank = ((volatility_20d - min_vol) / (max_vol - min_vol)) * 100 if max_vol > min_vol else 50
            else:
                iv_rank = 50
            
            # Support/Resistance
            support = min(low[-20:])
            resistance = max(high[-20:])
            
            # Trend determination
            trend, trend_strength, reasons = self._determine_trend(
                current_price, rsi, macd, macd_signal, macd_hist,
                sma_20, sma_50, ema_9
            )
            
            # Build evidence
            evidence = self._build_evidence(
                current_price, rsi, macd, macd_signal, macd_hist,
                sma_20, sma_50, ema_9, adx, regime,
                iv_rank, atr_pct, bb_width
            )
            
            # Add regime info
            if regime == RegimeType.CHOPPY:
                reasons.append(f"CHOPPY regime (ADX={adx:.0f})")
            elif regime == RegimeType.SQUEEZE:
                reasons.append(f"Bollinger SQUEEZE (breakout pending)")
            elif regime == RegimeType.TRENDING:
                reasons.append(f"TRENDING regime (ADX={adx:.0f})")
            
            analysis = UnderlyingAnalysis(
                symbol=symbol,
                price=current_price,
                trend=trend,
                trend_strength=trend_strength,
                rsi=rsi,
                macd=macd,
                macd_signal=macd_signal,
                macd_histogram=macd_hist,
                sma_20=sma_20,
                sma_50=sma_50,
                ema_9=ema_9,
                atr=atr,
                atr_pct=atr_pct,
                iv_rank=iv_rank,
                volatility_20d=volatility_20d,
                reasons=reasons,
                adx=adx,
                regime=regime,
                bollinger_upper=bb_upper,
                bollinger_lower=bb_lower,
                bollinger_width=bb_width,
                sma_50_slope=sma_50_slope,
                support=support,
                resistance=resistance,
                evidence=evidence
            )
            
            self.cache[symbol] = analysis
            self.cache_time[symbol] = datetime.now()
            
            return analysis
            
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
            return None
    
    def _calculate_rsi(self, prices: list, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50
        
        gains, losses = [], []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            gains.append(change if change >= 0 else 0)
            losses.append(abs(change) if change < 0 else 0)
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, prices: list) -> Tuple[float, float, float]:
        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)
        macd = ema_12 - ema_26
        
        macd_values = []
        for i in range(26, len(prices) + 1):
            e12 = self._calculate_ema(prices[:i], 12)
            e26 = self._calculate_ema(prices[:i], 26)
            macd_values.append(e12 - e26)
        
        signal = self._calculate_ema(macd_values, 9) if len(macd_values) >= 9 else macd
        histogram = macd - signal
        
        return macd, signal, histogram
    
    def _calculate_sma(self, prices: list, period: int) -> float:
        if len(prices) < period:
            return float(prices[-1]) if len(prices) > 0 else 0
        return sum(prices[-period:]) / period
    
    def _calculate_ema(self, prices: list, period: int) -> float:
        if len(prices) < period:
            return float(prices[-1]) if len(prices) > 0 else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def _calculate_atr(self, high: list, low: list, close: list, period: int = 14) -> float:
        if len(close) < period + 1:
            return (max(high) - min(low)) / len(high) if len(high) > 0 else 0
        
        tr_values = []
        for i in range(1, len(close)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            tr_values.append(tr)
        
        return sum(tr_values[-period:]) / period
    
    def _calculate_std(self, values: list) -> float:
        if len(values) == 0:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)
    
    def _calculate_bollinger(self, close: list, period: int = 20, std_mult: float = 2.0) -> Tuple[float, float, float]:
        if len(close) < period:
            return 100.0, 0.0, 0.0
        
        recent = close[-period:]
        sma = sum(recent) / period
        std = self._calculate_std(recent)
        
        upper = sma + (std_mult * std)
        lower = sma - (std_mult * std)
        width = upper - lower
        width_pct = (width / sma * 100) if sma > 0 else 0
        
        return round(width_pct, 2), round(upper, 2), round(lower, 2)
    
    def _calculate_adx(self, high: list, low: list, close: list, period: int = 14) -> float:
        if len(close) < period + 1:
            return 0.0
        
        plus_dm, minus_dm, tr_list = [], [], []
        
        for i in range(1, len(close)):
            high_diff = high[i] - high[i-1]
            low_diff = low[i-1] - low[i]
            
            plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
            minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)
            
            tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
            tr_list.append(tr)
        
        if len(tr_list) < period:
            return 0.0
        
        atr = sum(tr_list[:period]) / period
        plus_di_sum = sum(plus_dm[:period]) / period
        minus_di_sum = sum(minus_dm[:period]) / period
        
        for i in range(period, len(tr_list)):
            atr = (atr * (period - 1) + tr_list[i]) / period
            plus_di_sum = (plus_di_sum * (period - 1) + plus_dm[i]) / period
            minus_di_sum = (minus_di_sum * (period - 1) + minus_dm[i]) / period
        
        plus_di = (plus_di_sum / atr * 100) if atr > 0 else 0
        minus_di = (minus_di_sum / atr * 100) if atr > 0 else 0
        
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        dx = (di_diff / di_sum * 100) if di_sum > 0 else 0
        
        return round(dx, 1)
    
    def _calculate_sma_slope(self, close: list, sma_period: int = 50, slope_period: int = 5) -> float:
        if len(close) < sma_period + slope_period:
            return 0.0
        
        sma_values = []
        for i in range(slope_period + 1):
            idx = len(close) - slope_period - 1 + i
            start = idx - sma_period + 1
            if start >= 0:
                sma_values.append(sum(close[start:idx+1]) / sma_period)
        
        if len(sma_values) < 2:
            return 0.0
        
        first_sma = sma_values[0]
        last_sma = sma_values[-1]
        if first_sma == 0:
            return 0.0
        
        total_change_pct = ((last_sma - first_sma) / first_sma) * 100
        return round(total_change_pct / slope_period, 3)
    
    def _detect_regime(self, adx: float, sma_slope: float, bb_width: float) -> RegimeType:
        if bb_width < 4.0:
            return RegimeType.SQUEEZE
        if adx < 18 and abs(sma_slope) < 0.1:
            return RegimeType.CHOPPY
        if adx > 20 and abs(sma_slope) > 0.05:
            return RegimeType.TRENDING
        if adx < 20:
            return RegimeType.CHOPPY
        return RegimeType.TRENDING
    
    def _build_evidence(self, price, rsi, macd, macd_signal, macd_hist, sma_20, sma_50, ema_9, adx, regime, iv_rank, atr_pct, bb_width) -> Evidence:
        evidence = Evidence()
        evidence.adx = adx
        evidence.regime = regime
        evidence.is_choppy = regime == RegimeType.CHOPPY
        evidence.in_squeeze = regime == RegimeType.SQUEEZE
        evidence.iv_rank = iv_rank
        evidence.atr_pct = atr_pct
        evidence.bollinger_width = bb_width
        evidence.rsi = rsi
        evidence.macd_histogram = macd_hist
        
        # Structure score
        structure_score = 0.0
        if price > sma_50:
            structure_score += 0.4
            evidence.reasons.append("Price > SMA50")
        else:
            structure_score -= 0.4
        
        if sma_20 > sma_50:
            structure_score += 0.3
            evidence.reasons.append("SMA20 > SMA50")
        else:
            structure_score -= 0.3
        
        evidence.structure_score = max(-1.0, min(1.0, structure_score))
        evidence.structure_bullish = structure_score > 0.3
        evidence.structure_bearish = structure_score < -0.3
        
        # Momentum score
        momentum_score = 0.0
        if price > ema_9:
            momentum_score += 0.3
        else:
            momentum_score -= 0.3
        
        if macd > macd_signal:
            momentum_score += 0.3
        else:
            momentum_score -= 0.3
        
        if macd_hist > 0:
            momentum_score += 0.2
        else:
            momentum_score -= 0.2
        
        if rsi > 50:
            momentum_score += 0.2
        else:
            momentum_score -= 0.2
        
        evidence.momentum_score = max(-1.0, min(1.0, momentum_score))
        evidence.momentum_bullish = momentum_score > 0.3
        evidence.momentum_bearish = momentum_score < -0.3
        
        return evidence
    
    def _determine_trend(self, price, rsi, macd, macd_signal, macd_hist, sma_20, sma_50, ema_9) -> Tuple[TrendDirection, float, List[str]]:
        bullish_points = 0
        bearish_points = 0
        reasons = []
        
        if price > sma_20:
            bullish_points += 15
            reasons.append("Price > SMA20")
        else:
            bearish_points += 15
        
        if price > sma_50:
            bullish_points += 20
            reasons.append("Price > SMA50")
        else:
            bearish_points += 20
        
        if sma_20 > sma_50:
            bullish_points += 15
            reasons.append("Golden Cross (SMA20 > SMA50)")
        else:
            bearish_points += 15
            reasons.append("Death Cross (SMA20 < SMA50)")
        
        if price > ema_9:
            bullish_points += 10
        else:
            bearish_points += 10
        
        if macd > macd_signal:
            bullish_points += 15
            reasons.append("MACD bullish")
        else:
            bearish_points += 15
            reasons.append("MACD bearish")
        
        if macd_hist > 0:
            bullish_points += 10
        else:
            bearish_points += 10
        
        if rsi > 50:
            bullish_points += 5
            if rsi > 60:
                bullish_points += 5
                reasons.append(f"RSI strong ({rsi:.0f})")
        else:
            bearish_points += 5
            if rsi < 40:
                bearish_points += 5
                reasons.append(f"RSI weak ({rsi:.0f})")
        
        if rsi < 30:
            reasons.append("RSI oversold - potential bounce")
        elif rsi > 70:
            reasons.append("RSI overbought - potential pullback")
        
        total = bullish_points + bearish_points
        if total == 0:
            return TrendDirection.NEUTRAL, 50, reasons
        
        if bullish_points > bearish_points * 1.3:
            return TrendDirection.BULLISH, (bullish_points / total) * 100, reasons
        elif bearish_points > bullish_points * 1.3:
            return TrendDirection.BEARISH, (bearish_points / total) * 100, reasons
        else:
            return TrendDirection.NEUTRAL, 50, reasons


# Singleton instance
_analyzer = None

def get_analyzer() -> TechnicalAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = TechnicalAnalyzer()
    return _analyzer
