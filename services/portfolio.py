"""
Portfolio Service - Public.com SDK integration for real portfolio.
Requires API credentials to function.
"""

from typing import Dict, List, Optional, Any
from decimal import Decimal

from config import Config, has_api_credentials

# Try to import Public SDK
try:
    from public_api_sdk import (
        PublicApiClient,
        ApiKeyAuthConfig,
        PublicApiClientConfiguration,
        OrderInstrument,
        InstrumentType
    )
    HAS_SDK = True
except ImportError:
    HAS_SDK = False


class PortfolioService:
    """Manages real portfolio via Public.com API."""
    
    def __init__(self):
        self.client: Optional[Any] = None
        self._init_client()
    
    def _init_client(self):
        """Initialize Public API client."""
        if not HAS_SDK:
            print("Public SDK not installed. Real trading unavailable.")
            return
        
        if not has_api_credentials():
            print("No API credentials. Real trading unavailable.")
            return
        
        try:
            config = PublicApiClientConfiguration(
                default_account_number=Config.PUBLIC_ACCOUNT_ID
            )
            self.client = PublicApiClient(
                ApiKeyAuthConfig(api_secret_key=Config.PUBLIC_API_KEY),
                config=config
            )
            print("Public API client initialized successfully")
        except Exception as e:
            print(f"Failed to initialize Public API client: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if real portfolio features are available."""
        return self.client is not None
    
    def get_portfolio(self) -> Dict[str, Any]:
        """Get real portfolio from Public.com."""
        if not self.is_available():
            return {
                'success': False,
                'error': 'Portfolio not available - add API credentials to .env'
            }
        
        try:
            portfolio = self.client.get_portfolio()
            
            # Extract positions
            positions = []
            if portfolio.positions:
                # Batch fetch quotes for bid/ask
                quote_map = {}
                try:
                    instruments = [pos.instrument for pos in portfolio.positions]
                    if instruments:
                        quotes = self.client.get_quotes(instruments)
                        for q in quotes:
                            if q.instrument:
                                quote_map[q.instrument.symbol] = q
                except Exception as e:
                    print(f"Error fetching quotes: {e}")
                
                for pos in portfolio.positions:
                    cost_basis = pos.cost_basis
                    total_cost = float(cost_basis.total_cost) if cost_basis and cost_basis.total_cost else 0
                    unit_cost = float(cost_basis.unit_cost) if cost_basis and cost_basis.unit_cost else 0
                    gain_value = float(cost_basis.gain_value) if cost_basis and cost_basis.gain_value else 0
                    gain_pct = float(cost_basis.gain_percentage) if cost_basis and cost_basis.gain_percentage else 0
                    
                    current_price = 0
                    if pos.last_price and pos.last_price.last_price:
                        current_price = float(pos.last_price.last_price)
                    
                    # Get bid/ask from quotes
                    bid_price = None
                    ask_price = None
                    quote = quote_map.get(pos.instrument.symbol)
                    if quote:
                        bid_price = float(quote.bid) if quote.bid else None
                        ask_price = float(quote.ask) if quote.ask else None
                        if quote.last:
                            current_price = float(quote.last)
                    
                    position_data = {
                        "symbol": pos.instrument.symbol,
                        "name": pos.instrument.name,
                        "type": pos.instrument.type.value if hasattr(pos.instrument.type, 'value') else str(pos.instrument.type),
                        "quantity": float(pos.quantity) if pos.quantity else 0,
                        "market_value": float(pos.current_value) if pos.current_value else 0,
                        "cost_basis": total_cost,
                        "average_price": unit_cost,
                        "current_price": current_price,
                        "bid": bid_price,
                        "ask": ask_price,
                        "unrealized_pl": gain_value,
                        "unrealized_pl_percent": gain_pct,
                    }
                    positions.append(position_data)
            
            # Extract account info
            total_equity = sum(float(e.value) for e in portfolio.equity) if portfolio.equity else 0
            cash_value = 0
            for e in portfolio.equity:
                if e.type.value == 'CASH':
                    cash_value = float(e.value)
                    break
            
            account_info = {
                "equity": total_equity,
                "cash": cash_value,
                "buying_power": float(portfolio.buying_power.buying_power) if portfolio.buying_power else 0,
                "options_buying_power": float(portfolio.buying_power.options_buying_power) if portfolio.buying_power else 0,
            }
            
            return {
                "success": True,
                "positions": positions,
                "account": account_info
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_quote(self, symbol: str, instrument_type: str = "EQUITY") -> Dict[str, Any]:
        """Get quote for a symbol."""
        if not self.is_available():
            return {'success': False, 'error': 'API not available'}
        
        try:
            inst_type = InstrumentType.OPTION if instrument_type.upper() == "OPTION" else InstrumentType.EQUITY
            instrument = OrderInstrument(symbol=symbol, type=inst_type)
            
            quotes = self.client.get_quotes([instrument])
            
            if quotes:
                q = quotes[0]
                return {
                    'success': True,
                    'quote': {
                        'symbol': symbol,
                        'bid': float(q.bid) if q.bid else None,
                        'ask': float(q.ask) if q.ask else None,
                        'last': float(q.last) if q.last else None,
                        'volume': int(q.volume) if q.volume else None
                    }
                }
            
            return {'success': False, 'error': 'No quote data'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_option_chain(self, symbol: str, expiration: str = None) -> Dict[str, Any]:
        """Get option chain from Public API."""
        if not self.is_available():
            return {'success': False, 'error': 'API not available'}
        
        try:
            from public_api_sdk import OptionChainRequest, OptionExpirationsRequest
            
            instrument = OrderInstrument(symbol=symbol, type=InstrumentType.EQUITY)
            
            # Get expirations if not provided
            if not expiration:
                exp_request = OptionExpirationsRequest(instrument=instrument)
                exp_response = self.client.get_option_expirations(exp_request)
                if not exp_response.expirations:
                    return {'success': False, 'error': 'No expirations available'}
                expiration = exp_response.expirations[0]
            
            # Get chain
            chain_request = OptionChainRequest(
                instrument=instrument,
                expiration_date=expiration
            )
            chain = self.client.get_option_chain(chain_request)
            
            calls = []
            for opt in (chain.calls or []):
                calls.append({
                    'symbol': opt.instrument.symbol,
                    'strike': self._parse_strike(opt.instrument.symbol),
                    'bid': float(opt.bid) if opt.bid else None,
                    'ask': float(opt.ask) if opt.ask else None,
                    'last': float(opt.last) if opt.last else None,
                    'volume': int(opt.volume) if opt.volume else 0,
                    'open_interest': int(opt.open_interest) if opt.open_interest else 0
                })
            
            puts = []
            for opt in (chain.puts or []):
                puts.append({
                    'symbol': opt.instrument.symbol,
                    'strike': self._parse_strike(opt.instrument.symbol),
                    'bid': float(opt.bid) if opt.bid else None,
                    'ask': float(opt.ask) if opt.ask else None,
                    'last': float(opt.last) if opt.last else None,
                    'volume': int(opt.volume) if opt.volume else 0,
                    'open_interest': int(opt.open_interest) if opt.open_interest else 0
                })
            
            return {
                'success': True,
                'symbol': symbol,
                'expiration': expiration,
                'calls': calls,
                'puts': puts
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_option_expirations(self, symbol: str) -> Dict[str, Any]:
        """Get option expiration dates."""
        if not self.is_available():
            return {'success': False, 'error': 'API not available'}
        
        try:
            from public_api_sdk import OptionExpirationsRequest
            
            instrument = OrderInstrument(symbol=symbol, type=InstrumentType.EQUITY)
            request = OptionExpirationsRequest(instrument=instrument)
            response = self.client.get_option_expirations(request)
            
            return {
                'success': True,
                'symbol': symbol,
                'expirations': response.expirations or []
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _parse_strike(self, osi_symbol: str) -> float:
        """Parse strike price from OSI symbol."""
        try:
            clean = osi_symbol.replace('-OPTION', '')
            strike_str = clean[-8:]
            return int(strike_str) / 1000
        except:
            return 0.0


# Singleton instance
_portfolio_service = None

def get_portfolio_service() -> PortfolioService:
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = PortfolioService()
    return _portfolio_service
