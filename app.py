"""
Options Copilot - Competition Entry for Public.com
A comprehensive options trading assistant with paper trading, analysis, and real trading.
"""

import argparse
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

from config import Config, has_api_credentials
from services.market_data import get_market_data_service
from services.analysis import get_analyzer
from services.sentiment import get_sentiment_service
from services.paper_trading import get_paper_trading_service
from services.portfolio import get_portfolio_service
from services.trading import get_trading_service
from services.scanner import get_scanner
from services.indicators import get_indicator_service
from services.algo_trading import get_algo_trading_service


# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
CORS(app)

# Initialize services
market_data = get_market_data_service()
analyzer = get_analyzer()
sentiment_service = get_sentiment_service()
paper_service = get_paper_trading_service()
portfolio_service = get_portfolio_service()
trading_service = get_trading_service()
scanner = get_scanner()
indicator_service = get_indicator_service()
algo_service = get_algo_trading_service()

# SPY Scalper game state (persistent)
spy_game = {
    'position': None,  # {'side': 'long'/'short', 'entry': price, 'quantity': 100}
    'pnl': 0.0,
    'trades': 0,
    'high_score': 0.0,
    'price_history': []  # Last 50 prices for mini chart
}


# ================== Page Routes ==================

@app.route('/')
def index():
    """Serve the main SPA."""
    return render_template('index.html')


# ================== Status Routes ==================

@app.route('/api/status')
def get_status():
    """Get application status."""
    return jsonify({
        'success': True,
        'api_available': has_api_credentials(),
        'paper_trading': True,
        'market_data': True,
        'timestamp': datetime.now().isoformat()
    })


# ================== Market Data Routes ==================

@app.route('/api/quote/<symbol>')
def get_quote(symbol: str):
    """Get quote for a symbol."""
    quote = market_data.get_quote(symbol.upper())
    if quote:
        return jsonify({'success': True, 'quote': quote})
    return jsonify({'success': False, 'error': f'Could not get quote for {symbol}'}), 404


@app.route('/api/chart/<symbol>')
def get_chart_data(symbol: str):
    """Get chart data for a symbol."""
    period = request.args.get('period', '60d')
    interval = request.args.get('interval', '1d')
    
    hist = market_data.get_history(symbol.upper(), period, interval)
    if hist is None or hist.empty:
        return jsonify({'success': False, 'error': 'No data available'}), 404
    
    # Convert to JSON-serializable format
    data = {
        'dates': hist.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
        'open': hist['Open'].tolist(),
        'high': hist['High'].tolist(),
        'low': hist['Low'].tolist(),
        'close': hist['Close'].tolist(),
        'volume': hist['Volume'].tolist()
    }
    
    # Compute indicators
    prices = data['close']
    indicators = indicator_service.compute_all(
        prices, 
        volumes=data['volume'],
        highs=data['high'],
        lows=data['low']
    )
    
    return jsonify({
        'success': True,
        'symbol': symbol.upper(),
        'data': data,
        'indicators': indicators
    })


@app.route('/api/options/<symbol>/expirations')
def get_option_expirations(symbol: str):
    """Get option expiration dates with days to expiry."""
    expirations = market_data.get_option_expirations(symbol.upper(), include_dte=True)
    return jsonify({
        'success': True,
        'symbol': symbol.upper(),
        'expirations': expirations
    })


@app.route('/api/options/<symbol>/chain-near')
def get_option_chain_near(symbol: str):
    """Get option chain for the expiration nearest to requested DTE."""
    target_dte = request.args.get('dte', 30, type=int)
    
    nearest = market_data.get_nearest_expiration(symbol.upper(), target_dte)
    if not nearest:
        return jsonify({'success': False, 'error': 'No expirations available'}), 404
    
    # Get the chain for that expiration
    chain = market_data.get_option_chain(symbol.upper(), nearest['date'])
    if chain:
        chain['requested_dte'] = target_dte
        chain['actual_dte'] = nearest['days_to_expiry']
        return jsonify({'success': True, **chain})
    
    return jsonify({'success': False, 'error': 'Could not get option chain'}), 404


