#!/usr/bin/env python3
"""
app.py — Options Copilot Web UI (Flask)

Serves a browser-based command center for all copilot features.
Run locally: python3 app.py → open http://localhost:8080

Environment variables:
    PUBLIC_COM_SECRET      API secret key from Public.com
    PUBLIC_COM_ACCOUNT_ID  Your brokerage account ID
    COPILOT_READ_ONLY      Set to 'true' to disable order execution
"""

import os
import sys
import json
import time
import threading
import math
from datetime import datetime, timedelta, time as dtime
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# ── App setup ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

API_SECRET   = os.environ.get('PUBLIC_COM_SECRET', '')
ACCOUNT_ID   = os.environ.get('PUBLIC_COM_ACCOUNT_ID', '')
READ_ONLY    = os.environ.get('COPILOT_READ_ONLY', '').lower() in ('true', '1', 'yes')

# ── SDK & optional deps ────────────────────────────────────────────────────────
SDK_AVAILABLE = False
YFINANCE_AVAILABLE = False

try:
    from public_api_sdk import (
        PublicApiClient,
        PublicApiClientConfiguration,
        ApiKeyAuthConfig,
    )
    SDK_AVAILABLE = True
except ImportError:
    pass

try:
    import yfinance as yf
    import numpy as np
    YFINANCE_AVAILABLE = True
except ImportError:
    pass

# ── SDK client (lazy — created per-request so env can be set after import) ─────
_client_cache = {}
_client_lock = threading.Lock()


def get_client():
    """Return a cached SDK client; raises RuntimeError if not configured."""
    secret = os.environ.get('PUBLIC_COM_SECRET', API_SECRET)
    acct   = os.environ.get('PUBLIC_COM_ACCOUNT_ID', ACCOUNT_ID)
    if not SDK_AVAILABLE:
        raise RuntimeError("publicdotcom-py SDK not installed")
    if not secret:
        raise RuntimeError("PUBLIC_COM_SECRET not set")
    key = (secret, acct)
    with _client_lock:
        if key not in _client_cache:
            auth   = ApiKeyAuthConfig(api_secret_key=secret)
            config = PublicApiClientConfiguration(default_account_number=acct)
            _client_cache[key] = PublicApiClient(auth_config=auth, config=config)
        return _client_cache[key]


# ── Monitor state (in-memory) ──────────────────────────────────────────────────
monitor_state = {
    'running': False,
    'thread': None,
    'last_check': None,
    'positions': [],
    'log': [],
}
monitor_lock = threading.Lock()

PROFIT_TARGET_PCT  = 0.20
STOP_LOSS_PCT      = 0.15
CHECK_INTERVAL_SEC = 10
EOD_EXIT_TIME      = dtime(15, 45)


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def get_attr(obj, *keys, default=None):
    for key in keys:
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
        else:
            v = getattr(obj, key, None)
            if v is not None:
                return v
    return default


def is_option(symbol):
    return len(symbol) > 10 and any(c.isdigit() for c in symbol[6:])


def parse_osi(osi):
    try:
        underlying = osi[:6].strip()
        date_str   = osi[6:12]
        call_put   = osi[12]
        strike     = int(osi[13:]) / 1000
        exp_date   = datetime.strptime(date_str, "%y%m%d").strftime("%Y-%m-%d")
        dte        = (datetime.strptime(exp_date, "%Y-%m-%d") - datetime.today()).days
        return {
            'underlying':  underlying,
            'expiration':  exp_date,
            'dte':         dte,
            'option_type': 'call' if call_put == 'C' else 'put',
            'strike':      strike,
        }
    except Exception:
        return {}


def api_error(msg, status=500):
    return jsonify({'error': msg, 'ok': False}), status


def ok(data):
    data['ok'] = True
    return jsonify(data)


# ══════════════════════════════════════════════════════════════════════════════
#  Routes
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    return render_template('dashboard.html')


# ── /api/status ────────────────────────────────────────────────────────────────
@app.route('/api/status')
def api_status():
    """Check API connection and return account info."""
    if not SDK_AVAILABLE:
        return ok({
            'connected':  False,
            'sdk':        False,
            'message':    'publicdotcom-py SDK not installed. Run: pip install publicdotcom-py',
            'read_only':  READ_ONLY,
            'account_id': ACCOUNT_ID or '—',
        })
    if not os.environ.get('PUBLIC_COM_SECRET', API_SECRET):
        return ok({
            'connected':  False,
            'sdk':        True,
            'message':    'PUBLIC_COM_SECRET not set',
            'read_only':  READ_ONLY,
            'account_id': ACCOUNT_ID or '—',
        })
    try:
        client    = get_client()
        portfolio = client.get_portfolio()
        if isinstance(portfolio, dict):
            bp = safe_float(portfolio.get('buyingPower', portfolio.get('buying_power', 0)))
        else:
            bp = safe_float(get_attr(portfolio, 'buyingPower', 'buying_power', default=0))
        return ok({
            'connected':     True,
            'sdk':           True,
            'message':       'Connected',
            'read_only':     READ_ONLY,
            'account_id':    os.environ.get('PUBLIC_COM_ACCOUNT_ID', ACCOUNT_ID) or '—',
            'buying_power':  bp,
        })
    except Exception as e:
        return ok({
            'connected':  False,
            'sdk':        True,
            'message':    str(e),
            'read_only':  READ_ONLY,
            'account_id': os.environ.get('PUBLIC_COM_ACCOUNT_ID', ACCOUNT_ID) or '—',
        })


