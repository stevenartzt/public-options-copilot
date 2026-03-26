"""
Algo Trading Service
Strategy builder, backtester, and automated execution.
"""

import json
import os
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
import uuid

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

from config import Config
from .market_data import get_market_data_service
from .paper_trading import get_paper_trading_service
from .analysis import get_analyzer


class ConditionType(Enum):
    RSI_BELOW = "rsi_below"
    RSI_ABOVE = "rsi_above"
    RSI_CROSSES_BELOW = "rsi_crosses_below"
    RSI_CROSSES_ABOVE = "rsi_crosses_above"
    ATR_PCT_ABOVE = "atr_pct_above"
    ATR_PCT_BELOW = "atr_pct_below"
    TREND_BULLISH = "trend_bullish"
    TREND_BEARISH = "trend_bearish"
    TREND_NEUTRAL = "trend_neutral"
    MACD_BULLISH = "macd_bullish"
    MACD_BEARISH = "macd_bearish"
    PRICE_ABOVE_SMA20 = "price_above_sma20"
    PRICE_BELOW_SMA20 = "price_below_sma20"
    PRICE_ABOVE_SMA50 = "price_above_sma50"
    PRICE_BELOW_SMA50 = "price_below_sma50"
    ADX_ABOVE = "adx_above"
    ADX_BELOW = "adx_below"
    REGIME_TRENDING = "regime_trending"
    REGIME_CHOPPY = "regime_choppy"
    REGIME_SQUEEZE = "regime_squeeze"
    PROFIT_ABOVE = "profit_above"
    LOSS_ABOVE = "loss_above"
    HOLD_DAYS_ABOVE = "hold_days_above"


@dataclass
class Condition:
    """A single condition for entry/exit rules."""
    type: str
    value: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {'type': self.type, 'value': self.value}
    
    @staticmethod
    def from_dict(d: dict) -> 'Condition':
        return Condition(type=d['type'], value=d.get('value'))


@dataclass
class Strategy:
    """A trading strategy with entry/exit rules."""
    id: str
    name: str
    symbols: List[str]
    entry_conditions: List[Condition]  # AND logic
    exit_conditions: List[Condition]   # OR logic
    position_size_pct: float = 10.0    # % of portfolio per trade
    max_positions: int = 5
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    enabled: bool = False
    is_live: bool = False  # Paper vs real
    created_at: str = ""
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'symbols': self.symbols,
            'entry_conditions': [c.to_dict() for c in self.entry_conditions],
            'exit_conditions': [c.to_dict() for c in self.exit_conditions],
            'position_size_pct': self.position_size_pct,
            'max_positions': self.max_positions,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'enabled': self.enabled,
            'is_live': self.is_live,
            'created_at': self.created_at
        }
    
    @staticmethod
    def from_dict(d: dict) -> 'Strategy':
        return Strategy(
            id=d['id'],
            name=d['name'],
            symbols=d['symbols'],
            entry_conditions=[Condition.from_dict(c) for c in d.get('entry_conditions', [])],
            exit_conditions=[Condition.from_dict(c) for c in d.get('exit_conditions', [])],
            position_size_pct=d.get('position_size_pct', 10.0),
            max_positions=d.get('max_positions', 5),
            stop_loss_pct=d.get('stop_loss_pct'),
            take_profit_pct=d.get('take_profit_pct'),
            enabled=d.get('enabled', False),
            is_live=d.get('is_live', False),
            created_at=d.get('created_at', '')
        )


@dataclass
class BacktestTrade:
    """A single trade from backtesting."""
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    hold_days: int
    exit_reason: str
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    strategy_name: str
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    total_return: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    avg_trade_pnl: float
    avg_hold_days: float
    trades: List[BacktestTrade]
    equity_curve: List[Dict]
    
    def to_dict(self) -> dict:
        return {
            'strategy_name': self.strategy_name,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'initial_capital': round(self.initial_capital, 2),
            'final_equity': round(self.final_equity, 2),
            'total_return': round(self.total_return, 2),
            'total_return_pct': round(self.total_return_pct, 2),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate, 1),
            'profit_factor': round(self.profit_factor, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct, 2),
            'avg_trade_pnl': round(self.avg_trade_pnl, 2),
            'avg_hold_days': round(self.avg_hold_days, 1),
            'trades': [t.to_dict() for t in self.trades],
            'equity_curve': self.equity_curve
        }