@app.route('/api/options/<symbol>/chain')
def get_option_chain(symbol: str):
    """Get option chain."""
    expiration = request.args.get('expiration')
    
    # Try Public API first if available
    if portfolio_service.is_available():
        result = portfolio_service.get_option_chain(symbol.upper(), expiration)
        if result.get('success'):
            return jsonify(result)
    
    # Fallback to yfinance
    chain = market_data.get_option_chain(symbol.upper(), expiration)
    if chain:
        # Add current price for ATM detection
        if not chain.get('underlying_price'):
            quote = market_data.get_quote(symbol.upper())
            if quote:
                chain['underlying_price'] = quote.get('price')
        return jsonify({'success': True, **chain})
    
    return jsonify({'success': False, 'error': 'Could not get option chain'}), 404


# ================== Analysis Routes ==================

@app.route('/api/analysis/<symbol>')
def get_analysis(symbol: str):
    """Get technical analysis for a symbol."""
    analysis = analyzer.analyze(symbol.upper())
    if analysis:
        return jsonify({
            'success': True,
            'analysis': analysis.to_dict()
        })
    return jsonify({'success': False, 'error': f'Could not analyze {symbol}'}), 404


@app.route('/api/sentiment')
def get_sentiment():
    """Get market sentiment data."""
    sentiment = sentiment_service.get_sentiment()
    if sentiment:
        return jsonify({
            'success': True,
            'sentiment': sentiment.to_dict()
        })
    return jsonify({'success': False, 'error': 'Could not get sentiment data'}), 500


# ================== Scanner Routes ==================

@app.route('/api/scanner/scan', methods=['POST'])
def scan_options():
    """Scan for option opportunities."""
    data = request.json or {}
    
    symbols = data.get('symbols')
    min_volume = data.get('min_volume')
    min_oi = data.get('min_oi')
    max_dte = data.get('max_dte')
    limit = data.get('limit')
    
    results = scanner.scan(
        symbols=symbols,
        min_volume=min_volume,
        min_oi=min_oi,
        max_dte=max_dte,
        limit=limit
    )
    
    return jsonify({
        'success': True,
        'results': [r.to_dict() for r in results],
        'count': len(results)
    })


@app.route('/api/scanner/watchlist', methods=['GET'])
def get_watchlist():
    """Get scanner watchlist."""
    return jsonify({
        'success': True,
        'watchlist': scanner.get_watchlist()
    })


@app.route('/api/scanner/watchlist', methods=['POST'])
def set_watchlist():
    """Set scanner watchlist."""
    data = request.json
    if not data or 'symbols' not in data:
        return jsonify({'success': False, 'error': 'symbols required'}), 400
    
    scanner.set_watchlist(data['symbols'])
    return jsonify({
        'success': True,
        'watchlist': scanner.get_watchlist()
    })


@app.route('/api/scanner/presets')
def get_presets():
    """Get available watchlist presets."""
    return jsonify({
        'success': True,
        'presets': Config.WATCHLIST_PRESETS
    })


@app.route('/api/scanner/preset/<name>', methods=['POST'])
def use_preset(name: str):
    """Use a watchlist preset."""
    if name not in Config.WATCHLIST_PRESETS:
        return jsonify({'success': False, 'error': f'Unknown preset: {name}'}), 400
    
    scanner.set_watchlist(Config.WATCHLIST_PRESETS[name])
    return jsonify({
        'success': True,
        'preset': name,
        'watchlist': scanner.get_watchlist()
    })


# ================== Paper Trading Routes ==================

@app.route('/api/paper/portfolio')
def get_paper_portfolio():
    """Get paper trading portfolio."""
    portfolio = paper_service.get_portfolio()
    return jsonify({'success': True, **portfolio})