# ── /api/portfolio ─────────────────────────────────────────────────────────────
@app.route('/api/portfolio')
def api_portfolio():
    try:
        client    = get_client()
        portfolio = client.get_portfolio()

        if isinstance(portfolio, dict):
            positions      = portfolio.get('positions', portfolio.get('holdings', []))
            buying_power   = safe_float(portfolio.get('buyingPower', portfolio.get('buying_power', 0)))
            portfolio_val  = safe_float(portfolio.get('portfolioValue', portfolio.get('totalValue', 0)))
            cash           = safe_float(portfolio.get('cashBalance', portfolio.get('cash', 0)))
        else:
            positions      = getattr(portfolio, 'positions', None) or []
            # buying_power is an object with .buying_power inside
            bp_obj = getattr(portfolio, 'buying_power', None)
            if bp_obj and hasattr(bp_obj, 'buying_power'):
                buying_power = safe_float(bp_obj.buying_power)
                cash = safe_float(getattr(bp_obj, 'cash_only_buying_power', bp_obj.buying_power))
            else:
                buying_power = safe_float(bp_obj)
                cash = buying_power
            # equity is a list of asset types — sum all values
            equity_list = getattr(portfolio, 'equity', []) or []
            if isinstance(equity_list, list):
                portfolio_val = sum(safe_float(getattr(e, 'value', 0)) for e in equity_list)
            else:
                portfolio_val = safe_float(equity_list)

        # Build position list with live quotes
        all_symbols = []
        parsed = []
        for pos in positions:
            # Public.com SDK: pos.instrument.symbol, pos.quantity, pos.cost_basis, etc.
            if hasattr(pos, 'instrument') and hasattr(pos.instrument, 'symbol'):
                sym = str(pos.instrument.symbol)
                inst_type = str(getattr(pos.instrument, 'type', '')).upper()
            else:
                sym = get_attr(pos, 'symbol', 'ticker', default='')
                inst_type = ''
            qty       = safe_float(get_attr(pos, 'quantity', 'qty', 'shares', default=0))
            if hasattr(pos, 'cost_basis') and pos.cost_basis:
                avg_cost = safe_float(getattr(pos.cost_basis, 'unit_cost', 0))
            else:
                avg_cost  = safe_float(get_attr(pos, 'averageCost', 'average_cost', 'costBasis', default=0))
            mkt_val   = safe_float(get_attr(pos, 'current_value', 'marketValue', 'market_value', default=0))
            if hasattr(pos, 'cost_basis') and pos.cost_basis:
                unrealised = safe_float(getattr(pos.cost_basis, 'gain_value', 0))
            else:
                unrealised = safe_float(get_attr(pos, 'unrealizedPnl', 'unrealizedGainLoss', default=0))
            parsed.append({'symbol': sym, 'qty': qty, 'avg_cost': avg_cost,
                           'market_val': mkt_val, 'unrealized': unrealised})
            if sym:
                all_symbols.append(sym)

        # Live quotes
        live_prices = {}
        if all_symbols:
            try:
                from public_api_sdk.models.order import OrderInstrument
                from public_api_sdk import InstrumentType
                quote_instruments = [OrderInstrument(symbol=s, type=InstrumentType.OPTION if len(s) > 10 else InstrumentType.EQUITY) for s in all_symbols]
                quotes_resp = client.get_quotes(quote_instruments)
                quotes = []
                if isinstance(quotes_resp, dict):
                    quotes = quotes_resp.get('quotes', list(quotes_resp.values()))
                elif isinstance(quotes_resp, list):
                    quotes = quotes_resp
                for q in quotes:
                    qsym = get_attr(q, 'symbol', 'ticker', default='')
                    last = safe_float(get_attr(q, 'lastTradePrice', 'last', 'price', default=0))
                    bid  = safe_float(get_attr(q, 'bid', default=0))
                    ask  = safe_float(get_attr(q, 'ask', default=0))
                    if qsym:
                        live_prices[qsym] = {'last': last, 'bid': bid, 'ask': ask}
            except Exception:
                pass

        result_positions = []
        total_unrealised = 0.0
        for pos in parsed:
            sym   = pos['symbol']
            live  = live_prices.get(sym, {})
            mult  = 100 if is_option(sym) else 1
            last  = live.get('last', 0) or pos['avg_cost']
            unreal = (last - pos['avg_cost']) * pos['qty'] * mult
            pnl_pct = ((last / pos['avg_cost']) - 1) * 100 if pos['avg_cost'] else 0
            total_unrealised += unreal

            # Greeks for options
            delta = gamma = theta = iv = 0.0
            if is_option(sym):
                try:
                    gr = client.get_option_greeks(sym)
                    if isinstance(gr, dict):
                        delta = safe_float(gr.get('delta', 0))
                        gamma = safe_float(gr.get('gamma', 0))
                        theta = safe_float(gr.get('theta', 0))
                        iv    = safe_float(gr.get('impliedVolatility', gr.get('iv', 0))) * 100
                    else:
                        delta = safe_float(get_attr(gr, 'delta', default=0))
                        gamma = safe_float(get_attr(gr, 'gamma', default=0))
                        theta = safe_float(get_attr(gr, 'theta', default=0))
                        iv    = safe_float(get_attr(gr, 'impliedVolatility', 'iv', default=0)) * 100
                except Exception:
                    pass

            osi_info = parse_osi(sym) if is_option(sym) else {}
            result_positions.append({
                'symbol':       sym,
                'type':         osi_info.get('option_type', 'equity') if osi_info else 'equity',
                'qty':          pos['qty'],
                'entry':        round(pos['avg_cost'], 2),
                'current':      round(last, 2),
                'pnl_pct':      round(pnl_pct, 2),
                'pnl_dollars':  round(unreal, 2),
                'market_val':   round(last * pos['qty'] * mult, 2),
                'delta':        round(delta, 3),
                'gamma':        round(gamma, 4),
                'theta':        round(theta, 3),
                'iv':           round(iv, 1),
                'strike':       osi_info.get('strike'),
                'expiry':       osi_info.get('expiration'),
                'dte':          osi_info.get('dte'),
                'underlying':   osi_info.get('underlying', sym),
            })

        return ok({
            'positions':       result_positions,
            'portfolio_value': round(portfolio_val, 2),
            'buying_power':    round(buying_power, 2),
            'cash':            round(cash, 2),
            'total_unrealized':round(total_unrealised, 2),
            'count':           len(result_positions),
        })

    except Exception as e:
        return api_error(str(e))


