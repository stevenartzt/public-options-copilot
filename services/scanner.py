"""
Options Scanner Service
Scans for high-quality option opportunities with edge-based scoring.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import math

from config import Config, has_api_credentials
from .analysis import TechnicalAnalyzer, TrendDirection, RegimeType, get_analyzer
from .market_data import get_market_data_service

# Try to import Public SDK
try:
    from public_api_sdk import (
        PublicApiClient,
        ApiKeyAuthConfig,
        PublicApiClientConfiguration,
        OrderInstrument,
        InstrumentType,
        OptionChainRequest,
        OptionExpirationsRequest
    )
    HAS_SDK = True
except ImportError:
    HAS_SDK = False


class SignalType(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"


@dataclass
class ScanResult:
    """A scanned option with scoring."""
    symbol: str
    underlying: str
    strike: float
    expiration: str
    option_type: str
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    days_to_expiry: int
    underlying_price: float
    
    # Scoring
    signal: SignalType
    score: float
    reasons: List[str]
    
    # Analysis
    trend: str
    trend_strength: float
    iv_rank: float
    rsi: float
    win_probability: float
    directional_alignment: bool
    
    # Entry/Exit
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    
    # Affordability
    is_affordable: bool
    is_cheap: bool
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'underlying': self.underlying,
            'strike': self.strike,
            'expiration': self.expiration,
            'option_type': self.option_type,
            'bid': round(self.bid, 2),
            'ask': round(self.ask, 2),
            'last': round(self.last, 2),
            'mid': round((self.bid + self.ask) / 2, 2),
            'volume': self.volume,
            'open_interest': self.open_interest,
            'days_to_expiry': self.days_to_expiry,
            'underlying_price': round(self.underlying_price, 2),
            'signal': self.signal.value,
            'score': round(self.score, 1),
            'reasons': self.reasons,
            'trend': self.trend,
            'trend_strength': round(self.trend_strength, 1),
            'iv_rank': round(self.iv_rank, 1),
            'rsi': round(self.rsi, 1),
            'win_probability': round(self.win_probability, 1),
            'directional_alignment': self.directional_alignment,
            'entry_price': round(self.entry_price, 2),
            'stop_loss': round(self.stop_loss, 2),
            'take_profit': round(self.take_profit, 2),
            'risk_reward': round(self.risk_reward, 2),
            'is_affordable': self.is_affordable,
            'is_cheap': self.is_cheap
        }


class OptionsScanner:
    """Scans for option opportunities using edge-based analysis."""
    
    def __init__(self):
        self.analyzer = get_analyzer()
        self.market_data = get_market_data_service()
        self.client: Optional[Any] = None
        self.watchlist: List[str] = Config.WATCHLIST_PRESETS['default']
        
        self._init_client()
    
    def _init_client(self):
        """Initialize Public API client for option chain data."""
        if not HAS_SDK or not has_api_credentials():
            return
        
        try:
            config = PublicApiClientConfiguration(
                default_account_number=Config.PUBLIC_ACCOUNT_ID
            )
            self.client = PublicApiClient(
                ApiKeyAuthConfig(api_secret_key=Config.PUBLIC_API_KEY),
                config=config
            )
        except Exception as e:
            print(f"Scanner: Failed to init API client: {e}")
            self.client = None
    
    def set_watchlist(self, symbols: List[str]):
        """Update the scanner watchlist."""
        self.watchlist = [s.upper() for s in symbols]
    
    def get_watchlist(self) -> List[str]:
        """Get current watchlist."""
        return self.watchlist
    
    def scan(self, symbols: Optional[List[str]] = None,
             min_volume: int = None, min_oi: int = None,
             max_dte: int = None, limit: int = None) -> List[ScanResult]:
        """
        Scan for option opportunities.
        Falls back to yfinance if no API credentials.
        """
        symbols = symbols or self.watchlist
        min_volume = min_volume or Config.DEFAULT_MIN_VOLUME
        min_oi = min_oi or Config.DEFAULT_MIN_OI
        max_dte = max_dte or Config.DEFAULT_MAX_DTE
        limit = limit or Config.DEFAULT_SCAN_LIMIT
        
        all_results = []
        
        for symbol in symbols:
            try:
                # Analyze underlying first
                analysis = self.analyzer.analyze(symbol)
                if not analysis:
                    continue
                
                # Skip choppy regimes
                if analysis.regime == RegimeType.CHOPPY:
                    continue
                
                # Get option chain
                if self.client:
                    results = self._scan_with_api(
                        symbol, analysis, min_volume, min_oi, max_dte
                    )
                else:
                    results = self._scan_with_yfinance(
                        symbol, analysis, min_volume, min_oi, max_dte
                    )
                
                all_results.extend(results)
                
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
                continue
        
        # Filter to aligned signals only
        aligned = [r for r in all_results if r.directional_alignment and r.signal != SignalType.NEUTRAL]
        
        # Sort by score
        aligned.sort(key=lambda x: (x.signal == SignalType.STRONG_BUY, x.score), reverse=True)
        
        # Enforce STRONG_BUY scarcity
        max_strong = max(2, limit // 5)
        strong_count = 0
        final = []
        
        for r in aligned:
            if r.signal == SignalType.STRONG_BUY:
                if strong_count >= max_strong:
                    r.signal = SignalType.BUY
                    r.reasons.append("Downgraded (STRONG_BUY quota)")
                else:
                    strong_count += 1
            final.append(r)
        
        return final[:limit]
    
    def _scan_with_api(self, symbol: str, analysis, min_volume: int,
                       min_oi: int, max_dte: int) -> List[ScanResult]:
        """Scan using Public API."""
        results = []
        
        try:
            instrument = OrderInstrument(symbol=symbol, type=InstrumentType.EQUITY)
            
            # Get expirations
            exp_req = OptionExpirationsRequest(instrument=instrument)
            exp_resp = self.client.get_option_expirations(exp_req)
            
            today = datetime.now().date()
            min_date = today + timedelta(days=7)
            max_date = today + timedelta(days=max_dte)
            
            valid_exps = [
                exp for exp in exp_resp.expirations
                if min_date <= datetime.strptime(exp, "%Y-%m-%d").date() <= max_date
            ][:3]
            
            for expiration in valid_exps:
                days_to_exp = (datetime.strptime(expiration, "%Y-%m-%d").date() - today).days
                
                if days_to_exp <= 0:
                    continue
                
                chain_req = OptionChainRequest(
                    instrument=instrument,
                    expiration_date=expiration
                )
                chain = self.client.get_option_chain(chain_req)
                
                # Scan calls if bullish
                if analysis.trend == TrendDirection.BULLISH:
                    for opt in (chain.calls or []):
                        result = self._score_option(
                            opt, symbol, expiration, "call",
                            analysis, days_to_exp, min_volume, min_oi
                        )
                        if result:
                            results.append(result)
                
                # Scan puts if bearish
                elif analysis.trend == TrendDirection.BEARISH:
                    for opt in (chain.puts or []):
                        result = self._score_option(
                            opt, symbol, expiration, "put",
                            analysis, days_to_exp, min_volume, min_oi
                        )
                        if result:
                            results.append(result)
                            
        except Exception as e:
            print(f"API scan error for {symbol}: {e}")
        
        return results
    
    def _scan_with_yfinance(self, symbol: str, analysis, min_volume: int,
                            min_oi: int, max_dte: int) -> List[ScanResult]:
        """Scan using yfinance (fallback)."""
        results = []
        
        chain_data = self.market_data.get_option_chain(symbol)
        if not chain_data:
            return results
        
        today = datetime.now().date()
        expiration = chain_data['expiration']
        
        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
            days_to_exp = (exp_date - today).days
        except:
            return results
        
        if days_to_exp <= 0 or days_to_exp > max_dte:
            return results
        
        # Scan calls if bullish
        if analysis.trend == TrendDirection.BULLISH:
            for opt in chain_data['calls']:
                result = self._score_yf_option(
                    opt, symbol, expiration, "call",
                    analysis, days_to_exp, min_volume, min_oi
                )
                if result:
                    results.append(result)
        
        # Scan puts if bearish
        elif analysis.trend == TrendDirection.BEARISH:
            for opt in chain_data['puts']:
                result = self._score_yf_option(
                    opt, symbol, expiration, "put",
                    analysis, days_to_exp, min_volume, min_oi
                )
                if result:
                    results.append(result)
        
        return results
    
    def _score_option(self, quote, underlying: str, expiration: str,
                      option_type: str, analysis, days_to_exp: int,
                      min_volume: int, min_oi: int) -> Optional[ScanResult]:
        """Score an option from API data."""
        try:
            volume = int(quote.volume) if quote.volume else 0
            oi = int(quote.open_interest) if quote.open_interest else 0
            bid = float(quote.bid) if quote.bid else 0
            ask = float(quote.ask) if quote.ask else 0
            last = float(quote.last) if quote.last else 0
            
            # Basic filters
            if volume < min_volume or oi < min_oi:
                return None
            if bid <= 0 or ask <= 0:
                return None
            
            mid = (bid + ask) / 2
            spread_pct = (ask - bid) / mid if mid > 0 else 1
            
            if spread_pct > 0.10:
                return None
            
            strike = self._parse_strike(quote.instrument.symbol)
            symbol = quote.instrument.symbol.replace('-OPTION', '')
            
            return self._compute_score(
                symbol, underlying, strike, expiration, option_type,
                bid, ask, last, volume, oi, days_to_exp, analysis, mid
            )
            
        except Exception as e:
            return None
    
    def _score_yf_option(self, opt: dict, underlying: str, expiration: str,
                         option_type: str, analysis, days_to_exp: int,
                         min_volume: int, min_oi: int) -> Optional[ScanResult]:
        """Score an option from yfinance data."""
        try:
            volume = opt.get('volume', 0) or 0
            oi = opt.get('open_interest', 0) or 0
            bid = opt.get('bid', 0) or 0
            ask = opt.get('ask', 0) or 0
            last = opt.get('last', 0) or 0
            strike = opt.get('strike', 0)
            
            if volume < min_volume or oi < min_oi:
                return None
            if bid <= 0 or ask <= 0:
                return None
            
            mid = (bid + ask) / 2
            spread_pct = (ask - bid) / mid if mid > 0 else 1
            
            if spread_pct > 0.10:
                return None
            
            # Build OSI-like symbol
            exp_fmt = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")
            opt_char = "C" if option_type == "call" else "P"
            strike_str = f"{int(strike * 1000):08d}"
            symbol = f"{underlying}{exp_fmt}{opt_char}{strike_str}"
            
            return self._compute_score(
                symbol, underlying, strike, expiration, option_type,
                bid, ask, last, volume, oi, days_to_exp, analysis, mid
            )
            
        except Exception as e:
            return None
    
    def _compute_score(self, symbol: str, underlying: str, strike: float,
                       expiration: str, option_type: str, bid: float,
                       ask: float, last: float, volume: int, oi: int,
                       days_to_exp: int, analysis, mid: float) -> Optional[ScanResult]:
        """Compute edge-based score for an option."""
        score = 0.0
        reasons = []
        
        trend = analysis.trend
        trend_strength = analysis.trend_strength
        rsi = analysis.rsi
        iv_rank = analysis.iv_rank
        atr = analysis.atr
        underlying_price = analysis.price
        
        # Directional alignment
        directional_alignment = False
        if option_type == 'call' and trend == TrendDirection.BULLISH:
            directional_alignment = True
            score += 20
            reasons.append("CALL aligns with BULLISH trend")
        elif option_type == 'put' and trend == TrendDirection.BEARISH:
            directional_alignment = True
            score += 20
            reasons.append("PUT aligns with BEARISH trend")
        else:
            return None  # Wrong direction
        
        # Trend strength
        if trend_strength >= 75:
            score += 12
            reasons.append(f"Very strong trend ({trend_strength:.0f}%)")
        elif trend_strength >= 65:
            score += 8
        elif trend_strength >= 55:
            score += 4
        
        # IV rank (buy low)
        is_cheap = iv_rank < 30
        if iv_rank < 20:
            score += 15
            reasons.append(f"Bargain IV ({iv_rank:.0f}%)")
        elif iv_rank < 30:
            score += 12
            reasons.append(f"Low IV ({iv_rank:.0f}%)")
        elif iv_rank < 45:
            score += 6
        elif iv_rank > 70:
            score -= 8
            reasons.append(f"High IV ({iv_rank:.0f}%)")
        
        # RSI
        if option_type == 'call':
            if 35 <= rsi <= 55:
                score += 8
                reasons.append(f"RSI favorable ({rsi:.0f})")
            elif rsi < 35:
                score += 6
            elif rsi > 70:
                score -= 4
        else:
            if 45 <= rsi <= 65:
                score += 8
            elif rsi > 65:
                score += 6
            elif rsi < 30:
                score -= 4
        
        # Delta estimation
        delta = self._estimate_delta(option_type, strike, underlying_price, days_to_exp, iv_rank)
        if 0.35 <= delta <= 0.50:
            score += 12
            reasons.append(f"Optimal delta ({delta:.2f})")
        elif 0.25 <= delta < 0.35:
            score += 8
        elif 0.50 < delta <= 0.65:
            score += 6
        elif delta < 0.20:
            score -= 4
        
        # Volume/OI ratio
        vol_oi_ratio = volume / oi if oi > 0 else 0
        if vol_oi_ratio > 1.5 and oi >= 200:
            score += 10
            reasons.append(f"Unusual volume (V/OI: {vol_oi_ratio:.1f}x)")
        elif vol_oi_ratio > 0.8:
            score += 5
        
        # Liquidity bonus
        spread_pct = (ask - bid) / mid if mid > 0 else 1
        if spread_pct < 0.03:
            score += 6
            reasons.append("Very liquid")
        elif spread_pct < 0.06:
            score += 3
        
        # DTE bonus
        if 14 <= days_to_exp <= 30:
            score += 6
            reasons.append(f"Optimal DTE ({days_to_exp}d)")
        elif 7 <= days_to_exp < 14 or 30 < days_to_exp <= 45:
            score += 3
        
        # Affordability
        is_affordable = mid <= 3.00
        if mid <= 1.00:
            score += 6
            reasons.append(f"Budget entry ${mid:.2f}")
        elif mid <= 3.00:
            score += 4
        elif mid <= 7.00:
            score += 2
        
        # Win probability
        win_prob = 45.0 + 5  # Base + alignment
        if analysis.evidence.structure_bullish and analysis.evidence.momentum_bullish and option_type == 'call':
            win_prob += 5
        elif analysis.evidence.structure_bearish and analysis.evidence.momentum_bearish and option_type == 'put':
            win_prob += 5
        win_prob += (trend_strength - 50) * 0.15
        if iv_rank < 30:
            win_prob += 4
        if delta > 0.50:
            win_prob += 3
        win_prob = max(20, min(85, win_prob))
        
        # Signal determination
        if score >= 65 and win_prob >= 55:
            signal = SignalType.STRONG_BUY
        elif score >= 45 and win_prob >= 45:
            signal = SignalType.BUY
        else:
            signal = SignalType.NEUTRAL
        
        if signal == SignalType.NEUTRAL:
            return None
        
        # Entry/Exit
        entry_price = mid
        if atr > 0:
            atr_pct = (1.5 * atr / underlying_price) * 100
            stop_pct = min(0.35, max(0.20, atr_pct / 100 * 3))
            profit_pct = stop_pct * 2.5
            stop_loss = round(mid * (1 - stop_pct), 2)
            take_profit = round(mid * (1 + profit_pct), 2)
            risk_reward = round(profit_pct / stop_pct, 2)
        else:
            stop_loss = round(mid * 0.75, 2)
            take_profit = round(mid * 1.50, 2)
            risk_reward = 2.0
        
        return ScanResult(
            symbol=symbol,
            underlying=underlying,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            open_interest=oi,
            days_to_expiry=days_to_exp,
            underlying_price=underlying_price,
            signal=signal,
            score=score,
            reasons=reasons,
            trend=trend.value,
            trend_strength=trend_strength,
            iv_rank=iv_rank,
            rsi=rsi,
            win_probability=win_prob,
            directional_alignment=directional_alignment,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            is_affordable=is_affordable,
            is_cheap=is_cheap
        )
    
    def _estimate_delta(self, option_type: str, strike: float,
                        underlying_price: float, days_to_exp: int, iv_rank: float) -> float:
        """Estimate option delta."""
        if option_type == 'call':
            moneyness = (underlying_price - strike) / underlying_price
        else:
            moneyness = (strike - underlying_price) / underlying_price
        
        iv_estimate = 0.20 + (iv_rank / 100) * 0.40
        time_factor = math.sqrt(days_to_exp / 365) if days_to_exp > 0 else 0.1
        scale = iv_estimate * time_factor * underlying_price
        
        if scale == 0:
            scale = 0.01
        
        d1_proxy = (moneyness * underlying_price) / scale
        d1_proxy = max(-10, min(10, d1_proxy))
        
        delta = 1 / (1 + math.exp(-1.7 * d1_proxy))
        return round(delta, 2)
    
    def _parse_strike(self, osi_symbol: str) -> float:
        """Parse strike from OSI symbol."""
        try:
            clean = osi_symbol.replace('-OPTION', '')
            return int(clean[-8:]) / 1000
        except:
            return 0.0


# Singleton
_scanner = None

def get_scanner() -> OptionsScanner:
    global _scanner
    if _scanner is None:
        _scanner = OptionsScanner()
    return _scanner