@app.route('/api/paper/buy', methods=['POST'])
def paper_buy():
    """Execute paper buy order."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required = ['symbol', 'quantity']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'error': f'{field} required'}), 400
    
    result = paper_service.buy(
        symbol=data['symbol'].upper(),
        quantity=int(data['quantity']),
        price=float(data['price']) if data.get('price') else None,
        asset_type=data.get('asset_type', 'STOCK'),
        notes=data.get('notes', '')
    )
    
    return jsonify(result)


@app.route('/api/paper/sell', methods=['POST'])
def paper_sell():
    """Execute paper sell order."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required = ['symbol', 'quantity']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'error': f'{field} required'}), 400
    
    result = paper_service.sell(
        symbol=data['symbol'].upper(),
        quantity=int(data['quantity']),
        price=float(data['price']) if data.get('price') else None,
        notes=data.get('notes', '')
    )
    
    return jsonify(result)


@app.route('/api/paper/history')
def get_paper_history():
    """Get paper trade history."""
    limit = request.args.get('limit', 50, type=int)
    history = paper_service.get_trade_history(limit)
    return jsonify({'success': True, 'trades': history})


@app.route('/api/paper/equity')
def get_paper_equity():
    """Get paper equity history for charting."""
    history = paper_service.get_equity_history()
    return jsonify({'success': True, 'history': history})


@app.route('/api/paper/reset', methods=['POST'])
def reset_paper():
    """Reset paper trading account."""
    result = paper_service.reset()
    return jsonify(result)


# ================== Real Portfolio Routes ==================

@app.route('/api/portfolio')
def get_portfolio():
    """Get real portfolio (requires API credentials)."""
    result = portfolio_service.get_portfolio()
    return jsonify(result)


# ================== Real Trading Routes ==================

@app.route('/api/order/preflight', methods=['POST'])
def order_preflight():
    """Calculate order preflight."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required = ['symbol', 'side', 'quantity']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'error': f'{field} required'}), 400
    
    result = trading_service.preflight(
        symbol=data['symbol'],
        side=data['side'],
        quantity=int(data['quantity']),
        limit_price=float(data['limit_price']) if data.get('limit_price') else None
    )
    
    return jsonify(result)


@app.route('/api/order/place', methods=['POST'])
def place_order():
    """Place a real order."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required = ['symbol', 'side', 'quantity']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'error': f'{field} required'}), 400
    
    result = trading_service.place_order(
        symbol=data['symbol'],
        side=data['side'],
        quantity=int(data['quantity']),
        limit_price=float(data['limit_price']) if data.get('limit_price') else None,
        order_type=data.get('order_type', 'LIMIT')
    )
    
    return jsonify(result)


@app.route('/api/order/<order_id>')
def get_order(order_id: str):
    """Get order status."""
    result = trading_service.get_order(order_id)
    return jsonify(result)


@app.route('/api/order/<order_id>/cancel', methods=['POST'])
def cancel_order(order_id: str):
    """Cancel an order."""
    result = trading_service.cancel_order(order_id)
    return jsonify(result)


@app.route('/api/orders/open')
def get_open_orders():
    """Get open orders."""
    result = trading_service.get_open_orders()
    return jsonify(result)


# ================== SPY Scalper Game Routes ==================

