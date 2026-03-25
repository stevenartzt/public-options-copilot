"""
Trading Service - Order placement via Public.com SDK.
Handles both stock and option orders.
"""

import uuid
from typing import Dict, Any, Optional
from decimal import Decimal

from config import Config, has_api_credentials

# Try to import Public SDK
try:
    from public_api_sdk import (
        PublicApiClient,
        ApiKeyAuthConfig,
        PublicApiClientConfiguration,
        OrderInstrument,
        InstrumentType,
        OrderRequest,
        OrderSide,
        OrderType,
        TimeInForce,
        OrderExpirationRequest,
        OpenCloseIndicator,
        PreflightRequest
    )
    HAS_SDK = True
except ImportError:
    HAS_SDK = False


class TradingService:
    """Handles order placement via Public.com API."""
    
    def __init__(self):
        self.client: Optional[Any] = None
        self._init_client()
    
    def _init_client(self):
        """Initialize Public API client."""
        if not HAS_SDK:
            return
        
        if not has_api_credentials():
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
            print(f"Failed to initialize trading client: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if real trading is available."""
        return self.client is not None
    
    def _is_option_symbol(self, symbol: str) -> bool:
        """Check if symbol is an option (OSI format)."""
        return len(symbol) > 10
    
    def preflight(self, symbol: str, side: str, quantity: int, 
                  limit_price: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculate order preflight (fees, buying power impact).
        """
        if not self.is_available():
            return {'success': False, 'error': 'Trading not available'}
        
        try:
            is_option = self._is_option_symbol(symbol)
            
            instrument = OrderInstrument(
                symbol=symbol,
                type=InstrumentType.OPTION if is_option else InstrumentType.EQUITY
            )
            
            preflight_req = PreflightRequest(
                instrument=instrument,
                order_side=OrderSide.BUY if side.upper() == 'BUY' else OrderSide.SELL,
                order_type=OrderType.LIMIT if limit_price else OrderType.MARKET,
                quantity=Decimal(str(quantity)),
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                expiration=OrderExpirationRequest(time_in_force=TimeInForce.DAY),
                open_close_indicator=OpenCloseIndicator.OPEN if side.upper() == 'BUY' else OpenCloseIndicator.CLOSE
            )
            
            result = self.client.perform_preflight_calculation(preflight_req)
            
            return {
                'success': True,
                'preflight': {
                    'order_value': float(result.order_value) if result.order_value else 0,
                    'estimated_commission': float(result.estimated_commission) if result.estimated_commission else 0,
                    'estimated_cost': float(result.estimated_cost) if result.estimated_cost else 0,
                    'buying_power_requirement': float(result.buying_power_requirement) if result.buying_power_requirement else 0,
                    'estimated_quantity': float(result.estimated_quantity) if result.estimated_quantity else quantity,
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def place_order(self, symbol: str, side: str, quantity: int,
                    limit_price: Optional[float] = None,
                    order_type: str = "LIMIT") -> Dict[str, Any]:
        """
        Place an order.
        
        Args:
            symbol: Stock or option symbol
            side: BUY or SELL
            quantity: Number of shares/contracts
            limit_price: Limit price (required for LIMIT orders)
            order_type: LIMIT or MARKET
        """
        if not self.is_available():
            return {'success': False, 'error': 'Trading not available - add API credentials'}
        
        try:
            is_option = self._is_option_symbol(symbol)
            
            instrument = OrderInstrument(
                symbol=symbol,
                type=InstrumentType.OPTION if is_option else InstrumentType.EQUITY
            )
            
            order_id = str(uuid.uuid4())
            
            # Determine order type
            if order_type.upper() == "MARKET":
                ot = OrderType.MARKET
            else:
                ot = OrderType.LIMIT
                if not limit_price:
                    return {'success': False, 'error': 'Limit price required for LIMIT orders'}
            
            # Determine open/close for options
            open_close = OpenCloseIndicator.OPEN if side.upper() == 'BUY' else OpenCloseIndicator.CLOSE
            
            order_req = OrderRequest(
                order_id=order_id,
                instrument=instrument,
                order_side=OrderSide.BUY if side.upper() == 'BUY' else OrderSide.SELL,
                order_type=ot,
                quantity=Decimal(str(quantity)),
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                expiration=OrderExpirationRequest(time_in_force=TimeInForce.DAY),
                open_close_indicator=open_close
            )
            
            new_order = self.client.place_order(order_req)
            
            return {
                'success': True,
                'order_id': new_order.order_id,
                'message': f'{side} {quantity} {symbol} @ ${limit_price:.2f}' if limit_price else f'{side} {quantity} {symbol} (market)'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order status."""
        if not self.is_available():
            return {'success': False, 'error': 'Trading not available'}
        
        try:
            order = self.client.get_order(order_id)
            
            return {
                'success': True,
                'order': {
                    'order_id': order.order_id,
                    'symbol': order.instrument.symbol,
                    'side': order.side.value,
                    'type': order.type.value,
                    'status': order.status.value,
                    'quantity': float(order.quantity) if order.quantity else None,
                    'filled_quantity': float(order.filled_quantity) if order.filled_quantity else None,
                    'average_price': float(order.average_price) if order.average_price else None,
                    'limit_price': float(order.limit_price) if order.limit_price else None,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                    'closed_at': order.closed_at.isoformat() if order.closed_at else None,
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        if not self.is_available():
            return {'success': False, 'error': 'Trading not available'}
        
        try:
            self.client.cancel_order(order_id)
            return {
                'success': True,
                'message': f'Order {order_id} cancellation requested'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_open_orders(self) -> Dict[str, Any]:
        """Get all open/pending orders."""
        if not self.is_available():
            return {'success': False, 'error': 'Trading not available'}
        
        try:
            portfolio = self.client.get_portfolio()
            
            open_orders = []
            if portfolio.orders:
                for order in portfolio.orders:
                    status = order.status.value if hasattr(order.status, 'value') else str(order.status)
                    if status in ['NEW', 'PARTIALLY_FILLED', 'PENDING_REPLACE', 'PENDING_CANCEL']:
                        open_orders.append({
                            'order_id': order.order_id,
                            'symbol': order.instrument.symbol if order.instrument else "N/A",
                            'side': order.side.value if hasattr(order.side, 'value') else str(order.side),
                            'type': order.type.value if hasattr(order.type, 'value') else str(order.type),
                            'status': status,
                            'quantity': float(order.quantity) if order.quantity else 0,
                            'filled_quantity': float(order.filled_quantity) if order.filled_quantity else 0,
                            'limit_price': float(order.limit_price) if order.limit_price else None,
                            'created_at': order.created_at.isoformat() if order.created_at else None,
                        })
            
            return {
                'success': True,
                'orders': open_orders
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Singleton instance
_trading_service = None

def get_trading_service() -> TradingService:
    global _trading_service
    if _trading_service is None:
        _trading_service = TradingService()
    return _trading_service