# ── /api/scan ──────────────────────────────────────────────────────────────────
@app.route('/api/scan')
def api_scan():
    symbols_raw  = request.args.get('symbols', 'AAPL,NVDA,TSLA,META,SPY,QQQ')
    min_score    = float(request.args.get('min_score', 72))
    limit        = int(request.args.get('limit', 20))

    symbols = [s.strip().upper() for s in symbols_raw.split(',') if s.strip()]
    if not symbols:
        return api_error('No symbols provided', 400)

    try:
        client = get_client()
    except Exception as e:
        return api_error(str(e))

    if not YFINANCE_AVAILABLE:
        return api_error('yfinance not installed. Run: pip install yfinance numpy')

    # Import scoring helpers from scan.py
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
    try:
        # Temporarily swap sys.exit so the module-level check doesn't crash us
        import builtins
        real_exit = sys.exit

        def _no_exit(code=0):
            raise RuntimeError(f"script tried to exit({code})")

        sys.exit = _no_exit
        # Patch env before import
        os.environ.setdefault('PUBLIC_COM_SECRET', 'placeholder_for_import')
        import importlib
        import scan as scan_mod
        importlib.reload(scan_mod)
        sys.exit = real_exit

        get_tech   = scan_mod.get_technicals
        pick_exp   = scan_mod.pick_expiration
        score_opt  = scan_mod.score_option
    except Exception as e:
        sys.exit = real_exit
        import traceback
        return api_error(f'Could not load scanner: {e}\n{traceback.format_exc()}')

    all_signals = []
    errors = []

    for sym in symbols[:15]:  # cap at 15 symbols per request
        try:
            tech = get_tech(sym)
            if not tech:
                continue

            # Get expirations
            try:
                from public_api_sdk import OptionExpirationsRequest, InstrumentType
                from public_api_sdk.models.order import OrderInstrument
                exp_req = OptionExpirationsRequest(instrument=OrderInstrument(symbol=sym, type=InstrumentType.EQUITY))
                exp_resp = client.get_option_expirations(exp_req)
                expirations  = []
                if isinstance(exp_resp, dict):
                    expirations = exp_resp.get('expirations', [])
                elif isinstance(exp_resp, list):
                    expirations = exp_resp
                else:
                    expirations = getattr(exp_resp, 'expirations', []) or []
            except Exception:
                continue

            exp = pick_exp(expirations, target_dte=21)
            if not exp:
                continue

            today = datetime.today().date()
            dte   = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days

            # Get option chain
            try:
                from public_api_sdk import OptionChainRequest
                chain_resp = client.get_option_chain(OptionChainRequest(
                    instrument=OrderInstrument(symbol=sym, type=InstrumentType.EQUITY),
                    expiration_date=exp
                ))
                chain = []
                if hasattr(chain_resp, 'calls') and hasattr(chain_resp, 'puts'):
                    chain = list(chain_resp.calls or []) + list(chain_resp.puts or [])
                elif isinstance(chain_resp, list):
                    chain = chain_resp
                elif isinstance(chain_resp, dict):
                    chain = chain_resp.get('calls', []) + chain_resp.get('puts', [])
            except Exception:
                continue

            for opt in chain:
                try:
                    if isinstance(opt, dict):
                        osi   = opt.get('symbol', '')
                        otype = opt.get('optionType', opt.get('type', '')).lower()
                        bid   = float(opt.get('bid', 0) or 0)
                        ask   = float(opt.get('ask', 0) or 0)
                        last  = float(opt.get('lastTradePrice', opt.get('last', 0)) or 0)
                    else:
                        osi   = getattr(opt, 'symbol', '')
                        otype = (getattr(opt, 'optionType', '') or '').lower()
                        bid   = float(getattr(opt, 'bid', 0) or 0)
                        ask   = float(getattr(opt, 'ask', 0) or 0)
                        last  = float(getattr(opt, 'lastTradePrice', None) or 0)

                    if not osi or otype not in ('call', 'put'):
                        continue
                    entry = (bid + ask) / 2 if bid and ask else last
                    if entry <= 0:
                        continue

                    # Greeks
                    try:
                        gr = client.get_option_greeks(osi)
                        greeks = gr if isinstance(gr, dict) else (vars(gr) if hasattr(gr, '__dict__') else {})
                    except Exception:
                        greeks = {}

                    score, breakdown = score_opt(otype, greeks, tech, entry, bid, ask, dte)
                    if score >= min_score:
                        osi_info = parse_osi(osi)
                        all_signals.append({
                            'symbol':    sym,
                            'osi':       osi,
                            'direction': otype,
                            'strike':    osi_info.get('strike', 0),
                            'expiry':    exp,
                            'dte':       dte,
                            'score':     round(score, 1),
                            'delta':     round(safe_float(breakdown.get('delta', 0)), 3),
                            'iv':        round(safe_float(breakdown.get('iv', 0)), 1),
                            'entry':     round(entry, 2),
                            'bid':       round(bid, 2),
                            'ask':       round(ask, 2),
                            'trend':     tech.get('trend', 'neutral'),
                            'rsi':       round(tech.get('rsi', 50), 1),
                            'breakdown': {k: v for k, v in breakdown.items()
                                          if k not in ('reject',)},
                        })
                except Exception:
                    continue

        except Exception as ex:
            errors.append(f'{sym}: {ex}')

    all_signals.sort(key=lambda x: x['score'], reverse=True)
    return ok({
        'signals':    all_signals[:limit],
        'count':      len(all_signals),
        'symbols':    symbols,
        'min_score':  min_score,
        'errors':     errors,
        'scanned_at': datetime.now().isoformat(),
    })