@app.route('/api/game/spy')
def get_spy_game():
    """Get SPY scalper game state — options style."""
    spy_price = market_data.get_spy_price()
    
    # Track price history for mini chart
    if spy_price:
        spy_game['price_history'].append({
            'time': datetime.now().isoformat(),
            'price': spy_price
        })
        if len(spy_game['price_history']) > 50:
            spy_game['price_history'] = spy_game['price_history'][-50:]
    
    # Calculate nearest call/put strikes
    call_strike = None
    put_strike = None
    if spy_price:
        # Round to nearest $1
        call_strike = int(spy_price) + 1  # One strike above
        put_strike = int(spy_price)       # One strike at/below
    
    # Estimate option prices (simplified: ~$1.50 ATM, scales with delta)
    call_price = max(0.05, round(max(0, spy_price - call_strike) + 1.50, 2)) if spy_price else 0
    put_price = max(0.05, round(max(0, put_strike - spy_price) + 1.50, 2)) if spy_price else 0
    
    # Calculate current P/L if in position
    current_pnl = 0
    if spy_game['position'] and spy_price:
        pos = spy_game['position']
        if pos['type'] == 'CALL':
            current_option_price = max(0.05, round(max(0, spy_price - pos['strike']) + 1.50, 2))
        else:
            current_option_price = max(0.05, round(max(0, pos['strike'] - spy_price) + 1.50, 2))
        current_pnl = round((current_option_price - pos['entry_price']) * 100, 2)  # 1 contract = 100 shares
        spy_game['position']['current_price'] = current_option_price
        spy_game['position']['current_pnl'] = current_pnl
        spy_game['position']['pnl_pct'] = round((current_option_price / pos['entry_price'] - 1) * 100, 1) if pos['entry_price'] > 0 else 0
    
    return jsonify({
        'success': True,
        'spy_price': spy_price,
        'call_strike': call_strike,
        'put_strike': put_strike,
        'call_price': call_price,
        'put_price': put_price,
        'position': spy_game['position'],
        'current_pnl': current_pnl,
        'session_pnl': round(spy_game['pnl'], 2),
        'trades': spy_game['trades'],
        'high_score': round(spy_game['high_score'], 2),
        'price_history': spy_game['price_history']
    })


@app.route('/api/game/spy/buy', methods=['POST'])
def spy_game_buy():
    """Buy a CALL or PUT in the game."""
    data = request.json or {}
    option_type = data.get('type', 'CALL').upper()
    
    if spy_game['position']:
        return jsonify({'success': False, 'error': 'Already in a position. Close it first.'})
    
    spy_price = market_data.get_spy_price()
    if not spy_price:
        return jsonify({'success': False, 'error': 'Could not get SPY price'})
    
    if option_type == 'CALL':
        strike = int(spy_price) + 1
        entry_price = max(0.05, round(max(0, spy_price - strike) + 1.50, 2))
    else:
        strike = int(spy_price)
        entry_price = max(0.05, round(max(0, strike - spy_price) + 1.50, 2))
    
    spy_game['position'] = {
        'type': option_type,
        'strike': strike,
        'entry_price': entry_price,
        'entry_spy': spy_price,
        'current_price': entry_price,
        'current_pnl': 0,
        'pnl_pct': 0,
    }
    
    return jsonify({
        'success': True,
        'message': f'Bought SPY ${strike} {option_type} @ ${entry_price:.2f}',
        'position': spy_game['position'],
        'session_pnl': round(spy_game['pnl'], 2)
    })


@app.route('/api/game/spy/sell', methods=['POST'])
def spy_game_sell():
    """Close current option position."""
    spy_price = market_data.get_spy_price()
    if not spy_price:
        return jsonify({'success': False, 'error': 'Could not get SPY price'})
    
    if not spy_game['position']:
        return jsonify({'success': False, 'error': 'No position to close'})
    
    pos = spy_game['position']
    if pos['type'] == 'CALL':
        exit_price = max(0.01, round(max(0, spy_price - pos['strike']) + 1.50, 2))
    else:
        exit_price = max(0.01, round(max(0, pos['strike'] - spy_price) + 1.50, 2))
    
    pnl = round((exit_price - pos['entry_price']) * 100, 2)
    spy_game['pnl'] += pnl
    spy_game['trades'] += 1
    
    if spy_game['pnl'] > spy_game['high_score']:
        spy_game['high_score'] = spy_game['pnl']
    
    msg = f"Closed SPY ${pos['strike']} {pos['type']} @ ${exit_price:.2f} (Entry: ${pos['entry_price']:.2f}, P/L: ${pnl:.2f})"
    spy_game['position'] = None
    
    return jsonify({
        'success': True,
        'message': msg,
        'pnl': pnl,
        'session_pnl': round(spy_game['pnl'], 2)
    })


