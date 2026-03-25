"""
Indicators Service
Toggleable chart indicators and data series computation.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import math

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


@dataclass
class IndicatorConfig:
    """Configuration for an indicator."""
    name: str
    enabled: bool = True
    params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}


class IndicatorService:
    """Computes technical indicators for charting."""
    
    # Default indicator configurations
    DEFAULT_CONFIG = {
        'sma_20': IndicatorConfig('SMA 20', True, {'period': 20}),
        'sma_50': IndicatorConfig('SMA 50', True, {'period': 50}),
        'ema_9': IndicatorConfig('EMA 9', True, {'period': 9}),
        'bollinger': IndicatorConfig('Bollinger Bands', True, {'period': 20, 'std': 2}),
        'macd': IndicatorConfig('MACD', True, {'fast': 12, 'slow': 26, 'signal': 9}),
        'rsi': IndicatorConfig('RSI', True, {'period': 14}),
        'volume': IndicatorConfig('Volume', True, {}),
    }
    
    def __init__(self):
        self.config = dict(self.DEFAULT_CONFIG)
    
    def set_enabled(self, indicator: str, enabled: bool):
        """Enable or disable an indicator."""
        if indicator in self.config:
            self.config[indicator].enabled = enabled
    
    def get_config(self) -> Dict[str, Dict]:
        """Get current indicator configuration."""
        return {
            name: {
                'name': cfg.name,
                'enabled': cfg.enabled,
                'params': cfg.params
            }
            for name, cfg in self.config.items()
        }
    
    def compute_all(self, prices: List[float], volumes: List[float] = None,
                    highs: List[float] = None, lows: List[float] = None) -> Dict[str, Any]:
        """
        Compute all enabled indicators.
        
        Returns dict with indicator data ready for charting.
        """
        results = {}
        
        if not prices:
            return results
        
        # Moving averages
        if self.config['sma_20'].enabled:
            results['sma_20'] = self._sma(prices, 20)
        
        if self.config['sma_50'].enabled:
            results['sma_50'] = self._sma(prices, 50)
        
        if self.config['ema_9'].enabled:
            results['ema_9'] = self._ema(prices, 9)
        
        # Bollinger Bands
        if self.config['bollinger'].enabled:
            bb = self._bollinger(prices, 20, 2)
            results['bollinger_upper'] = bb['upper']
            results['bollinger_middle'] = bb['middle']
            results['bollinger_lower'] = bb['lower']
        
        # MACD
        if self.config['macd'].enabled:
            macd = self._macd(prices, 12, 26, 9)
            results['macd_line'] = macd['macd']
            results['macd_signal'] = macd['signal']
            results['macd_histogram'] = macd['histogram']
        
        # RSI
        if self.config['rsi'].enabled:
            results['rsi'] = self._rsi(prices, 14)
        
        # Volume
        if self.config['volume'].enabled and volumes:
            results['volume'] = volumes
        
        return results
    
    def compute_single(self, indicator: str, prices: List[float],
                       **kwargs) -> Optional[List[float]]:
        """Compute a single indicator."""
        if indicator == 'sma':
            period = kwargs.get('period', 20)
            return self._sma(prices, period)
        elif indicator == 'ema':
            period = kwargs.get('period', 9)
            return self._ema(prices, period)
        elif indicator == 'rsi':
            period = kwargs.get('period', 14)
            return self._rsi(prices, period)
        elif indicator == 'atr':
            period = kwargs.get('period', 14)
            highs = kwargs.get('highs', prices)
            lows = kwargs.get('lows', prices)
            return self._atr(highs, lows, prices, period)
        return None
    
    def _sma(self, prices: List[float], period: int) -> List[Optional[float]]:
        """Simple Moving Average."""
        result = [None] * len(prices)
        
        for i in range(period - 1, len(prices)):
            result[i] = sum(prices[i - period + 1:i + 1]) / period
        
        return result
    
    def _ema(self, prices: List[float], period: int) -> List[Optional[float]]:
        """Exponential Moving Average."""
        result = [None] * len(prices)
        
        if len(prices) < period:
            return result
        
        # Start with SMA
        sma = sum(prices[:period]) / period
        result[period - 1] = sma
        
        multiplier = 2 / (period + 1)
        ema = sma
        
        for i in range(period, len(prices)):
            ema = (prices[i] - ema) * multiplier + ema
            result[i] = ema
        
        return result
    
    def _bollinger(self, prices: List[float], period: int = 20, 
                   std_mult: float = 2.0) -> Dict[str, List[Optional[float]]]:
        """Bollinger Bands."""
        upper = [None] * len(prices)
        middle = [None] * len(prices)
        lower = [None] * len(prices)
        
        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            sma = sum(window) / period
            
            # Standard deviation
            variance = sum((x - sma) ** 2 for x in window) / period
            std = math.sqrt(variance)
            
            middle[i] = sma
            upper[i] = sma + (std_mult * std)
            lower[i] = sma - (std_mult * std)
        
        return {'upper': upper, 'middle': middle, 'lower': lower}
    
    def _macd(self, prices: List[float], fast: int = 12, slow: int = 26,
              signal_period: int = 9) -> Dict[str, List[Optional[float]]]:
        """MACD indicator."""
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)
        
        # MACD line
        macd_line = [None] * len(prices)
        for i in range(len(prices)):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                macd_line[i] = ema_fast[i] - ema_slow[i]
        
        # Signal line (EMA of MACD)
        macd_values = [v for v in macd_line if v is not None]
        signal_ema = self._ema(macd_values, signal_period)
        
        signal_line = [None] * len(prices)
        macd_start = next((i for i, v in enumerate(macd_line) if v is not None), len(prices))
        
        for i, sig_val in enumerate(signal_ema):
            if sig_val is not None:
                signal_line[macd_start + i] = sig_val
        
        # Histogram
        histogram = [None] * len(prices)
        for i in range(len(prices)):
            if macd_line[i] is not None and signal_line[i] is not None:
                histogram[i] = macd_line[i] - signal_line[i]
        
        return {'macd': macd_line, 'signal': signal_line, 'histogram': histogram}
    
    def _rsi(self, prices: List[float], period: int = 14) -> List[Optional[float]]:
        """RSI indicator."""
        result = [None] * len(prices)
        
        if len(prices) < period + 1:
            return result
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            gains.append(change if change > 0 else 0)
            losses.append(abs(change) if change < 0 else 0)
        
        for i in range(period, len(prices)):
            avg_gain = sum(gains[i - period:i]) / period
            avg_loss = sum(losses[i - period:i]) / period
            
            if avg_loss == 0:
                result[i] = 100
            else:
                rs = avg_gain / avg_loss
                result[i] = 100 - (100 / (1 + rs))
        
        return result
    
    def _atr(self, highs: List[float], lows: List[float], 
             closes: List[float], period: int = 14) -> List[Optional[float]]:
        """Average True Range."""
        result = [None] * len(closes)
        
        if len(closes) < period + 1:
            return result
        
        tr_values = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            tr_values.append(tr)
        
        for i in range(period, len(closes)):
            result[i] = sum(tr_values[i - period:i]) / period
        
        return result


# Singleton
_indicator_service = None

def get_indicator_service() -> IndicatorService:
    global _indicator_service
    if _indicator_service is None:
        _indicator_service = IndicatorService()
    return _indicator_service