# ── /api/trade ─────────────────────────────────────────────────────────────────
@app.route('/api/trade', methods=['POST'])
def api_trade():
    body     = request.get_json(force=True) or {}
    symbol   = body.get('symbol', '').upper()
    side     = body.get('side', 'buy').lower()
    quantity = body.get('quantity')  # None = auto-size

    if not symbol:
        return api_error('symbol required', 400)
    if side not in ('buy', 'sell'):
        return api_error('side must be buy or sell', 400)

    try:
        client = get_client()
    except Exception as e:
        return api_error(str(e))

    # Get live quote
    try:
        quotes_resp = client.get_quotes([symbol])
        quotes = []
        if isinstance(quotes_resp, dict):
            quotes = quotes_resp.get('quotes', list(quotes_resp.values()))
        elif isinstance(quotes_resp, list):
            quotes = quotes_resp
        bid = ask = last = 0.0
        for q in quotes:
            bid  = safe_float(get_attr(q, 'bid', default=0))
            ask  = safe_float(get_attr(q, 'ask', default=0))
            last = safe_float(get_attr(q, 'lastTradePrice', 'last', 'price', default=0))
            break
    except Exception as e:
        return api_error(f'Quote fetch failed: {e}')

    if bid <= 0 and ask <= 0 and last <= 0:
        return api_error('No valid market data for this symbol')

    mid = (bid + ask) / 2 if bid and ask else (ask or last)
    spread_pct = (ask - bid) / mid if mid and bid and ask else 0
    if spread_pct > 0.10:
        return api_error(f'Bid/ask spread too wide ({spread_pct:.1%}). Use a more liquid contract.')

    limit_price = round(mid, 2)

    # Auto-size
    if quantity is None:
        cost_per = limit_price * 100
        qty = 1
        for q in range(1, 20):
            total = cost_per * q
            if 300 <= total <= 500:
                qty = q
                break
            if total > 500:
                prev = cost_per * (q - 1)
                qty = q - 1 if prev >= 300 else 1
                break
    else:
        qty = int(quantity)

    qty = max(1, qty)
    total_cost = round(limit_price * 100 * qty, 2)
    max_risk   = round(total_cost * STOP_LOSS_PCT, 2)

    # Preflight
    preflight_result = {}
    try:
        pf = client.perform_preflight_calculation(
            symbol=symbol,
            side=side.upper(),
            quantity=qty,
            orderType='LIMIT',
            limitPrice=limit_price,
            timeInForce='DAY',
        )
        preflight_result = pf if isinstance(pf, dict) else (vars(pf) if hasattr(pf, '__dict__') else {})
    except Exception as ex:
        preflight_result = {'warning': str(ex)}

    read_only = READ_ONLY or os.environ.get('COPILOT_READ_ONLY', '').lower() in ('true', '1', 'yes')

    if read_only:
        return ok({
            'read_only':    True,
            'message':      'READ-ONLY MODE — order not placed',
            'symbol':       symbol,
            'side':         side,
            'quantity':     qty,
            'limit_price':  limit_price,
            'total_cost':   total_cost,
            'max_risk':     max_risk,
            'preflight':    preflight_result,
        })

    # Place order
    try:
        result = client.place_order(
            symbol=symbol,
            side=side.upper(),
            quantity=qty,
            orderType='LIMIT',
            limitPrice=limit_price,
            timeInForce='DAY',
        )
        if isinstance(result, dict):
            order = result
        else:
            order = vars(result) if hasattr(result, '__dict__') else {'result': str(result)}

        order_id = order.get('orderId', order.get('id', 'unknown'))
        status   = order.get('status', order.get('orderStatus', 'submitted'))

        return ok({
            'read_only':   False,
            'message':     f'Order placed — ID: {order_id}',
            'order_id':    order_id,
            'status':      status,
            'symbol':      symbol,
            'side':        side,
            'quantity':    qty,
            'limit_price': limit_price,
            'total_cost':  total_cost,
            'max_risk':    max_risk,
            'preflight':   preflight_result,
        })
    except Exception as e:
        return api_error(f'Order failed: {e}')