@app.route('/api/game/spy/reset', methods=['POST'])
def spy_game_reset():
    """Reset SPY scalper game."""
    spy_game['position'] = None
    spy_game['pnl'] = 0.0
    spy_game['trades'] = 0
    spy_game['price_history'] = []
    
    return jsonify({
        'success': True,
        'message': 'Game reset'
    })


# ================== Indicator Config Routes ==================

@app.route('/api/indicators/config')
def get_indicator_config():
    """Get indicator configuration."""
    return jsonify({
        'success': True,
        'config': indicator_service.get_config()
    })


@app.route('/api/indicators/toggle', methods=['POST'])
def toggle_indicator():
    """Toggle an indicator on/off."""
    data = request.json
    if not data or 'indicator' not in data:
        return jsonify({'success': False, 'error': 'indicator required'}), 400
    
    indicator = data['indicator']
    enabled = data.get('enabled', True)
    
    indicator_service.set_enabled(indicator, enabled)
    
    return jsonify({
        'success': True,
        'indicator': indicator,
        'enabled': enabled
    })


# ================== Position Analysis Routes ==================

@app.route('/api/analysis/full/<symbol>')
def get_full_analysis(symbol: str):
    """Get full technical analysis with chart data for modal."""
    symbol = symbol.upper()
    
    # Get analysis
    analysis_result = analyzer.analyze(symbol)
    if not analysis_result:
        return jsonify({'success': False, 'error': f'Could not analyze {symbol}'}), 404
    
    analysis = analysis_result.to_dict()
    
    # Get chart data (30 days)
    hist = market_data.get_history(symbol, "30d", "1d")
    chart_data = None
    if hist is not None and not hist.empty:
        chart_data = {
            'dates': hist.index.strftime('%Y-%m-%d').tolist(),
            'close': hist['Close'].tolist(),
            'high': hist['High'].tolist(),
            'low': hist['Low'].tolist()
        }
    
    # Generate recommendation
    trend = analysis.get('trend', 'NEUTRAL')
    rsi = analysis.get('rsi', 50)
    regime = analysis.get('regime', 'UNKNOWN')
    momentum_score = analysis.get('evidence', {}).get('momentum_score', 0)
    structure_score = analysis.get('evidence', {}).get('structure_score', 0)
    
    combined_score = (momentum_score + structure_score) / 2
    
    if combined_score > 0.5 and trend == 'BULLISH':
        recommendation = 'STRONG BUY'
        rec_class = 'strong-buy'
    elif combined_score > 0.2 and trend in ['BULLISH', 'NEUTRAL']:
        recommendation = 'BUY'
        rec_class = 'buy'
    elif combined_score < -0.5 and trend == 'BEARISH':
        recommendation = 'STRONG SELL'
        rec_class = 'strong-sell'
    elif combined_score < -0.2 and trend in ['BEARISH', 'NEUTRAL']:
        recommendation = 'SELL'
        rec_class = 'sell'
    else:
        recommendation = 'HOLD'
        rec_class = 'hold'
    
    return jsonify({
        'success': True,
        'symbol': symbol,
        'analysis': analysis,
        'chart_data': chart_data,
        'recommendation': recommendation,
        'recommendation_class': rec_class
    })


# ================== Algo Trading Routes ==================

@app.route('/api/algo/conditions')
def get_algo_conditions():
    """Get available condition types for strategy builder."""
    conditions = algo_service.get_condition_types()
    return jsonify({'success': True, 'conditions': conditions})


@app.route('/api/algo/strategies')
def get_algo_strategies():
    """Get all saved strategies."""
    strategies = algo_service.get_strategies()
    return jsonify({'success': True, 'strategies': strategies})