class AlgoTradingService:
    """Manages algo trading strategies and execution."""
    
    def __init__(self, state_file: str = None):
        self.state_file = state_file or os.path.join(Config.DATA_DIR, 'algo_strategies.json')
        self.strategies: Dict[str, Strategy] = {}
        self.market_data = get_market_data_service()
        self.paper_service = get_paper_trading_service()
        self.analyzer = get_analyzer()
        
        # Forward test state
        self.forward_test_positions: Dict[str, Dict] = {}  # strategy_id -> {symbol -> position}
        
        self._load_state()
        self._ensure_examples()
    
    def _load_state(self):
        """Load strategies from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                
                for strat_data in data.get('strategies', []):
                    strat = Strategy.from_dict(strat_data)
                    self.strategies[strat.id] = strat
                
                self.forward_test_positions = data.get('forward_test_positions', {})
                    
            except Exception as e:
                print(f"Error loading algo trading state: {e}")
    
    def _save_state(self):
        """Save strategies to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            data = {
                'strategies': [s.to_dict() for s in self.strategies.values()],
                'forward_test_positions': self.forward_test_positions,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Error saving algo trading state: {e}")
    
    def _ensure_examples(self):
        """Add example strategies if fewer than 4 exist."""
        if len(self.strategies) >= 4:
            return
        
        examples = [
            {
                'name': 'RSI Mean Reversion',
                'symbols': ['SPY', 'AAPL', 'MSFT', 'NVDA'],
                'entry_conditions': [{'type': 'rsi_below', 'value': 30}],
                'exit_conditions': [{'type': 'profit_above', 'value': 10}, {'type': 'loss_above', 'value': 5}, {'type': 'hold_days_above', 'value': 5}],
                'position_size_pct': 20,
                'max_positions': 3,
                'stop_loss_pct': 5,
                'take_profit_pct': 10,
            },
            {
                'name': 'MACD Momentum',
                'symbols': ['AAPL', 'NVDA', 'AMD', 'TSLA'],
                'entry_conditions': [{'type': 'macd_bullish', 'value': 0}, {'type': 'trend_bullish', 'value': 0}],
                'exit_conditions': [{'type': 'profit_above', 'value': 8}, {'type': 'loss_above', 'value': 4}],
                'position_size_pct': 15,
                'max_positions': 4,
                'stop_loss_pct': 4,
                'take_profit_pct': 8,
            },
            {
                'name': 'Trend + Volatility',
                'symbols': ['SPY', 'QQQ'],
                'entry_conditions': [{'type': 'price_above_sma50', 'value': 0}, {'type': 'atr_pct_above', 'value': 1.5}],
                'exit_conditions': [{'type': 'profit_above', 'value': 5}, {'type': 'loss_above', 'value': 3}, {'type': 'hold_days_above', 'value': 10}],
                'position_size_pct': 25,
                'max_positions': 2,
                'stop_loss_pct': 3,
                'take_profit_pct': 5,
            },
            {
                'name': 'RSI Overbought Short',
                'symbols': ['SPY', 'AAPL', 'MSFT'],
                'entry_conditions': [{'type': 'rsi_above', 'value': 70}, {'type': 'regime_trending', 'value': 0}],
                'exit_conditions': [{'type': 'profit_above', 'value': 5}, {'type': 'loss_above', 'value': 3}],
                'position_size_pct': 15,
                'max_positions': 2,
                'stop_loss_pct': 3,
                'take_profit_pct': 5,
            },
        ]
        
        for ex in examples:
            self.create_strategy(**ex)
        print(f"[Algo] Loaded {len(examples)} example strategies")
    
    def create_strategy(self, name: str, symbols: List[str], 
                       entry_conditions: List[Dict], exit_conditions: List[Dict],
                       position_size_pct: float = 10.0, max_positions: int = 5,
                       stop_loss_pct: Optional[float] = None,
                       take_profit_pct: Optional[float] = None) -> Dict[str, Any]:
        """Create a new trading strategy."""
        strat_id = str(uuid.uuid4())[:8]
        
        strategy = Strategy(
            id=strat_id,
            name=name,
            symbols=symbols,
            entry_conditions=[Condition.from_dict(c) for c in entry_conditions],
            exit_conditions=[Condition.from_dict(c) for c in exit_conditions],
            position_size_pct=position_size_pct,
            max_positions=max_positions,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            created_at=datetime.now().isoformat()
        )
        
        self.strategies[strat_id] = strategy
        self._save_state()
        
        return {
            'success': True,
            'strategy': strategy.to_dict(),
            'message': f'Strategy "{name}" created'
        }
    
    def get_strategies(self) -> List[Dict]:
        """Get all strategies."""
        return [s.to_dict() for s in self.strategies.values()]
    
    def get_strategy(self, strategy_id: str) -> Optional[Dict]:
        """Get a specific strategy."""
        if strategy_id in self.strategies:
            return self.strategies[strategy_id].to_dict()
        return None
    
    def delete_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """Delete a strategy."""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            self._save_state()
            return {'success': True, 'message': 'Strategy deleted'}
        return {'success': False, 'error': 'Strategy not found'}
    
    def toggle_strategy(self, strategy_id: str, enabled: bool = None, 
                       is_live: bool = None) -> Dict[str, Any]:
        """Toggle strategy enabled/live status."""
        if strategy_id not in self.strategies:
            return {'success': False, 'error': 'Strategy not found'}
        
        strat = self.strategies[strategy_id]
        
        if enabled is not None:
            strat.enabled = enabled
        
        if is_live is not None:
            strat.is_live = is_live
        
        self._save_state()
        
        return {
            'success': True,
            'strategy': strat.to_dict(),
            'message': f'Strategy updated: enabled={strat.enabled}, live={strat.is_live}'
        }
    
    def _check_condition(self, condition: Condition, analysis: Dict, 
                        position: Optional[Dict] = None) -> bool:
        """Check if a single condition is met."""
        ctype = condition.type
        value = condition.value or 0
        
        # Entry conditions (based on technical analysis)
        if ctype == "rsi_below":
            return analysis.get('rsi', 50) < value
        elif ctype == "rsi_above":
            return analysis.get('rsi', 50) > value
        elif ctype == "rsi_crosses_below":
            return analysis.get('rsi', 50) < value  # Simplified
        elif ctype == "rsi_crosses_above":
            return analysis.get('rsi', 50) > value  # Simplified
        elif ctype == "atr_pct_above":
            return analysis.get('atr_pct', 0) > value
        elif ctype == "atr_pct_below":
            return analysis.get('atr_pct', 0) < value
        elif ctype == "trend_bullish":
            return analysis.get('trend') == 'BULLISH'
        elif ctype == "trend_bearish":
            return analysis.get('trend') == 'BEARISH'
        elif ctype == "trend_neutral":
            return analysis.get('trend') == 'NEUTRAL'
        elif ctype == "macd_bullish":
            return analysis.get('macd_histogram', 0) > 0
        elif ctype == "macd_bearish":
            return analysis.get('macd_histogram', 0) < 0
        elif ctype == "price_above_sma20":
            return analysis.get('price', 0) > analysis.get('sma_20', 0)
        elif ctype == "price_below_sma20":
            return analysis.get('price', 0) < analysis.get('sma_20', 0)
        elif ctype == "price_above_sma50":
            return analysis.get('price', 0) > analysis.get('sma_50', 0)
        elif ctype == "price_below_sma50":
            return analysis.get('price', 0) < analysis.get('sma_50', 0)
        elif ctype == "adx_above":
            return analysis.get('adx', 0) > value
        elif ctype == "adx_below":
            return analysis.get('adx', 0) < value
        elif ctype == "regime_trending":
            return analysis.get('regime') == 'TRENDING'
        elif ctype == "regime_choppy":
            return analysis.get('regime') == 'CHOPPY'
        elif ctype == "regime_squeeze":
            return analysis.get('regime') == 'SQUEEZE'
        
        # Exit conditions (based on position)
        elif ctype == "profit_above" and position:
            pnl_pct = ((analysis.get('price', 0) - position['entry_price']) / position['entry_price']) * 100
            return pnl_pct > value
        elif ctype == "loss_above" and position:
            pnl_pct = ((analysis.get('price', 0) - position['entry_price']) / position['entry_price']) * 100
            return pnl_pct < -value
        elif ctype == "hold_days_above" and position:
            entry_date = datetime.fromisoformat(position['entry_date'])
            hold_days = (datetime.now() - entry_date).days
            return hold_days > value
        
        return False
    
    def _check_entry_conditions(self, strategy: Strategy, analysis: Dict) -> bool:
        """Check if all entry conditions are met (AND logic)."""
        if not strategy.entry_conditions:
            return False
        
        for condition in strategy.entry_conditions:
            if not self._check_condition(condition, analysis):
                return False
        return True
    
    def _check_exit_conditions(self, strategy: Strategy, analysis: Dict, 
                               position: Dict) -> tuple[bool, str]:
        """Check if any exit condition is met (OR logic)."""
        # Check stop loss first
        if strategy.stop_loss_pct:
            pnl_pct = ((analysis.get('price', 0) - position['entry_price']) / position['entry_price']) * 100
            if pnl_pct < -strategy.stop_loss_pct:
                return True, "stop_loss"
        
        # Check take profit
        if strategy.take_profit_pct:
            pnl_pct = ((analysis.get('price', 0) - position['entry_price']) / position['entry_price']) * 100
            if pnl_pct > strategy.take_profit_pct:
                return True, "take_profit"
        
        # Check custom exit conditions
        for condition in strategy.exit_conditions:
            if self._check_condition(condition, analysis, position):
                return True, condition.type
        
        return False, ""
    
    def backtest(self, strategy_id: str = None, strategy_config: Dict = None,
                symbols: List[str] = None, period: str = "1y",
                initial_capital: float = 10000.0) -> Dict[str, Any]:
        """Run a backtest on historical data."""
        if not HAS_YFINANCE:
            return {'success': False, 'error': 'yfinance not installed'}
        
        # Get strategy
        if strategy_id and strategy_id in self.strategies:
            strategy = self.strategies[strategy_id]
        elif strategy_config:
            strategy = Strategy(
                id='backtest',
                name=strategy_config.get('name', 'Backtest'),
                symbols=strategy_config.get('symbols', ['SPY']),
                entry_conditions=[Condition.from_dict(c) for c in strategy_config.get('entry_conditions', [])],
                exit_conditions=[Condition.from_dict(c) for c in strategy_config.get('exit_conditions', [])],
                position_size_pct=strategy_config.get('position_size_pct', 10.0),
                max_positions=strategy_config.get('max_positions', 5),
                stop_loss_pct=strategy_config.get('stop_loss_pct'),
                take_profit_pct=strategy_config.get('take_profit_pct')
            )
        else:
            return {'success': False, 'error': 'Strategy required'}
        
        symbols_to_test = symbols or strategy.symbols
        if not symbols_to_test:
            return {'success': False, 'error': 'No symbols to test'}
        
        # Collect historical data for all symbols
        all_data = {}
        for symbol in symbols_to_test:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period, interval="1d")
                if not hist.empty:
                    all_data[symbol] = hist
            except Exception as e:
                print(f"Error getting data for {symbol}: {e}")
        
        if not all_data:
            return {'success': False, 'error': 'No historical data available'}
        
        # Run backtest
        cash = initial_capital
        positions: Dict[str, Dict] = {}  # symbol -> {entry_price, entry_date, shares}
        trades: List[BacktestTrade] = []
        equity_curve = []
        
        # Get common date range — use integer indexing to avoid timezone issues
        max_len = max(len(h) for h in all_data.values())
        
        # Use the longest history as the date spine
        primary_hist = max(all_data.values(), key=len)
        
        for day_idx in range(20, len(primary_hist)):
            date_str = primary_hist.index[day_idx].strftime('%Y-%m-%d')
            date = primary_hist.index[day_idx].to_pydatetime().replace(tzinfo=None)
            
            # Calculate current equity
            total_equity = cash
            for sym, pos in positions.items():
                if sym in all_data:
                    hist = all_data[sym]
                    try:
                        matching = hist.index.strftime('%Y-%m-%d') == date_str
                        if matching.any():
                            idx = matching.values.nonzero()[0][-1]
                            current_price = float(hist.iloc[idx]['Close'])
                            total_equity += current_price * pos['shares']
                    except:
                        pass
            
            equity_curve.append({
                'date': date_str,
                'equity': round(total_equity, 2)
            })
            
            # Process each symbol
            for symbol in symbols_to_test:
                if symbol not in all_data:
                    continue
                
                hist = all_data[symbol]
                
                # Get data up to this date — use matching date string
                try:
                    matching = hist.index.strftime('%Y-%m-%d') == date_str
                    if not matching.any():
                        continue
                    idx = int(matching.nonzero()[0][-1])
                    if idx < 20:
                        continue
                except Exception as e:
                    print(f"  Index error for {symbol} on {date_str}: {e}")
                    continue
                
                # Calculate indicators for analysis
                close_data = hist.iloc[:idx+1]['Close'].values
                high_data = hist.iloc[:idx+1]['High'].values
                low_data = hist.iloc[:idx+1]['Low'].values
                current_price = float(close_data[-1])
                
                analysis = self._calculate_indicators(close_data, high_data, low_data, current_price)
                
                # Check exits first
                if symbol in positions:
                    pos = positions[symbol]
                    should_exit, exit_reason = self._check_exit_conditions(strategy, analysis, pos)
                    
                    if should_exit:
                        # Close position
                        pnl = (current_price - pos['entry_price']) * pos['shares']
                        pnl_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                        entry_date = datetime.fromisoformat(pos['entry_date'])
                        hold_days = (date - entry_date).days
                        
                        trades.append(BacktestTrade(
                            symbol=symbol,
                            entry_date=pos['entry_date'],
                            entry_price=pos['entry_price'],
                            exit_date=date_str,
                            exit_price=current_price,
                            shares=pos['shares'],
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            hold_days=hold_days,
                            exit_reason=exit_reason
                        ))
                        
                        cash += current_price * pos['shares']
                        del positions[symbol]
                
                # Check entries
                elif symbol not in positions and len(positions) < strategy.max_positions:
                    if self._check_entry_conditions(strategy, analysis):
                        # Calculate position size
                        position_value = total_equity * (strategy.position_size_pct / 100)
                        shares = int(position_value / current_price)
                        
                        if shares > 0 and cash >= shares * current_price:
                            positions[symbol] = {
                                'entry_price': current_price,
                                'entry_date': date_str,
                                'shares': shares
                            }
                            cash -= shares * current_price
        
        # Close any remaining positions at the end
        if positions:
            last_date = primary_hist.index[-1].strftime('%Y-%m-%d')
            for symbol, pos in list(positions.items()):
                if symbol in all_data:
                    hist = all_data[symbol]
                    current_price = float(hist.iloc[-1]['Close'])
                    pnl = (current_price - pos['entry_price']) * pos['shares']
                    pnl_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                    entry_date = datetime.fromisoformat(pos['entry_date'])
                    hold_days = (datetime.strptime(last_date, '%Y-%m-%d') - entry_date).days
                    
                    trades.append(BacktestTrade(
                        symbol=symbol,
                        entry_date=pos['entry_date'],
                        entry_price=pos['entry_price'],
                        exit_date=last_date,
                        exit_price=current_price,
                        shares=pos['shares'],
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        hold_days=hold_days,
                        exit_reason='end_of_backtest'
                    ))
                    
                    cash += current_price * pos['shares']
        
        # Calculate statistics
        final_equity = cash
        total_return = final_equity - initial_capital
        total_return_pct = (total_return / initial_capital) * 100
        
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        
        win_rate = (len(winning_trades) / len(trades) * 100) if trades else 0
        
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
        
        # Sharpe ratio (simplified)
        if len(equity_curve) > 1:
            returns = []
            for i in range(1, len(equity_curve)):
                prev = equity_curve[i-1]['equity']
                curr = equity_curve[i]['equity']
                if prev > 0:
                    returns.append((curr - prev) / prev)
            
            if returns:
                avg_return = sum(returns) / len(returns)
                std_return = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 1
                sharpe_ratio = (avg_return / std_return) * math.sqrt(252) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        # Max drawdown
        peak = initial_capital
        max_dd = 0
        max_dd_pct = 0
        for point in equity_curve:
            equity = point['equity']
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = (dd / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
        
        avg_trade_pnl = sum(t.pnl for t in trades) / len(trades) if trades else 0
        avg_hold_days = sum(t.hold_days for t in trades) / len(trades) if trades else 0
        
        result = BacktestResult(
            strategy_name=strategy.name,
            start_date=primary_hist.index[20].strftime('%Y-%m-%d'),
            end_date=primary_hist.index[-1].strftime('%Y-%m-%d'),
            initial_capital=initial_capital,
            final_equity=final_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            avg_trade_pnl=avg_trade_pnl,
            avg_hold_days=avg_hold_days,
            trades=trades,
            equity_curve=equity_curve
        )
        
        return {
            'success': True,
            'result': result.to_dict()
        }
    
    def _calculate_indicators(self, close: list, high: list, low: list, price: float) -> Dict:
        """Calculate technical indicators for backtesting."""
        # RSI
        rsi = self._calc_rsi(close, 14)
        
        # SMA
        sma_20 = sum(close[-20:]) / 20 if len(close) >= 20 else price
        sma_50 = sum(close[-50:]) / 50 if len(close) >= 50 else price
        
        # MACD — compute full MACD line then signal from that
        ema_12 = self._calc_ema(close, 12)
        ema_26 = self._calc_ema(close, 26)
        macd = ema_12 - ema_26
        # Build MACD history for signal calculation
        macd_history = []
        for i in range(26, len(close)):
            e12 = self._calc_ema(close[:i+1], 12)
            e26 = self._calc_ema(close[:i+1], 26)
            macd_history.append(e12 - e26)
        macd_signal = self._calc_ema(macd_history, 9) if len(macd_history) >= 9 else macd
        macd_histogram = macd - macd_signal
        
        # ATR
        atr = self._calc_atr(high, low, close, 14)
        atr_pct = (atr / price) * 100 if price > 0 else 0
        
        # ADX (simplified)
        adx = self._calc_adx(high, low, close, 14)
        
        # Trend
        if price > sma_50 and sma_20 > sma_50 and macd_histogram > 0:
            trend = 'BULLISH'
        elif price < sma_50 and sma_20 < sma_50 and macd_histogram < 0:
            trend = 'BEARISH'
        else:
            trend = 'NEUTRAL'
        
        # Regime
        if adx > 25:
            regime = 'TRENDING'
        elif adx < 20:
            regime = 'CHOPPY'
        else:
            regime = 'SQUEEZE'
        
        return {
            'price': price,
            'rsi': rsi,
            'sma_20': sma_20,
            'sma_50': sma_50,
            'macd': macd,
            'macd_signal': macd_signal,
            'macd_histogram': macd_histogram,
            'atr': atr,
            'atr_pct': atr_pct,
            'adx': adx,
            'trend': trend,
            'regime': regime
        }
    
    def _calc_rsi(self, prices: list, period: int = 14) -> float:
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
    
    def _calc_ema(self, prices, period: int) -> float:
        prices = list(prices) if not isinstance(prices, list) else prices
        if len(prices) < period:
            return float(prices[-1]) if len(prices) > 0 else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def _calc_atr(self, high: list, low: list, close: list, period: int = 14) -> float:
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
    
    def _calc_adx(self, high: list, low: list, close: list, period: int = 14) -> float:
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
    
    def compare_strategies(self, strategy_ids: List[str], period: str = "1y",
                          initial_capital: float = 10000.0, 
                          symbols: List[str] = None) -> Dict[str, Any]:
        """Run backtests on multiple strategies for comparison."""
        if not strategy_ids:
            return {'success': False, 'error': 'No strategy IDs provided'}
        
        results = []
        for strategy_id in strategy_ids:
            if strategy_id not in self.strategies:
                results.append({
                    'strategy_id': strategy_id,
                    'success': False,
                    'error': 'Strategy not found'
                })
                continue
            
            # Run backtest for this strategy
            bt_result = self.backtest(
                strategy_id=strategy_id,
                symbols=symbols,
                period=period,
                initial_capital=initial_capital
            )
            
            if bt_result.get('success'):
                result_data = bt_result['result']
                result_data['strategy_id'] = strategy_id
                results.append({
                    'strategy_id': strategy_id,
                    'success': True,
                    'result': result_data
                })
            else:
                results.append({
                    'strategy_id': strategy_id,
                    'success': False,
                    'error': bt_result.get('error', 'Backtest failed')
                })
        
        return {
            'success': True,
            'results': results,
            'period': period,
            'initial_capital': initial_capital
        }

    def get_condition_types(self) -> Dict[str, List[Dict]]:
        """Get available condition types for UI."""
        return {
            'entry_conditions': [
                {'value': 'rsi_below', 'label': 'RSI Below', 'needs_value': True, 'default': 30},
                {'value': 'rsi_above', 'label': 'RSI Above', 'needs_value': True, 'default': 70},
                {'value': 'rsi_crosses_below', 'label': 'RSI Crosses Below', 'needs_value': True, 'default': 30},
                {'value': 'rsi_crosses_above', 'label': 'RSI Crosses Above', 'needs_value': True, 'default': 70},
                {'value': 'atr_pct_above', 'label': 'ATR% Above', 'needs_value': True, 'default': 2},
                {'value': 'atr_pct_below', 'label': 'ATR% Below', 'needs_value': True, 'default': 1},
                {'value': 'trend_bullish', 'label': 'Trend = BULLISH', 'needs_value': False},
                {'value': 'trend_bearish', 'label': 'Trend = BEARISH', 'needs_value': False},
                {'value': 'trend_neutral', 'label': 'Trend = NEUTRAL', 'needs_value': False},
                {'value': 'macd_bullish', 'label': 'MACD Bullish', 'needs_value': False},
                {'value': 'macd_bearish', 'label': 'MACD Bearish', 'needs_value': False},
                {'value': 'price_above_sma20', 'label': 'Price > SMA20', 'needs_value': False},
                {'value': 'price_below_sma20', 'label': 'Price < SMA20', 'needs_value': False},
                {'value': 'price_above_sma50', 'label': 'Price > SMA50', 'needs_value': False},
                {'value': 'price_below_sma50', 'label': 'Price < SMA50', 'needs_value': False},
                {'value': 'adx_above', 'label': 'ADX Above', 'needs_value': True, 'default': 25},
                {'value': 'adx_below', 'label': 'ADX Below', 'needs_value': True, 'default': 20},
                {'value': 'regime_trending', 'label': 'Regime = TRENDING', 'needs_value': False},
                {'value': 'regime_choppy', 'label': 'Regime = CHOPPY', 'needs_value': False},
                {'value': 'regime_squeeze', 'label': 'Regime = SQUEEZE', 'needs_value': False},
            ],
            'exit_conditions': [
                {'value': 'profit_above', 'label': 'Profit % Above', 'needs_value': True, 'default': 15},
                {'value': 'loss_above', 'label': 'Loss % Above', 'needs_value': True, 'default': 8},
                {'value': 'hold_days_above', 'label': 'Hold Days Above', 'needs_value': True, 'default': 3},
                {'value': 'rsi_above', 'label': 'RSI Above', 'needs_value': True, 'default': 70},
                {'value': 'rsi_below', 'label': 'RSI Below', 'needs_value': True, 'default': 30},
                {'value': 'macd_bearish', 'label': 'MACD Bearish', 'needs_value': False},
                {'value': 'macd_bullish', 'label': 'MACD Bullish', 'needs_value': False},
                {'value': 'trend_bearish', 'label': 'Trend Turns BEARISH', 'needs_value': False},
                {'value': 'trend_neutral', 'label': 'Trend Turns NEUTRAL', 'needs_value': False},
            ]
        }


# Singleton instance
_algo_service = None

def get_algo_trading_service() -> AlgoTradingService:
    global _algo_service
    if _algo_service is None:
        _algo_service = AlgoTradingService()
    return _algo_service