# ── /api/spreads ───────────────────────────────────────────────────────────────
@app.route('/api/spreads')
def api_spreads():
    underlying   = request.args.get('underlying', '').upper()
    spread_type  = request.args.get('type', 'put_credit')   # put_credit | call_credit
    width        = float(request.args.get('width', 5))
    dte_target   = int(request.args.get('dte', 21))

    if not underlying:
        return api_error('underlying required', 400)

    try:
        client = get_client()
    except Exception as e:
        return api_error(str(e))

    option_type    = 'put' if spread_type == 'put_credit' else 'call'
    TARGET_DELTA   = 0.30
    DELTA_TOL      = 0.12
    MIN_CREDIT_PCT = 0.20

    # Expirations
    try:
        from public_api_sdk import OptionExpirationsRequest, InstrumentType
        from public_api_sdk.models.order import OrderInstrument
        exp_resp = client.get_option_expirations(OptionExpirationsRequest(
            instrument=OrderInstrument(symbol=underlying, type=InstrumentType.EQUITY)
        ))
        expirations = []
        if isinstance(exp_resp, dict):
            expirations = exp_resp.get('expirations', [])
        elif isinstance(exp_resp, list):
            expirations = exp_resp
        else:
            expirations = getattr(exp_resp, 'expirations', []) or []
    except Exception as e:
        return api_error(f'Could not fetch expirations: {e}')

    # Pick best expiry
    today = datetime.today().date()
    best_exp = best_diff = None
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            d = (exp_date - today).days
            if d < 7:
                continue
            diff = abs(d - dte_target)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_exp  = exp_str
        except Exception:
            continue

    if not best_exp:
        return api_error(f'No suitable expiration found near {dte_target}d DTE')

    actual_dte = (datetime.strptime(best_exp, "%Y-%m-%d").date() - today).days

    # Option chain
    try:
        from public_api_sdk import OptionChainRequest
        chain_resp = client.get_option_chain(OptionChainRequest(
            instrument=OrderInstrument(symbol=underlying, type=InstrumentType.EQUITY),
            expiration_date=best_exp
        ))
        chain = []
        if isinstance(chain_resp, list):
            chain = chain_resp
        elif isinstance(chain_resp, dict):
            chain = chain_resp.get('options', [])
        else:
            chain = getattr(chain_resp, 'options', []) or []
    except Exception as e:
        return api_error(f'Could not fetch chain: {e}')

    # Find candidates with Greeks
    candidates = []
    for opt in chain:
        try:
            otype = (get_attr(opt, 'optionType', 'type', default='') or '').lower()
            if otype != option_type:
                continue
            osi    = get_attr(opt, 'symbol', default='')
            bid    = safe_float(get_attr(opt, 'bid', default=0))
            ask    = safe_float(get_attr(opt, 'ask', default=0))
            strike = safe_float(get_attr(opt, 'strike', 'strikePrice', default=0))
            if not osi or not strike:
                continue

            try:
                gr     = client.get_option_greeks(osi)
                greeks = gr if isinstance(gr, dict) else (vars(gr) if hasattr(gr, '__dict__') else {})
            except Exception:
                greeks = {}

            delta = abs(safe_float(greeks.get('delta', 0)))
            iv    = safe_float(greeks.get('impliedVolatility', greeks.get('iv', 0))) * 100
            candidates.append({
                'osi': osi, 'strike': strike,
                'bid': bid, 'ask': ask,
                'mid': (bid + ask) / 2 if bid and ask else 0,
                'delta': delta, 'iv': iv,
            })
        except Exception:
            continue

    # Build spread results
    spreads = []
    # Sort by closeness to target delta
    sell_candidates = sorted(
        [c for c in candidates if abs(c['delta'] - TARGET_DELTA) <= DELTA_TOL + 0.05],
        key=lambda x: abs(x['delta'] - TARGET_DELTA)
    )

    for sell_leg in sell_candidates[:5]:
        # Find buy leg
        target_buy_strike = (sell_leg['strike'] - width if option_type == 'put'
                             else sell_leg['strike'] + width)
        buy_leg = min(
            [c for c in candidates if c['osi'] != sell_leg['osi']],
            key=lambda x: abs(x['strike'] - target_buy_strike),
            default=None
        )
        if not buy_leg:
            continue

        net_credit      = sell_leg['mid'] - buy_leg['mid']
        actual_width    = abs(sell_leg['strike'] - buy_leg['strike'])
        credit_pct      = net_credit / actual_width if actual_width else 0
        max_risk        = (actual_width - net_credit) * 100
        max_profit      = net_credit * 100
        rr              = actual_width / net_credit if net_credit > 0 else 999
        # Approximate win probability from delta
        win_prob        = (1 - sell_leg['delta']) * 100

        if net_credit <= 0 or credit_pct < MIN_CREDIT_PCT:
            continue

        spreads.append({
            'sell_osi':       sell_leg['osi'],
            'sell_strike':    round(sell_leg['strike'], 2),
            'sell_delta':     round(sell_leg['delta'], 3),
            'sell_bid':       round(sell_leg['bid'], 2),
            'sell_ask':       round(sell_leg['ask'], 2),
            'buy_osi':        buy_leg['osi'],
            'buy_strike':     round(buy_leg['strike'], 2),
            'buy_bid':        round(buy_leg['bid'], 2),
            'buy_ask':        round(buy_leg['ask'], 2),
            'net_credit':     round(net_credit, 2),
            'credit_per_spread': round(net_credit * 100, 2),
            'max_risk':       round(max_risk, 2),
            'max_profit':     round(max_profit, 2),
            'rr_ratio':       round(rr, 1),
            'win_prob':       round(win_prob, 1),
            'credit_pct':     round(credit_pct * 100, 1),
            'iv':             round(sell_leg['iv'], 1),
            'expiry':         best_exp,
            'dte':            actual_dte,
        })

    return ok({
        'spreads':     spreads,
        'count':       len(spreads),
        'underlying':  underlying,
        'type':        spread_type,
        'width':       width,
        'expiry':      best_exp,
        'dte':         actual_dte,
    })