@app.route('/api/algo/strategy', methods=['POST'])
def create_algo_strategy():
    """Create a new algo trading strategy."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required = ['name', 'symbols', 'entry_conditions', 'exit_conditions']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'error': f'{field} required'}), 400
    
    result = algo_service.create_strategy(
        name=data['name'],
        symbols=data['symbols'],
        entry_conditions=data['entry_conditions'],
        exit_conditions=data['exit_conditions'],
        position_size_pct=data.get('position_size_pct', 10.0),
        max_positions=data.get('max_positions', 5),
        stop_loss_pct=data.get('stop_loss_pct'),
        take_profit_pct=data.get('take_profit_pct')
    )
    
    return jsonify(result)


@app.route('/api/algo/strategy/<strategy_id>', methods=['GET'])
def get_algo_strategy(strategy_id: str):
    """Get a specific strategy."""
    strategy = algo_service.get_strategy(strategy_id)
    if strategy:
        return jsonify({'success': True, 'strategy': strategy})
    return jsonify({'success': False, 'error': 'Strategy not found'}), 404


@app.route('/api/algo/strategy/<strategy_id>', methods=['DELETE'])
def delete_algo_strategy(strategy_id: str):
    """Delete a strategy."""
    result = algo_service.delete_strategy(strategy_id)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 404


@app.route('/api/algo/toggle/<strategy_id>', methods=['POST'])
def toggle_algo_strategy(strategy_id: str):
    """Toggle strategy enabled/live status."""
    data = request.json or {}
    
    result = algo_service.toggle_strategy(
        strategy_id=strategy_id,
        enabled=data.get('enabled'),
        is_live=data.get('is_live')
    )
    
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 404


@app.route('/api/algo/backtest', methods=['POST'])
def run_algo_backtest():
    """Run backtest with strategy config."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Support both saved strategy (by ID) and inline strategy config
    strategy_config = data.get('strategy_config')
    if not strategy_config and not data.get('strategy_id'):
        # Try to build config from inline fields
        if data.get('entry_conditions') or data.get('symbol'):
            strategy_config = {
                'name': data.get('name', 'Quick Backtest'),
                'symbols': data.get('symbols', [data.get('symbol', 'SPY')]),
                'entry_conditions': data.get('entry_conditions', []),
                'exit_conditions': data.get('exit_conditions', []),
                'position_size_pct': data.get('position_size', 10),
                'max_positions': data.get('max_positions', 5),
                'stop_loss_pct': data.get('stop_loss'),
                'take_profit_pct': data.get('take_profit'),
            }
    
    result = algo_service.backtest(
        strategy_id=data.get('strategy_id'),
        strategy_config=strategy_config,
        symbols=data.get('symbols'),
        period=data.get('period', '1y'),
        initial_capital=data.get('initial_capital', 10000.0)
    )
    
    return jsonify(result)


@app.route('/api/algo/compare', methods=['POST'])
def compare_algo_strategies():
    """Compare multiple strategies via backtest."""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    strategy_ids = data.get('strategy_ids', [])
    if not strategy_ids or len(strategy_ids) < 2:
        return jsonify({'success': False, 'error': 'At least 2 strategy IDs required'}), 400
    
    if len(strategy_ids) > 5:
        return jsonify({'success': False, 'error': 'Maximum 5 strategies for comparison'}), 400
    
    result = algo_service.compare_strategies(
        strategy_ids=strategy_ids,
        period=data.get('period', '1y'),
        initial_capital=data.get('initial_capital', 10000.0),
        symbols=data.get('symbols')
    )
    
    return jsonify(result)


# ================== Run ==================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Options Copilot')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5006, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                     OPTIONS COPILOT                          ║
║                  Public.com Competition Entry                ║
╠══════════════════════════════════════════════════════════════╣
║  API Status: {'✓ Connected' if has_api_credentials() else '✗ Not configured (paper trading only)':45}║
║  Paper Trading: ✓ Available                                  ║
║  URL: http://{args.host}:{args.port}                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=args.host, port=args.port, debug=args.debug)
