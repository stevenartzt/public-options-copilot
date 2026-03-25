"""
Paper Trading Service
Virtual portfolio for practice trading without real money.
Works without any API keys - uses yfinance for price data.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from config import Config
from .market_data import get_market_data_service


class TradeType(Enum):
    BUY = "BUY"
    SELL = "SELL"


class AssetType(Enum):
    STOCK = "STOCK"
    OPTION = "OPTION"


@dataclass
class PaperTrade:
    """Record of a paper trade."""
    id: str
    timestamp: str
    symbol: str
    asset_type: str
    trade_type: str
    quantity: int
    price: float
    total_value: float
    notes: str = ""
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'asset_type': self.asset_type,
            'trade_type': self.trade_type,
            'quantity': self.quantity,
            'price': round(self.price, 2),
            'total_value': round(self.total_value, 2),
            'notes': self.notes
        }


@dataclass
class PaperPosition:
    """A position in the paper portfolio."""
    symbol: str
    asset_type: str
    quantity: int
    average_price: float
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pl: float = 0.0
    unrealized_pl_pct: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'asset_type': self.asset_type,
            'quantity': self.quantity,
            'average_price': round(self.average_price, 2),
            'current_price': round(self.current_price, 2),
            'market_value': round(self.market_value, 2),
            'unrealized_pl': round(self.unrealized_pl, 2),
            'unrealized_pl_pct': round(self.unrealized_pl_pct, 2)
        }


class PaperTradingService:
    """Manages paper trading portfolio and trades."""
    
    def __init__(self, state_file: str = None):
        self.state_file = state_file or Config.PAPER_STATE_FILE
        self.starting_balance = Config.PAPER_STARTING_BALANCE
        self.market_data = get_market_data_service()
        
        # State
        self.cash: float = self.starting_balance
        self.positions: Dict[str, PaperPosition] = {}
        self.trades: List[PaperTrade] = []
        self.equity_history: List[Dict] = []
        
        # Stats
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.total_pnl: float = 0.0
        
        # Load existing state
        self._load_state()
    
    def _load_state(self):
        """Load state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                
                self.cash = data.get('cash', self.starting_balance)
                self.total_trades = data.get('total_trades', 0)
                self.winning_trades = data.get('winning_trades', 0)
                self.losing_trades = data.get('losing_trades', 0)
                self.total_pnl = data.get('total_pnl', 0.0)
                
                # Load positions
                for sym, pos_data in data.get('positions', {}).items():
                    self.positions[sym] = PaperPosition(
                        symbol=pos_data['symbol'],
                        asset_type=pos_data['asset_type'],
                        quantity=pos_data['quantity'],
                        average_price=pos_data['average_price']
                    )
                
                # Load trades
                for trade_data in data.get('trades', []):
                    self.trades.append(PaperTrade(
                        id=trade_data['id'],
                        timestamp=trade_data['timestamp'],
                        symbol=trade_data['symbol'],
                        asset_type=trade_data['asset_type'],
                        trade_type=trade_data['trade_type'],
                        quantity=trade_data['quantity'],
                        price=trade_data['price'],
                        total_value=trade_data['total_value'],
                        notes=trade_data.get('notes', '')
                    ))
                
                # Load equity history
                self.equity_history = data.get('equity_history', [])
                
            except Exception as e:
                print(f"Error loading paper trading state: {e}")
    
    def _save_state(self):
        """Save state to file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            data = {
                'cash': self.cash,
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'total_pnl': self.total_pnl,
                'positions': {sym: pos.to_dict() for sym, pos in self.positions.items()},
                'trades': [t.to_dict() for t in self.trades],
                'equity_history': self.equity_history[-100:],  # Keep last 100 points
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Error saving paper trading state: {e}")
    
    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        return f"PT{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        quote = self.market_data.get_quote(symbol)
        return quote.get('price') if quote else None
    
    def _refresh_positions(self):
        """Update current prices and P/L for all positions."""
        for symbol, position in self.positions.items():
            price = self._get_current_price(symbol)
            if price:
                position.current_price = price
                position.market_value = price * position.quantity
                cost_basis = position.average_price * position.quantity
                position.unrealized_pl = position.market_value - cost_basis
                position.unrealized_pl_pct = (position.unrealized_pl / cost_basis) * 100 if cost_basis else 0
    
    def buy(self, symbol: str, quantity: int, price: Optional[float] = None, 
            asset_type: str = "STOCK", notes: str = "") -> Dict[str, Any]:
        """Execute a paper buy order."""
        # Get price
        if price is None:
            price = self._get_current_price(symbol)
            if price is None:
                return {'success': False, 'error': f'Could not get price for {symbol}'}
        
        total_cost = price * quantity
        
        # Check buying power
        if total_cost > self.cash:
            return {'success': False, 'error': f'Insufficient funds. Need ${total_cost:.2f}, have ${self.cash:.2f}'}
        
        # Deduct cash
        self.cash -= total_cost
        
        # Update or create position
        if symbol in self.positions:
            pos = self.positions[symbol]
            total_shares = pos.quantity + quantity
            total_cost_basis = (pos.average_price * pos.quantity) + (price * quantity)
            pos.average_price = total_cost_basis / total_shares
            pos.quantity = total_shares
        else:
            self.positions[symbol] = PaperPosition(
                symbol=symbol,
                asset_type=asset_type,
                quantity=quantity,
                average_price=price
            )
        
        # Record trade
        trade = PaperTrade(
            id=self._generate_trade_id(),
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            asset_type=asset_type,
            trade_type="BUY",
            quantity=quantity,
            price=price,
            total_value=total_cost,
            notes=notes
        )
        self.trades.append(trade)
        self.total_trades += 1
        
        # Save state
        self._save_state()
        
        return {
            'success': True,
            'trade': trade.to_dict(),
            'message': f'Bought {quantity} {symbol} @ ${price:.2f}'
        }
    
    def sell(self, symbol: str, quantity: int, price: Optional[float] = None,
             notes: str = "") -> Dict[str, Any]:
        """Execute a paper sell order."""
        # Check position exists
        if symbol not in self.positions:
            return {'success': False, 'error': f'No position in {symbol}'}
        
        pos = self.positions[symbol]
        
        # Check quantity
        if quantity > pos.quantity:
            return {'success': False, 'error': f'Only have {pos.quantity} shares of {symbol}'}
        
        # Get price
        if price is None:
            price = self._get_current_price(symbol)
            if price is None:
                return {'success': False, 'error': f'Could not get price for {symbol}'}
        
        total_value = price * quantity
        
        # Calculate P/L for this sale
        cost_basis = pos.average_price * quantity
        pnl = total_value - cost_basis
        
        # Add cash
        self.cash += total_value
        
        # Update position
        pos.quantity -= quantity
        if pos.quantity == 0:
            del self.positions[symbol]
        
        # Update stats
        self.total_pnl += pnl
        if pnl >= 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        # Record trade
        trade = PaperTrade(
            id=self._generate_trade_id(),
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            asset_type=pos.asset_type,
            trade_type="SELL",
            quantity=quantity,
            price=price,
            total_value=total_value,
            notes=f"{notes} | P/L: ${pnl:.2f}"
        )
        self.trades.append(trade)
        self.total_trades += 1
        
        # Save state
        self._save_state()
        
        return {
            'success': True,
            'trade': trade.to_dict(),
            'pnl': round(pnl, 2),
            'message': f'Sold {quantity} {symbol} @ ${price:.2f} (P/L: ${pnl:.2f})'
        }
    
    def get_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio state."""
        self._refresh_positions()
        
        # Calculate totals
        positions_value = sum(p.market_value for p in self.positions.values())
        total_equity = self.cash + positions_value
        total_unrealized_pl = sum(p.unrealized_pl for p in self.positions.values())
        
        # Record equity point
        self._record_equity(total_equity)
        
        return {
            'cash': round(self.cash, 2),
            'positions_value': round(positions_value, 2),
            'total_equity': round(total_equity, 2),
            'starting_balance': self.starting_balance,
            'total_return': round(total_equity - self.starting_balance, 2),
            'total_return_pct': round(((total_equity - self.starting_balance) / self.starting_balance) * 100, 2),
            'unrealized_pl': round(total_unrealized_pl, 2),
            'realized_pnl': round(self.total_pnl, 2),
            'positions': [p.to_dict() for p in self.positions.values()],
            'stats': {
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'win_rate': round((self.winning_trades / self.total_trades) * 100, 1) if self.total_trades > 0 else 0
            }
        }
    
    def _record_equity(self, equity: float):
        """Record equity point for chart."""
        self.equity_history.append({
            'timestamp': datetime.now().isoformat(),
            'equity': round(equity, 2)
        })
        
        # Keep last 100 points
        if len(self.equity_history) > 100:
            self.equity_history = self.equity_history[-100:]
    
    def get_equity_history(self) -> List[Dict]:
        """Get equity history for charting."""
        return self.equity_history
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get recent trade history."""
        return [t.to_dict() for t in self.trades[-limit:]][::-1]  # Most recent first
    
    def reset(self) -> Dict[str, Any]:
        """Reset paper portfolio to starting state."""
        self.cash = self.starting_balance
        self.positions = {}
        self.trades = []
        self.equity_history = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        
        self._save_state()
        
        return {
            'success': True,
            'message': f'Portfolio reset to ${self.starting_balance:.2f}'
        }


# Singleton instance
_paper_service = None

def get_paper_trading_service() -> PaperTradingService:
    global _paper_service
    if _paper_service is None:
        _paper_service = PaperTradingService()
    return _paper_service