# ── /api/monitor/* ─────────────────────────────────────────────────────────────

def _monitor_loop():
    """Background thread: checks positions every CHECK_INTERVAL_SEC seconds."""
    while True:
        with monitor_lock:
            if not monitor_state['running']:
                break

        try:
            client    = get_client()
            portfolio = client.get_portfolio()
            if isinstance(portfolio, dict):
                positions = portfolio.get('positions', portfolio.get('holdings', []))
            else:
                positions = getattr(portfolio, 'positions', None) or getattr(portfolio, 'holdings', []) or []

            option_positions = []
            for pos in positions:
                sym = get_attr(pos, 'symbol', 'ticker', default='')
                if is_option(sym):
                    option_positions.append({
                        'symbol':   sym,
                        'qty':      safe_float(get_attr(pos, 'quantity', 'qty', 'shares', default=0)),
                        'avg_cost': safe_float(get_attr(pos, 'averageCost', 'average_cost', default=0)),
                    })

            symbols = [p['symbol'] for p in option_positions]
            live = {}
            if symbols:
                qr = client.get_quotes(symbols)
                qs = []
                if isinstance(qr, dict):
                    qs = qr.get('quotes', list(qr.values()))
                elif isinstance(qr, list):
                    qs = qr
                for q in qs:
                    s   = get_attr(q, 'symbol', 'ticker', default='')
                    bid = safe_float(get_attr(q, 'bid', default=0))
                    last = safe_float(get_attr(q, 'lastTradePrice', 'last', default=0))
                    if s:
                        live[s] = {'bid': bid, 'last': last}

            now_time = datetime.now().time()
            eod      = now_time >= EOD_EXIT_TIME
            enriched = []
            for p in option_positions:
                sym  = p['symbol']
                px   = live.get(sym, {})
                curr = px.get('bid', 0) or px.get('last', 0)
                avg  = p['avg_cost']
                pnl_pct = ((curr - avg) / avg) if avg else 0
                pnl_d   = (curr - avg) * p['qty'] * 100

                if eod:
                    action, reason = 'exit', 'EOD close (3:45 PM)'
                elif pnl_pct >= PROFIT_TARGET_PCT:
                    action, reason = 'exit', f'Profit target +{pnl_pct:.1%}'
                elif pnl_pct <= -STOP_LOSS_PCT:
                    action, reason = 'exit', f'Stop loss {pnl_pct:.1%}'
                else:
                    action, reason = 'hold', 'Within range'

                enriched.append({
                    'symbol':      sym,
                    'qty':         p['qty'],
                    'avg_cost':    round(avg, 2),
                    'current':     round(curr, 2),
                    'pnl_pct':     round(pnl_pct * 100, 2),
                    'pnl_dollars': round(pnl_d, 2),
                    'action':      action,
                    'reason':      reason,
                    'target':      round(avg * (1 + PROFIT_TARGET_PCT), 2),
                    'stop':        round(avg * (1 - STOP_LOSS_PCT), 2),
                })

                # Auto-exit
                if action == 'exit' and not READ_ONLY:
                    try:
                        client.place_order(
                            symbol=sym,
                            side='SELL',
                            quantity=int(p['qty']),
                            orderType='LIMIT',
                            limitPrice=round(curr, 2),
                            timeInForce='DAY',
                        )
                        with monitor_lock:
                            monitor_state['log'].append({
                                'ts':     datetime.now().isoformat(),
                                'msg':    f'AUTO EXIT: {sym} — {reason}',
                                'level':  'warn',
                            })
                    except Exception as ex:
                        with monitor_lock:
                            monitor_state['log'].append({
                                'ts':    datetime.now().isoformat(),
                                'msg':   f'Exit order failed for {sym}: {ex}',
                                'level': 'error',
                            })

            with monitor_lock:
                monitor_state['positions']  = enriched
                monitor_state['last_check'] = datetime.now().isoformat()
                # Trim log to last 50 entries
                monitor_state['log'] = monitor_state['log'][-50:]

        except Exception as ex:
            with monitor_lock:
                monitor_state['log'].append({
                    'ts':    datetime.now().isoformat(),
                    'msg':   f'Monitor error: {ex}',
                    'level': 'error',
                })

        time.sleep(CHECK_INTERVAL_SEC)


@app.route('/api/monitor/status')
def api_monitor_status():
    with monitor_lock:
        return ok({
            'running':    monitor_state['running'],
            'last_check': monitor_state['last_check'],
            'positions':  monitor_state['positions'],
            'log':        monitor_state['log'][-20:],
            'interval':   CHECK_INTERVAL_SEC,
        })


@app.route('/api/monitor/start', methods=['POST'])
def api_monitor_start():
    with monitor_lock:
        if monitor_state['running']:
            return ok({'message': 'Monitor already running', 'running': True})
        monitor_state['running'] = True
        t = threading.Thread(target=_monitor_loop, daemon=True)
        monitor_state['thread'] = t
        t.start()
    return ok({'message': 'Monitor started', 'running': True})


@app.route('/api/monitor/stop', methods=['POST'])
def api_monitor_stop():
    with monitor_lock:
        monitor_state['running'] = False
    return ok({'message': 'Monitor stopped', 'running': False})


@app.route('/api/monitor/close', methods=['POST'])
def api_monitor_close():
    body       = request.get_json(force=True) or {}
    symbol     = body.get('symbol', '').upper()
    close_all  = body.get('close_all', False)

    try:
        client = get_client()
    except Exception as e:
        return api_error(str(e))

    read_only = READ_ONLY or os.environ.get('COPILOT_READ_ONLY', '').lower() in ('true', '1', 'yes')

    if not symbol and not close_all:
        return api_error('symbol or close_all required', 400)

    with monitor_lock:
        positions = monitor_state['positions']

    targets = positions if close_all else [p for p in positions if p['symbol'] == symbol]
    if not targets and not close_all:
        return api_error(f'Position {symbol} not found in monitor', 404)

    results = []
    for pos in targets:
        sym  = pos['symbol']
        qty  = int(pos['qty'])
        curr = pos['current']

        if read_only:
            results.append({'symbol': sym, 'status': 'read_only', 'message': 'READ-ONLY: not placed'})
            continue

        try:
            r = client.place_order(
                symbol=sym, side='SELL', quantity=qty,
                orderType='LIMIT', limitPrice=round(curr, 2), timeInForce='DAY',
            )
            order = r if isinstance(r, dict) else (vars(r) if hasattr(r, '__dict__') else {})
            results.append({
                'symbol':   sym,
                'status':   'submitted',
                'order_id': order.get('orderId', order.get('id', 'unknown')),
            })
        except Exception as ex:
            results.append({'symbol': sym, 'status': 'error', 'message': str(ex)})

    return ok({'results': results, 'read_only': read_only})


# ── /api/history ───────────────────────────────────────────────────────────────
@app.route('/api/history')
def api_history():
    days     = int(request.args.get('days', 30))
    show_all = request.args.get('show_all', 'false').lower() == 'true'

    try:
        client = get_client()
    except Exception as e:
        return api_error(str(e))

    try:
        from public_api_sdk import HistoryRequest
        start_dt = datetime.now() - timedelta(days=days)
        end_dt = datetime.now()
        hist_req = HistoryRequest(start=start_dt, end=end_dt, page_size=100)
        resp = client.get_history(history_request=hist_req)
        trades = []
        if isinstance(resp, dict):
            trades = resp.get('trades', resp.get('history', resp.get('orders', [])))
        elif isinstance(resp, list):
            trades = resp
        else:
            trades = getattr(resp, 'trades', None) or getattr(resp, 'history', []) or []
    except Exception as e:
        trades = []  # API error, return empty history

    # Parse trades
    FORMATS = [
        "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
    ]

    def parse_date(raw):
        if not raw:
            return None
        for fmt in FORMATS:
            try:
                return datetime.strptime(str(raw)[:26], fmt)
            except ValueError:
                continue
        return None

    parsed = []
    for t in trades:
        try:
            sym    = get_attr(t, 'symbol', 'ticker', default='')
            side   = (get_attr(t, 'side', 'action', 'orderSide', default='') or '').upper()
            qty    = safe_float(get_attr(t, 'quantity', 'qty', 'filledQuantity', default=0))
            price  = safe_float(get_attr(t, 'price', 'averageFillPrice', 'fillPrice', default=0))
            status = (get_attr(t, 'status', 'orderStatus', default='') or '').upper()
            dt     = parse_date(get_attr(t, 'timestamp', 'createdAt', 'date', 'executedAt', default=None))
            oid    = get_attr(t, 'orderId', 'id', default='')
            is_opt = is_option(sym)
            if status not in ('FILLED', 'PARTIALLY_FILLED', '') or qty <= 0 or price <= 0:
                continue
            if not show_all and not is_opt:
                continue
            parsed.append({
                'order_id': oid, 'symbol': sym, 'side': side,
                'qty': qty, 'price': price, 'date': dt, 'is_option': is_opt,
            })
        except Exception:
            continue

    # Match round-trips
    by_sym = {}
    for t in parsed:
        by_sym.setdefault(t['symbol'], []).append(t)

    completed = []
    for sym, sym_trades in by_sym.items():
        buys  = sorted([t for t in sym_trades if t['side'] in ('BUY', 'B')], key=lambda x: x['date'] or datetime.min)
        sells = sorted([t for t in sym_trades if t['side'] in ('SELL', 'S')], key=lambda x: x['date'] or datetime.min)
        while buys and sells:
            buy  = buys.pop(0)
            sell = sells.pop(0)
            mq   = min(buy['qty'], sell['qty'])
            pnl  = (sell['price'] - buy['price']) * mq * (100 if buy['is_option'] else 1)
            pnl_pct = ((sell['price'] / buy['price']) - 1) * 100 if buy['price'] else 0
            completed.append({
                'symbol':      sym,
                'date':        sell['date'].strftime("%Y-%m-%d") if sell['date'] else '—',
                'side':        'buy→sell',
                'entry':       round(buy['price'], 2),
                'exit':        round(sell['price'], 2),
                'qty':         mq,
                'pnl':         round(pnl, 2),
                'pnl_pct':     round(pnl_pct, 2),
                'reason':      'manual',
                'is_option':   buy['is_option'],
            })

    completed.sort(key=lambda x: x['date'], reverse=True)

    # Stats
    wins   = [t for t in completed if t['pnl'] > 0]
    losses = [t for t in completed if t['pnl'] <= 0]
    total_pnl     = sum(t['pnl'] for t in completed)
    win_rate      = len(wins) / len(completed) * 100 if completed else 0
    avg_win       = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
    avg_loss      = sum(t['pnl'] for t in losses) / len(losses) if losses else 0
    gross_wins    = sum(t['pnl'] for t in wins)
    gross_losses  = abs(sum(t['pnl'] for t in losses)) or 1
    profit_factor = gross_wins / gross_losses

    return ok({
        'trades':        completed,
        'count':         len(completed),
        'raw_count':     len(parsed),
        'days':          days,
        'stats': {
            'total_trades':  len(completed),
            'wins':          len(wins),
            'losses':        len(losses),
            'win_rate':      round(win_rate, 1),
            'total_pnl':     round(total_pnl, 2),
            'avg_win':       round(avg_win, 2),
            'avg_loss':      round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
        },
    })


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('DEBUG', '').lower() in ('true', '1', 'yes')

    print(f"""
╔══════════════════════════════════════════════════════════╗
║          Options Copilot — Web UI                        ║
╠══════════════════════════════════════════════════════════╣
║  URL:      http://{host}:{port:<37}║
║  SDK:      {'✅ Available' if SDK_AVAILABLE else '❌ Missing (pip install publicdotcom-py)':<44}║
║  yfinance: {'✅ Available' if YFINANCE_AVAILABLE else '❌ Missing (pip install yfinance numpy)':<44}║
║  Secret:   {'✅ Set' if (API_SECRET or os.environ.get('PUBLIC_COM_SECRET')) else '❌ Not set (export PUBLIC_COM_SECRET=...)':<44}║
║  Account:  {(ACCOUNT_ID or os.environ.get('PUBLIC_COM_ACCOUNT_ID') or '❌ Not set'):<44}║
║  Mode:     {'🔒 READ-ONLY' if READ_ONLY else '🟢 Live trading':<44}║
╚══════════════════════════════════════════════════════════╝
""")

    app.run(host=host, port=port, debug=debug, threaded=True)
