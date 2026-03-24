#!/usr/bin/env python3
"""
Public.com Options Copilot Dashboard
Competition Edition — March 2026
"""

import os
import sys
import json
import uuid
import time
from datetime import datetime, timedelta
from decimal import Decimal
from flask import Flask, jsonify, render_template_string, request
from dotenv import load_dotenv
import numpy as np

load_dotenv()

# Install dependencies if needed
try:
    import yfinance as yf
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

try:
    from public_api_sdk import (
        PublicApiClient, PublicApiClientConfiguration,
        OrderRequest, OrderInstrument, InstrumentType, OrderSide, OrderType,
        OrderExpirationRequest, TimeInForce, EquityMarketSession, OpenCloseIndicator,
        OptionChainRequest, OptionExpirationsRequest,
    )
    from public_api_sdk.auth_config import ApiKeyAuthConfig
    PUBLIC_SDK_AVAILABLE = True
except ImportError:
    PUBLIC_SDK_AVAILABLE = False

app = Flask(__name__)
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Config helpers
def get_api_secret(): return os.getenv("PUBLIC_COM_SECRET")
def get_account_id(): return os.getenv("PUBLIC_COM_ACCOUNT_ID")

def get_public_client():
    if not PUBLIC_SDK_AVAILABLE: return None
    secret, account_id = get_api_secret(), get_account_id()
    if not secret or not account_id: return None
    try:
        return PublicApiClient(ApiKeyAuthConfig(api_secret_key=secret),
            config=PublicApiClientConfiguration(default_account_number=account_id))
    except: return None

# File helpers
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path) as f: return json.load(f)
    except: pass
    return default

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, indent=2, default=str)

PAPER_FILE = os.path.join(DATA_DIR, "paper_portfolio.json")
TRADES_FILE = os.path.join(DATA_DIR, "paper_trades.json")
STRATEGIES_FILE = os.path.join(DATA_DIR, "strategies.json")
SCORES_FILE = os.path.join(DATA_DIR, "scalper_scores.json")

def get_paper(): return load_json(PAPER_FILE, {"cash": 10000.0, "starting": 10000.0, "positions": {}, "wins": 0, "losses": 0})
def save_paper(p): save_json(PAPER_FILE, p)
def get_trades(): return load_json(TRADES_FILE, [])
def save_trades(t): save_json(TRADES_FILE, t)
def get_strategies(): return load_json(STRATEGIES_FILE, [])
def save_strategies(s): save_json(STRATEGIES_FILE, s)
def get_scores(): return load_json(SCORES_FILE, {"high": 0, "games": []})
def save_scores(s): save_json(SCORES_FILE, s)

# =============================================================================
# HTML TEMPLATE
# =============================================================================

HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Options Copilot — Public.com</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:Inter,-apple-system,sans-serif;display:flex;min-height:100vh}
.sidebar{width:220px;background:linear-gradient(180deg,#0f0f1a,#12121f);border-right:1px solid #1e1e2e;position:fixed;height:100vh;display:flex;flex-direction:column}
.logo{padding:20px;border-bottom:1px solid #1e1e2e}
.logo h1{font-size:1em;color:#a78bfa;display:flex;align-items:center;gap:8px}
.logo p{font-size:.7em;color:#666;margin-top:4px}
.nav-item{display:flex;align-items:center;gap:10px;padding:12px 20px;color:#888;cursor:pointer;border-left:3px solid transparent;transition:.2s}
.nav-item:hover{background:rgba(167,139,250,.1);color:#e0e0e0}
.nav-item.active{background:rgba(167,139,250,.15);color:#a78bfa;border-left-color:#a78bfa}
.nav-icon{font-size:1.1em;width:20px;text-align:center}
.sidebar-footer{margin-top:auto;padding:16px;border-top:1px solid #1e1e2e}
.mode-toggle{display:flex;gap:6px}
.mode-btn{flex:1;padding:8px;border:1px solid #2a2a3e;border-radius:6px;background:transparent;color:#888;cursor:pointer;font-size:.7em}
.mode-btn.active{background:#6366f1;color:#fff;border-color:#6366f1}
.main{flex:1;margin-left:220px;padding:20px}
.page{display:none;animation:fadeIn .3s}
.page.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.header h2{font-size:1.4em;color:#a78bfa}
.badge{padding:4px 12px;border-radius:12px;font-size:.75em}
.badge.live{background:#1e3a2e;color:#4ade80}
.badge.paper{background:#3a2e1e;color:#f0b429}
.grid{display:grid;gap:16px}
.grid-2{grid-template-columns:1fr 1fr}
.grid-3{grid-template-columns:1fr 1fr 1fr}
.grid-4{grid-template-columns:1fr 1fr 1fr 1fr}
@media(max-width:1200px){.grid-2,.grid-3,.grid-4{grid-template-columns:1fr}}
.card{background:#12121a;border:1px solid #1e1e2e;border-radius:12px;padding:20px}
.card h3{color:#a78bfa;font-size:.8em;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px}
.card.full{grid-column:1/-1}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}
.stat-box{background:#0f0f18;border:1px solid #1e1e2e;border-radius:8px;padding:14px;text-align:center}
.stat-box .val{font-size:1.6em;font-weight:600;color:#a78bfa}
.stat-box .val.pos{color:#4ade80}
.stat-box .val.neg{color:#ef4444}
.stat-box .lbl{font-size:.7em;color:#666;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:.8em}
th,td{padding:10px;text-align:left;border-bottom:1px solid #1e1e2e}
th{color:#a78bfa;font-weight:500;font-size:.7em;text-transform:uppercase}
tr:hover{background:rgba(167,139,250,.05)}
.pos{color:#4ade80}
.neg{color:#ef4444}
.input-group{margin-bottom:14px}
.input-group label{display:block;font-size:.75em;color:#888;margin-bottom:6px}
.input-group input,.input-group select,.input-group textarea{width:100%;padding:10px;background:#0f0f18;border:1px solid #2a2a3e;border-radius:6px;color:#e0e0e0;font-family:inherit}
.input-group input:focus,.input-group select:focus{outline:none;border-color:#6366f1}
.input-row{display:flex;gap:10px}
.input-row .input-group{flex:1}
.btn{padding:10px 18px;border:none;border-radius:6px;cursor:pointer;font-family:inherit;font-size:.85em;font-weight:500;transition:.2s}
.btn-primary{background:#6366f1;color:#fff}
.btn-primary:hover{background:#7c3aed}
.btn-success{background:#059669;color:#fff}
.btn-danger{background:#dc2626;color:#fff}
.btn-outline{background:transparent;border:1px solid #2a2a3e;color:#888}
.btn-outline:hover{background:#1e1e2e;color:#e0e0e0}
.btn-group{display:flex;gap:8px}
.search-box{position:relative}
.search-box input{padding-right:80px}
.search-box button{position:absolute;right:4px;top:4px;bottom:4px;padding:0 14px}
.chart{height:320px}
.option-chain{font-size:.75em}
.option-chain td{padding:6px;text-align:center;cursor:pointer}
.option-chain .strike{background:#1e1e2e;font-weight:600;color:#a78bfa}
.option-chain tr:hover td{background:rgba(167,139,250,.1)}
.game-price{font-size:3.5em;font-weight:700;color:#a78bfa;margin:20px 0;text-align:center}
.game-price.up{color:#4ade80}
.game-price.down{color:#ef4444}
.game-btns{display:flex;gap:16px;justify-content:center;margin:20px 0}
.game-btn{font-size:1.5em;padding:16px 50px}
.game-info{text-align:center;padding:16px;background:#0f0f18;border-radius:8px;margin:16px 0}
.toast-container{position:fixed;top:20px;right:20px;z-index:1000}
.toast{background:#1e1e2e;border-left:4px solid #6366f1;padding:12px 20px;border-radius:4px;margin-bottom:8px;animation:slideIn .3s}
.toast.success{border-color:#4ade80}
.toast.error{border-color:#ef4444}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
.loading{text-align:center;padding:30px;color:#666}
.spinner{display:inline-block;width:24px;height:24px;border:3px solid #1e1e2e;border-top-color:#6366f1;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);display:none;justify-content:center;align-items:center;z-index:1000}
.modal-overlay.active{display:flex}
.modal{background:#12121a;border:1px solid #2a2a3e;border-radius:12px;padding:24px;width:90%;max-width:500px}
.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.modal-header h3{color:#a78bfa}
.modal-close{background:none;border:none;color:#666;font-size:1.5em;cursor:pointer}
</style>
</head>
<body>

<div class="sidebar">
  <div class="logo"><h1>📈 Options Copilot</h1><p>Public.com Trading</p></div>
  <nav>
    <div class="nav-item active" data-page="portfolio"><span class="nav-icon">💼</span>Portfolio</div>
    <div class="nav-item" data-page="trading"><span class="nav-icon">📊</span>Trading</div>
    <div class="nav-item" data-page="backtester"><span class="nav-icon">🧪</span>Backtester</div>
    <div class="nav-item" data-page="paper"><span class="nav-icon">📝</span>Paper Trading</div>
    <div class="nav-item" data-page="scalper"><span class="nav-icon">⚡</span>SPY Scalper</div>
    <div class="nav-item" data-page="strategies"><span class="nav-icon">🎯</span>Strategies</div>
  </nav>
  <div class="sidebar-footer">
    <div class="mode-toggle">
      <button class="mode-btn" id="btn-paper">📝 Paper</button>
      <button class="mode-btn active" id="btn-live">💰 Live</button>
    </div>
  </div>
</div>

<div class="main">
<div class="toast-container" id="toasts"></div>

<!-- PORTFOLIO -->
<div class="page active" id="page-portfolio">
  <div class="header"><h2>💼 Portfolio</h2><span class="badge live" id="mode-badge">LIVE</span></div>
  <div class="stat-grid" id="port-stats"></div>
  <div class="grid grid-2">
    <div class="card"><h3>📊 Allocation</h3><div id="alloc-chart" class="chart"></div></div>
    <div class="card"><h3>📈 Value History</h3><div id="value-chart" class="chart"></div></div>
  </div>
  <div class="card" style="margin-top:16px"><h3>📋 Positions</h3><div id="positions-tbl"></div></div>
  <div class="card" style="margin-top:16px"><h3>📜 Orders</h3><div id="orders-tbl"></div></div>
</div>

<!-- TRADING -->
<div class="page" id="page-trading">
  <div class="header"><h2>📊 Trading</h2></div>
  <div class="card" style="margin-bottom:16px">
    <h3>🔍 Search</h3>
    <div class="search-box">
      <input type="text" id="ticker-in" placeholder="Ticker (SPY, AAPL...)" onkeydown="if(event.key==='Enter')searchTicker()">
      <button class="btn btn-primary" onclick="searchTicker()">Search</button>
    </div>
  </div>
  <div id="ticker-info" style="display:none">
    <div class="stat-grid" id="ticker-stats"></div>
    <div class="card" style="margin-bottom:16px"><h3>📈 Chart</h3><div id="price-chart" class="chart"></div></div>
    <div class="grid grid-2">
      <div class="card">
        <h3>🎫 Stock Order</h3>
        <div class="input-row">
          <div class="input-group"><label>Side</label><select id="stk-side"><option value="BUY">Buy</option><option value="SELL">Sell</option></select></div>
          <div class="input-group"><label>Type</label><select id="stk-type"><option value="MARKET">Market</option><option value="LIMIT">Limit</option></select></div>
        </div>
        <div class="input-row">
          <div class="input-group"><label>Qty</label><input type="number" id="stk-qty" placeholder="Shares"></div>
          <div class="input-group"><label>Limit $</label><input type="number" id="stk-limit" step="0.01"></div>
        </div>
        <button class="btn btn-primary" onclick="placeStockOrder()">Place Order</button>
      </div>
      <div class="card"><h3>📅 Expirations</h3><div id="exp-list"></div></div>
    </div>
  </div>
  <div id="chain-box" style="display:none;margin-top:16px">
    <div class="card"><h3>🔗 Option Chain <span id="chain-title"></span></h3><div id="chain-tbl"></div></div>
  </div>
</div>

<!-- BACKTESTER -->
<div class="page" id="page-backtester">
  <div class="header"><h2>🧪 Backtester</h2></div>
  <div class="grid grid-2">
    <div class="card">
      <h3>⚙️ Strategy</h3>
      <div class="input-group"><label>Name</label><input type="text" id="bt-name" placeholder="My Strategy"></div>
      <div class="input-row">
        <div class="input-group"><label>Ticker</label><input type="text" id="bt-ticker" value="SPY"></div>
        <div class="input-group"><label>Period</label><select id="bt-period"><option value="1y">1Y</option><option value="2y">2Y</option><option value="5y">5Y</option></select></div>
      </div>
      <div class="input-group"><label>Type</label>
        <select id="bt-strat" onchange="updateBtParams()">
          <option value="sma_cross">SMA Crossover</option>
          <option value="rsi">RSI Mean Reversion</option>
          <option value="breakout">Breakout</option>
        </select>
      </div>
      <div id="bt-params">
        <div class="input-row">
          <div class="input-group"><label>Fast SMA</label><input type="number" id="bt-fast" value="10"></div>
          <div class="input-group"><label>Slow SMA</label><input type="number" id="bt-slow" value="30"></div>
        </div>
      </div>
      <div class="input-row">
        <div class="input-group"><label>Capital $</label><input type="number" id="bt-cap" value="10000"></div>
        <div class="input-group"><label>Size %</label><input type="number" id="bt-size" value="100"></div>
      </div>
      <button class="btn btn-primary" onclick="runBacktest()">🚀 Run</button>
      <button class="btn btn-outline" onclick="saveStrategy()" style="margin-left:8px">💾 Save</button>
    </div>
    <div class="card"><h3>📊 Results</h3><div id="bt-results"><p style="color:#666;text-align:center;padding:40px">Run a backtest</p></div></div>
  </div>
  <div class="card" style="margin-top:16px"><h3>📈 Equity Curve</h3><div id="bt-equity" class="chart"></div></div>
  <div class="card" style="margin-top:16px"><h3>📋 Trades</h3><div id="bt-trades"></div></div>
</div>

<!-- PAPER TRADING -->
<div class="page" id="page-paper">
  <div class="header"><h2>📝 Paper Trading</h2><span class="badge paper">SIMULATED</span></div>
  <div class="stat-grid" id="paper-stats"></div>
  <div class="grid grid-2">
    <div class="card">
      <h3>📈 Quick Trade</h3>
      <div class="input-row">
        <div class="input-group"><label>Ticker</label><input type="text" id="paper-ticker" placeholder="SPY"></div>
        <div class="input-group"><label>Shares</label><input type="number" id="paper-qty" value="10"></div>
      </div>
      <div class="btn-group">
        <button class="btn btn-success" onclick="paperTrade('BUY')">BUY</button>
        <button class="btn btn-danger" onclick="paperTrade('SELL')">SELL</button>
      </div>
    </div>
    <div class="card"><h3>📊 P/L Chart</h3><div id="paper-pnl-chart" class="chart"></div></div>
  </div>
  <div class="card" style="margin-top:16px"><h3>📋 Positions</h3><div id="paper-positions"></div></div>
  <div class="card" style="margin-top:16px"><h3>📜 History</h3><div id="paper-history"></div></div>
  <div style="margin-top:16px"><button class="btn btn-outline" onclick="resetPaper()">🔄 Reset Portfolio</button></div>
</div>

<!-- SPY SCALPER -->
<div class="page" id="page-scalper">
  <div class="header"><h2>⚡ SPY Scalper Game</h2></div>
  <div class="card">
    <div class="game-info"><strong>High Score:</strong> $<span id="high-score">0</span></div>
    <div class="game-price" id="spy-price">$---</div>
    <div class="game-info" id="game-position" style="display:none">
      <div>Position: <span id="pos-side">--</span> @ $<span id="pos-entry">--</span></div>
      <div style="font-size:1.2em;margin-top:8px">P/L: <span id="pos-pnl">$0</span></div>
    </div>
    <div class="game-btns">
      <button class="btn btn-success game-btn" id="btn-buy" onclick="scalperBuy()">BUY</button>
      <button class="btn btn-danger game-btn" id="btn-sell" onclick="scalperSell()">SELL</button>
    </div>
    <div class="game-info">
      <div>Session P/L: <span id="session-pnl" style="font-size:1.3em;font-weight:600">$0</span></div>
      <div style="margin-top:8px">Trades: <span id="trade-count">0</span> | Wins: <span id="win-count">0</span></div>
    </div>
    <div style="text-align:center;margin-top:16px">
      <button class="btn btn-outline" onclick="resetScalper()">🔄 New Session</button>
    </div>
  </div>
  <div class="card" style="margin-top:16px"><h3>📈 SPY Chart</h3><div id="spy-chart" class="chart"></div></div>
</div>

<!-- STRATEGIES -->
<div class="page" id="page-strategies">
  <div class="header"><h2>🎯 Saved Strategies</h2></div>
  <div class="card"><div id="strat-list"></div></div>
</div>

</div>

<!-- ORDER MODAL -->
<div class="modal-overlay" id="order-modal">
  <div class="modal">
    <div class="modal-header"><h3>🎫 Place Option Order</h3><button class="modal-close" onclick="closeModal()">&times;</button></div>
    <div id="modal-option-info"></div>
    <div class="input-row">
      <div class="input-group"><label>Side</label><select id="opt-side"><option value="BUY">Buy</option><option value="SELL">Sell</option></select></div>
      <div class="input-group"><label>Open/Close</label><select id="opt-oc"><option value="OPEN">Open</option><option value="CLOSE">Close</option></select></div>
    </div>
    <div class="input-row">
      <div class="input-group"><label>Contracts</label><input type="number" id="opt-qty" value="1"></div>
      <div class="input-group"><label>Limit $</label><input type="number" id="opt-limit" step="0.01"></div>
    </div>
    <button class="btn btn-primary" onclick="placeOptionOrder()">Place Order</button>
  </div>
</div>

<script>
// State
let mode = 'live';
let currentTicker = '';
let currentExp = '';
let scalperPos = null;
let scalperPnl = 0;
let scalperTrades = 0;
let scalperWins = 0;
let spyInterval = null;
let selectedOption = null;

// Navigation
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById('page-' + item.dataset.page).classList.add('active');
    if (item.dataset.page === 'portfolio') loadPortfolio();
    if (item.dataset.page === 'paper') loadPaper();
    if (item.dataset.page === 'scalper') startScalper();
    if (item.dataset.page === 'strategies') loadStrategies();
  });
});

// Mode toggle
document.getElementById('btn-paper').onclick = () => { mode = 'paper'; updateMode(); };
document.getElementById('btn-live').onclick = () => { mode = 'live'; updateMode(); };
function updateMode() {
  document.getElementById('btn-paper').classList.toggle('active', mode === 'paper');
  document.getElementById('btn-live').classList.toggle('active', mode === 'live');
  document.getElementById('mode-badge').textContent = mode === 'live' ? 'LIVE' : 'PAPER';
  document.getElementById('mode-badge').className = 'badge ' + mode;
  loadPortfolio();
}

// Toast
function toast(msg, type='info') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.getElementById('toasts').appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// API fetch helper
async function api(path, opts = {}) {
  try {
    const r = await fetch(path, opts);
    return await r.json();
  } catch (e) {
    console.error(e);
    return { error: e.message };
  }
}

// Portfolio
async function loadPortfolio() {
  const data = mode === 'live' ? await api('/api/portfolio') : await api('/api/paper/portfolio');
  if (data.error) {
    document.getElementById('port-stats').innerHTML = '<div class="stat-box"><div class="val">--</div><div class="lbl">Connect API</div></div>';
    return;
  }
  const equity = data.total_equity || (data.cash + (data.positions_value || 0));
  const bp = data.buying_power || data.cash;
  const dayPnl = data.day_pnl || 0;
  const totalPnl = data.total_pnl || (equity - (data.starting || 10000));
  document.getElementById('port-stats').innerHTML = `
    <div class="stat-box"><div class="val">$${equity.toLocaleString(undefined,{minimumFractionDigits:2})}</div><div class="lbl">Equity</div></div>
    <div class="stat-box"><div class="val">$${bp.toLocaleString(undefined,{minimumFractionDigits:2})}</div><div class="lbl">Buying Power</div></div>
    <div class="stat-box"><div class="val ${dayPnl>=0?'pos':'neg'}">$${dayPnl.toLocaleString(undefined,{minimumFractionDigits:2})}</div><div class="lbl">Day P/L</div></div>
    <div class="stat-box"><div class="val ${totalPnl>=0?'pos':'neg'}">$${totalPnl.toLocaleString(undefined,{minimumFractionDigits:2})}</div><div class="lbl">Total P/L</div></div>
  `;
  // Positions table
  const positions = data.positions || [];
  if (Array.isArray(positions) && positions.length > 0) {
    let html = '<table><thead><tr><th>Symbol</th><th>Qty</th><th>Value</th><th>P/L</th><th>P/L %</th></tr></thead><tbody>';
    positions.forEach(p => {
      const pnl = p.gain_value || 0;
      const pnlPct = p.gain_pct || 0;
      html += `<tr><td>${p.symbol}</td><td>${p.quantity}</td><td>$${(p.value||0).toLocaleString(undefined,{minimumFractionDigits:2})}</td>
        <td class="${pnl>=0?'pos':'neg'}">$${pnl.toFixed(2)}</td><td class="${pnlPct>=0?'pos':'neg'}">${pnlPct.toFixed(2)}%</td></tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('positions-tbl').innerHTML = html;
  } else {
    document.getElementById('positions-tbl').innerHTML = '<p style="color:#666;padding:20px;text-align:center">No positions</p>';
  }
  // Orders
  const orders = data.orders || [];
  if (orders.length > 0) {
    let html = '<table><thead><tr><th>Symbol</th><th>Side</th><th>Type</th><th>Qty</th><th>Status</th></tr></thead><tbody>';
    orders.forEach(o => {
      html += `<tr><td>${o.symbol}</td><td>${o.side}</td><td>${o.type}</td><td>${o.quantity||o.amount}</td><td>${o.status}</td></tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('orders-tbl').innerHTML = html;
  } else {
    document.getElementById('orders-tbl').innerHTML = '<p style="color:#666;padding:20px;text-align:center">No open orders</p>';
  }
  // Allocation chart
  if (data.allocation && data.allocation.length > 0) {
    Plotly.newPlot('alloc-chart', [{values: data.allocation.map(a=>a.value), labels: data.allocation.map(a=>a.type), type: 'pie', hole: 0.5, marker: {colors: ['#6366f1','#a78bfa','#8b5cf6','#c4b5fd']}, textinfo: 'label+percent', textfont: {color:'#fff'}}], {paper_bgcolor:'transparent', plot_bgcolor:'transparent', showlegend:false, margin:{t:20,b:20,l:20,r:20}}, {responsive:true});
  }
}

// Trading - Search
async function searchTicker() {
  const ticker = document.getElementById('ticker-in').value.toUpperCase().trim();
  if (!ticker) return;
  currentTicker = ticker;
  document.getElementById('ticker-info').style.display = 'block';
  document.getElementById('chain-box').style.display = 'none';
  const data = await api('/api/quote/' + ticker);
  if (data.error) { toast(data.error, 'error'); return; }
  document.getElementById('ticker-stats').innerHTML = `
    <div class="stat-box"><div class="val">$${data.price?.toFixed(2)||'--'}</div><div class="lbl">Price</div></div>
    <div class="stat-box"><div class="val ${data.change>=0?'pos':'neg'}">${data.change>=0?'+':''}${data.change?.toFixed(2)||'--'}</div><div class="lbl">Change</div></div>
    <div class="stat-box"><div class="val">${(data.volume/1000000)?.toFixed(1)||'--'}M</div><div class="lbl">Volume</div></div>
    <div class="stat-box"><div class="val">$${data.high?.toFixed(2)||'--'}</div><div class="lbl">High</div></div>
  `;
  // Chart
  const chart = await api('/api/chart/' + ticker);
  if (chart.dates) {
    Plotly.newPlot('price-chart', [{x: chart.dates, y: chart.closes, type:'scatter', mode:'lines', line:{color:'#6366f1'}}], {paper_bgcolor:'transparent', plot_bgcolor:'#0f0f18', xaxis:{color:'#666'}, yaxis:{color:'#666'}, margin:{t:20,b:40,l:50,r:20}}, {responsive:true});
  }
  // Expirations
  const exp = await api('/api/expirations/' + ticker);
  if (exp.expirations) {
    let html = '<div style="display:flex;flex-wrap:wrap;gap:8px">';
    exp.expirations.slice(0,12).forEach(e => {
      html += `<button class="btn btn-outline" onclick="loadChain('${e}')">${e}</button>`;
    });
    html += '</div>';
    document.getElementById('exp-list').innerHTML = html;
  } else {
    document.getElementById('exp-list').innerHTML = '<p style="color:#666">No options available</p>';
  }
}

async function loadChain(exp) {
  currentExp = exp;
  document.getElementById('chain-box').style.display = 'block';
  document.getElementById('chain-title').textContent = `- ${currentTicker} ${exp}`;
  const data = await api(`/api/chain/${currentTicker}/${exp}`);
  if (!data.calls || !data.puts) {
    document.getElementById('chain-tbl').innerHTML = '<p style="color:#666;padding:20px">No data</p>';
    return;
  }
  let html = '<table class="option-chain"><thead><tr><th>Bid</th><th>Ask</th><th>Last</th><th>Vol</th><th>Strike</th><th>Bid</th><th>Ask</th><th>Last</th><th>Vol</th></tr></thead><tbody>';
  const strikes = [...new Set([...data.calls.map(c=>c.strike), ...data.puts.map(p=>p.strike)])].sort((a,b)=>a-b);
  const callMap = Object.fromEntries(data.calls.map(c=>[c.strike, c]));
  const putMap = Object.fromEntries(data.puts.map(p=>[p.strike, p]));
  strikes.forEach(s => {
    const c = callMap[s] || {};
    const p = putMap[s] || {};
    html += `<tr>
      <td onclick="showOptionModal('${c.symbol}','CALL',${s},${c.bid||0},${c.ask||0})">${c.bid?.toFixed(2)||'-'}</td>
      <td onclick="showOptionModal('${c.symbol}','CALL',${s},${c.bid||0},${c.ask||0})">${c.ask?.toFixed(2)||'-'}</td>
      <td>${c.last?.toFixed(2)||'-'}</td>
      <td>${c.volume||'-'}</td>
      <td class="strike">${s.toFixed(2)}</td>
      <td onclick="showOptionModal('${p.symbol}','PUT',${s},${p.bid||0},${p.ask||0})">${p.bid?.toFixed(2)||'-'}</td>
      <td onclick="showOptionModal('${p.symbol}','PUT',${s},${p.bid||0},${p.ask||0})">${p.ask?.toFixed(2)||'-'}</td>
      <td>${p.last?.toFixed(2)||'-'}</td>
      <td>${p.volume||'-'}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('chain-tbl').innerHTML = html;
}

function showOptionModal(symbol, type, strike, bid, ask) {
  if (!symbol) return;
  selectedOption = {symbol, type, strike};
  document.getElementById('modal-option-info').innerHTML = `<p style="margin-bottom:16px"><strong>${currentTicker}</strong> ${currentExp} <strong>${strike}</strong> ${type}<br>Bid: $${bid.toFixed(2)} | Ask: $${ask.toFixed(2)}</p>`;
  document.getElementById('opt-limit').value = ((bid+ask)/2).toFixed(2);
  document.getElementById('order-modal').classList.add('active');
}
function closeModal() { document.getElementById('order-modal').classList.remove('active'); }

async function placeStockOrder() {
  const data = {
    symbol: currentTicker,
    side: document.getElementById('stk-side').value,
    type: document.getElementById('stk-type').value,
    quantity: parseFloat(document.getElementById('stk-qty').value),
    limit_price: parseFloat(document.getElementById('stk-limit').value) || null
  };
  if (mode === 'paper') {
    const r = await api('/api/paper/trade', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    toast(r.message || r.error, r.error ? 'error' : 'success');
  } else {
    const r = await api('/api/order/stock', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    toast(r.message || r.error, r.error ? 'error' : 'success');
  }
  loadPortfolio();
}

async function placeOptionOrder() {
  const data = {
    symbol: selectedOption.symbol,
    side: document.getElementById('opt-side').value,
    open_close: document.getElementById('opt-oc').value,
    quantity: parseInt(document.getElementById('opt-qty').value),
    limit_price: parseFloat(document.getElementById('opt-limit').value)
  };
  const r = await api('/api/order/option', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  toast(r.message || r.error, r.error ? 'error' : 'success');
  closeModal();
  loadPortfolio();
}

// Backtester
function updateBtParams() {
  const strat = document.getElementById('bt-strat').value;
  let html = '';
  if (strat === 'sma_cross') {
    html = '<div class="input-row"><div class="input-group"><label>Fast SMA</label><input type="number" id="bt-fast" value="10"></div><div class="input-group"><label>Slow SMA</label><input type="number" id="bt-slow" value="30"></div></div>';
  } else if (strat === 'rsi') {
    html = '<div class="input-row"><div class="input-group"><label>RSI Period</label><input type="number" id="bt-rsi-period" value="14"></div><div class="input-group"><label>Oversold</label><input type="number" id="bt-oversold" value="30"></div></div><div class="input-row"><div class="input-group"><label>Overbought</label><input type="number" id="bt-overbought" value="70"></div><div class="input-group"></div></div>';
  } else if (strat === 'breakout') {
    html = '<div class="input-row"><div class="input-group"><label>Period</label><input type="number" id="bt-breakout-period" value="20"></div><div class="input-group"></div></div>';
  }
  document.getElementById('bt-params').innerHTML = html;
}

async function runBacktest() {
  const strat = document.getElementById('bt-strat').value;
  const params = {
    ticker: document.getElementById('bt-ticker').value.toUpperCase(),
    period: document.getElementById('bt-period').value,
    strategy: strat,
    capital: parseFloat(document.getElementById('bt-cap').value),
    position_size: parseFloat(document.getElementById('bt-size').value) / 100
  };
  if (strat === 'sma_cross') {
    params.fast = parseInt(document.getElementById('bt-fast')?.value || 10);
    params.slow = parseInt(document.getElementById('bt-slow')?.value || 30);
  } else if (strat === 'rsi') {
    params.rsi_period = parseInt(document.getElementById('bt-rsi-period')?.value || 14);
    params.oversold = parseInt(document.getElementById('bt-oversold')?.value || 30);
    params.overbought = parseInt(document.getElementById('bt-overbought')?.value || 70);
  } else if (strat === 'breakout') {
    params.breakout_period = parseInt(document.getElementById('bt-breakout-period')?.value || 20);
  }
  document.getElementById('bt-results').innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  const r = await api('/api/backtest', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(params)});
  if (r.error) { document.getElementById('bt-results').innerHTML = `<p style="color:#ef4444">${r.error}</p>`; return; }
  const m = r.metrics;
  document.getElementById('bt-results').innerHTML = `
    <div class="stat-grid">
      <div class="stat-box"><div class="val ${m.total_return>=0?'pos':'neg'}">${m.total_return.toFixed(2)}%</div><div class="lbl">Return</div></div>
      <div class="stat-box"><div class="val">${m.sharpe.toFixed(2)}</div><div class="lbl">Sharpe</div></div>
      <div class="stat-box"><div class="val neg">${m.max_drawdown.toFixed(2)}%</div><div class="lbl">Max DD</div></div>
      <div class="stat-box"><div class="val">${m.win_rate.toFixed(1)}%</div><div class="lbl">Win Rate</div></div>
      <div class="stat-box"><div class="val">${m.trades}</div><div class="lbl">Trades</div></div>
      <div class="stat-box"><div class="val">${m.profit_factor.toFixed(2)}</div><div class="lbl">Profit Factor</div></div>
    </div>
  `;
  Plotly.newPlot('bt-equity', [{x:r.equity.dates, y:r.equity.values, type:'scatter', mode:'lines', line:{color:'#6366f1'}, fill:'tozeroy', fillcolor:'rgba(99,102,241,0.2)'}], {paper_bgcolor:'transparent', plot_bgcolor:'#0f0f18', xaxis:{color:'#666'}, yaxis:{color:'#666'}, margin:{t:20,b:40,l:50,r:20}}, {responsive:true});
  if (r.trades && r.trades.length > 0) {
    let html = '<table><thead><tr><th>Date</th><th>Type</th><th>Price</th><th>P/L</th></tr></thead><tbody>';
    r.trades.slice(-20).forEach(t => {
      html += `<tr><td>${t.date}</td><td>${t.type}</td><td>$${t.price.toFixed(2)}</td><td class="${t.pnl>=0?'pos':'neg'}">$${t.pnl.toFixed(2)}</td></tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('bt-trades').innerHTML = html;
  }
}

async function saveStrategy() {
  const name = document.getElementById('bt-name').value || 'Unnamed Strategy';
  const params = {
    name,
    ticker: document.getElementById('bt-ticker').value,
    strategy: document.getElementById('bt-strat').value,
    capital: parseFloat(document.getElementById('bt-cap').value),
    position_size: parseFloat(document.getElementById('bt-size').value) / 100,
    live: false
  };
  const r = await api('/api/strategy/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(params)});
  toast(r.message || r.error, r.error ? 'error' : 'success');
}

// Paper Trading
async function loadPaper() {
  const data = await api('/api/paper/portfolio');
  const equity = data.cash + (data.positions_value || 0);
  const pnl = equity - (data.starting || 10000);
  document.getElementById('paper-stats').innerHTML = `
    <div class="stat-box"><div class="val">$${equity.toLocaleString(undefined,{minimumFractionDigits:2})}</div><div class="lbl">Equity</div></div>
    <div class="stat-box"><div class="val">$${data.cash.toLocaleString(undefined,{minimumFractionDigits:2})}</div><div class="lbl">Cash</div></div>
    <div class="stat-box"><div class="val ${pnl>=0?'pos':'neg'}">$${pnl.toFixed(2)}</div><div class="lbl">P/L</div></div>
    <div class="stat-box"><div class="val">${data.wins||0}/${(data.wins||0)+(data.losses||0)}</div><div class="lbl">W/L</div></div>
  `;
  // Positions
  const positions = data.positions || {};
  const posArr = Object.entries(positions);
  if (posArr.length > 0) {
    let html = '<table><thead><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Value</th><th>P/L</th><th></th></tr></thead><tbody>';
    for (const [sym, pos] of posArr) {
      const quote = await api('/api/quote/' + sym);
      const val = (quote.price || pos.avg_price) * pos.quantity;
      const pnl = (quote.price - pos.avg_price) * pos.quantity;
      html += `<tr><td>${sym}</td><td>${pos.quantity}</td><td>$${pos.avg_price.toFixed(2)}</td><td>$${val.toFixed(2)}</td><td class="${pnl>=0?'pos':'neg'}">$${pnl.toFixed(2)}</td><td><button class="btn btn-outline" onclick="closePaperPosition('${sym}')">Close</button></td></tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('paper-positions').innerHTML = html;
  } else {
    document.getElementById('paper-positions').innerHTML = '<p style="color:#666;padding:20px;text-align:center">No positions</p>';
  }
  // History
  const trades = await api('/api/paper/trades');
  if (trades.length > 0) {
    let html = '<table><thead><tr><th>Date</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>P/L</th></tr></thead><tbody>';
    trades.slice(-20).reverse().forEach(t => {
      html += `<tr><td>${t.date}</td><td>${t.symbol}</td><td>${t.side}</td><td>${t.quantity}</td><td>$${t.price.toFixed(2)}</td><td class="${(t.pnl||0)>=0?'pos':'neg'}">$${(t.pnl||0).toFixed(2)}</td></tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('paper-history').innerHTML = html;
  }
}

async function paperTrade(side) {
  const sym = document.getElementById('paper-ticker').value.toUpperCase();
  const qty = parseInt(document.getElementById('paper-qty').value);
  if (!sym || !qty) { toast('Enter ticker and quantity', 'error'); return; }
  const r = await api('/api/paper/trade', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol:sym, side, quantity:qty})});
  toast(r.message || r.error, r.error ? 'error' : 'success');
  loadPaper();
}

async function closePaperPosition(sym) {
  const data = await api('/api/paper/portfolio');
  const pos = data.positions[sym];
  if (!pos) return;
  const r = await api('/api/paper/trade', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol:sym, side:'SELL', quantity:pos.quantity})});
  toast(r.message || r.error, r.error ? 'error' : 'success');
  loadPaper();
}

async function resetPaper() {
  await api('/api/paper/reset', {method:'POST'});
  toast('Portfolio reset to $10,000', 'success');
  loadPaper();
}

// SPY Scalper Game
async function startScalper() {
  if (spyInterval) clearInterval(spyInterval);
  const scores = await api('/api/scalper/scores');
  document.getElementById('high-score').textContent = scores.high?.toFixed(2) || '0';
  updateSpyPrice();
  spyInterval = setInterval(updateSpyPrice, 3000);
  // Load chart
  const chart = await api('/api/chart/SPY');
  if (chart.dates) {
    Plotly.newPlot('spy-chart', [{x:chart.dates.slice(-60), y:chart.closes.slice(-60), type:'scatter', mode:'lines', line:{color:'#6366f1'}}], {paper_bgcolor:'transparent', plot_bgcolor:'#0f0f18', xaxis:{color:'#666'}, yaxis:{color:'#666'}, margin:{t:20,b:40,l:50,r:20}}, {responsive:true});
  }
}

async function updateSpyPrice() {
  const q = await api('/api/quote/SPY');
  const el = document.getElementById('spy-price');
  const oldPrice = parseFloat(el.dataset.price) || q.price;
  el.textContent = '$' + (q.price?.toFixed(2) || '--');
  el.className = 'game-price ' + (q.price > oldPrice ? 'up' : q.price < oldPrice ? 'down' : '');
  el.dataset.price = q.price;
  if (scalperPos) {
    const pnl = scalperPos.side === 'LONG' ? (q.price - scalperPos.entry) * 100 : (scalperPos.entry - q.price) * 100;
    document.getElementById('pos-pnl').textContent = '$' + pnl.toFixed(2);
    document.getElementById('pos-pnl').className = pnl >= 0 ? 'pos' : 'neg';
  }
}

function scalperBuy() {
  const price = parseFloat(document.getElementById('spy-price').dataset.price);
  if (scalperPos) {
    if (scalperPos.side === 'SHORT') {
      const pnl = (scalperPos.entry - price) * 100;
      scalperPnl += pnl;
      scalperTrades++;
      if (pnl > 0) scalperWins++;
      scalperPos = null;
      document.getElementById('game-position').style.display = 'none';
    }
  } else {
    scalperPos = {side:'LONG', entry:price};
    document.getElementById('game-position').style.display = 'block';
    document.getElementById('pos-side').textContent = 'LONG';
    document.getElementById('pos-entry').textContent = price.toFixed(2);
  }
  updateScalperUI();
}

function scalperSell() {
  const price = parseFloat(document.getElementById('spy-price').dataset.price);
  if (scalperPos) {
    if (scalperPos.side === 'LONG') {
      const pnl = (price - scalperPos.entry) * 100;
      scalperPnl += pnl;
      scalperTrades++;
      if (pnl > 0) scalperWins++;
      scalperPos = null;
      document.getElementById('game-position').style.display = 'none';
    }
  } else {
    scalperPos = {side:'SHORT', entry:price};
    document.getElementById('game-position').style.display = 'block';
    document.getElementById('pos-side').textContent = 'SHORT';
    document.getElementById('pos-entry').textContent = price.toFixed(2);
  }
  updateScalperUI();
}

function updateScalperUI() {
  document.getElementById('session-pnl').textContent = '$' + scalperPnl.toFixed(2);
  document.getElementById('session-pnl').className = scalperPnl >= 0 ? 'pos' : 'neg';
  document.getElementById('trade-count').textContent = scalperTrades;
  document.getElementById('win-count').textContent = scalperWins;
  api('/api/scalper/update', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({pnl:scalperPnl, trades:scalperTrades, wins:scalperWins})});
}

function resetScalper() {
  scalperPos = null;
  scalperPnl = 0;
  scalperTrades = 0;
  scalperWins = 0;
  document.getElementById('game-position').style.display = 'none';
  updateScalperUI();
}

// Strategies
async function loadStrategies() {
  const strats = await api('/api/strategies');
  if (!strats.length) {
    document.getElementById('strat-list').innerHTML = '<p style="color:#666;padding:20px;text-align:center">No saved strategies. Create one in the Backtester.</p>';
    return;
  }
  let html = '<table><thead><tr><th>Name</th><th>Ticker</th><th>Type</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
  strats.forEach((s, i) => {
    html += `<tr><td>${s.name}</td><td>${s.ticker}</td><td>${s.strategy}</td><td><span class="badge ${s.live?'live':'paper'}">${s.live?'LIVE':'PAPER'}</span></td>
      <td><button class="btn btn-outline" onclick="toggleStrategyLive(${i})">${s.live?'Disable':'Enable'}</button>
      <button class="btn btn-danger" onclick="deleteStrategy(${i})" style="margin-left:4px">Delete</button></td></tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('strat-list').innerHTML = html;
}

async function toggleStrategyLive(idx) {
  await api('/api/strategy/toggle/' + idx, {method:'POST'});
  loadStrategies();
}

async function deleteStrategy(idx) {
  await api('/api/strategy/delete/' + idx, {method:'POST'});
  loadStrategies();
}

// Init
loadPortfolio();
</script>
</body>
</html>'''

# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/portfolio')
def api_portfolio():
    """Get live portfolio from Public.com"""
    client = get_public_client()
    if not client:
        return jsonify({"error": "API not configured", "positions": [], "orders": []})
    try:
        portfolio = client.get_portfolio()
        total_equity = sum(e.value for e in portfolio.equity)
        positions = []
        for p in portfolio.positions or []:
            pos = {
                "symbol": p.instrument.symbol,
                "name": p.instrument.name,
                "type": p.instrument.type.value,
                "quantity": p.quantity,
                "value": float(p.current_value),
                "last_price": float(p.last_price.last_price) if p.last_price else 0,
            }
            if p.position_daily_gain:
                pos["day_gain"] = float(p.position_daily_gain.gain_value)
                pos["day_gain_pct"] = float(p.position_daily_gain.gain_percentage)
            if p.cost_basis:
                pos["gain_value"] = float(p.cost_basis.gain_value)
                pos["gain_pct"] = float(p.cost_basis.gain_percentage)
            positions.append(pos)
        orders = []
        for o in portfolio.orders or []:
            orders.append({
                "order_id": o.order_id,
                "symbol": o.instrument.symbol,
                "side": o.side.value,
                "type": o.type.value,
                "status": o.status.value,
                "quantity": o.quantity,
                "amount": float(o.notional_value) if o.notional_value else None,
            })
        allocation = [{"type": e.type.value.replace("_", " ").title(), "value": float(e.value)} for e in portfolio.equity]
        client.close()
        return jsonify({
            "total_equity": float(total_equity),
            "buying_power": float(portfolio.buying_power.buying_power),
            "options_bp": float(portfolio.buying_power.options_buying_power),
            "day_pnl": sum(p.get("day_gain", 0) for p in positions),
            "total_pnl": sum(p.get("gain_value", 0) for p in positions),
            "positions": positions,
            "orders": orders,
            "allocation": allocation,
        })
    except Exception as e:
        return jsonify({"error": str(e), "positions": [], "orders": []})

@app.route('/api/quote/<ticker>')
def api_quote(ticker):
    """Get quote for ticker using yfinance"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="2d")
        if hist.empty:
            return jsonify({"error": "No data"})
        price = float(hist['Close'].iloc[-1])
        prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else price
        return jsonify({
            "symbol": ticker,
            "price": price,
            "change": price - prev,
            "change_pct": ((price - prev) / prev) * 100 if prev else 0,
            "volume": int(hist['Volume'].iloc[-1]),
            "high": float(hist['High'].iloc[-1]),
            "low": float(hist['Low'].iloc[-1]),
            "open": float(hist['Open'].iloc[-1]),
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/chart/<ticker>')
def api_chart(ticker):
    """Get price history for chart"""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo")
        if hist.empty:
            return jsonify({"error": "No data"})
        return jsonify({
            "dates": hist.index.strftime('%Y-%m-%d').tolist(),
            "closes": hist['Close'].tolist(),
            "highs": hist['High'].tolist(),
            "lows": hist['Low'].tolist(),
            "volumes": hist['Volume'].tolist(),
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/expirations/<ticker>')
def api_expirations(ticker):
    """Get option expirations"""
    client = get_public_client()
    if client:
        try:
            req = OptionExpirationsRequest(instrument=OrderInstrument(symbol=ticker, type=InstrumentType.EQUITY))
            resp = client.get_option_expirations(req)
            exps = [str(e) for e in (resp.expirations or [])]
            client.close()
            return jsonify({"expirations": exps})
        except Exception as e:
            return jsonify({"error": str(e)})
    # Fallback to yfinance
    try:
        t = yf.Ticker(ticker)
        return jsonify({"expirations": list(t.options)})
    except:
        return jsonify({"expirations": []})

@app.route('/api/chain/<ticker>/<expiration>')
def api_chain(ticker, expiration):
    """Get option chain"""
    client = get_public_client()
    if client:
        try:
            req = OptionChainRequest(instrument=OrderInstrument(symbol=ticker, type=InstrumentType.EQUITY), expiration_date=expiration)
            chain = client.get_option_chain(req)
            calls = [{"symbol": c.instrument.symbol, "strike": int(c.instrument.symbol[-8:])/1000, "bid": float(c.bid) if c.bid else None, "ask": float(c.ask) if c.ask else None, "last": float(c.last) if c.last else None, "volume": c.volume} for c in (chain.calls or [])]
            puts = [{"symbol": p.instrument.symbol, "strike": int(p.instrument.symbol[-8:])/1000, "bid": float(p.bid) if p.bid else None, "ask": float(p.ask) if p.ask else None, "last": float(p.last) if p.last else None, "volume": p.volume} for p in (chain.puts or [])]
            client.close()
            return jsonify({"calls": calls, "puts": puts})
        except Exception as e:
            return jsonify({"error": str(e)})
    # Fallback to yfinance
    try:
        t = yf.Ticker(ticker)
        opt = t.option_chain(expiration)
        calls = [{"symbol": f"{ticker}{expiration.replace('-','')}C{int(r['strike']*1000):08d}", "strike": r['strike'], "bid": r['bid'], "ask": r['ask'], "last": r['lastPrice'], "volume": int(r['volume']) if not np.isnan(r['volume']) else 0} for _, r in opt.calls.iterrows()]
        puts = [{"symbol": f"{ticker}{expiration.replace('-','')}P{int(r['strike']*1000):08d}", "strike": r['strike'], "bid": r['bid'], "ask": r['ask'], "last": r['lastPrice'], "volume": int(r['volume']) if not np.isnan(r['volume']) else 0} for _, r in opt.puts.iterrows()]
        return jsonify({"calls": calls, "puts": puts})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/order/stock', methods=['POST'])
def api_order_stock():
    """Place stock order via Public.com"""
    client = get_public_client()
    if not client:
        return jsonify({"error": "API not configured"})
    try:
        data = request.json
        order_type = OrderType.LIMIT if data.get('limit_price') else OrderType.MARKET
        kwargs = {
            "order_id": str(uuid.uuid4()),
            "instrument": OrderInstrument(symbol=data['symbol'], type=InstrumentType.EQUITY),
            "order_side": OrderSide.BUY if data['side'] == 'BUY' else OrderSide.SELL,
            "order_type": order_type,
            "quantity": data['quantity'],
            "expiration": OrderExpirationRequest(time_in_force=TimeInForce.DAY),
        }
        if data.get('limit_price'):
            kwargs['limit_price'] = Decimal(str(data['limit_price']))
        order = OrderRequest(**kwargs)
        resp = client.place_order(order)
        client.close()
        return jsonify({"message": f"Order placed: {resp.order_id}", "order_id": resp.order_id})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/order/option', methods=['POST'])
def api_order_option():
    """Place option order via Public.com"""
    client = get_public_client()
    if not client:
        return jsonify({"error": "API not configured"})
    try:
        data = request.json
        kwargs = {
            "order_id": str(uuid.uuid4()),
            "instrument": OrderInstrument(symbol=data['symbol'], type=InstrumentType.OPTION),
            "order_side": OrderSide.BUY if data['side'] == 'BUY' else OrderSide.SELL,
            "order_type": OrderType.LIMIT,
            "quantity": data['quantity'],
            "limit_price": Decimal(str(data['limit_price'])),
            "expiration": OrderExpirationRequest(time_in_force=TimeInForce.DAY),
            "open_close_indicator": OpenCloseIndicator.OPEN if data.get('open_close') == 'OPEN' else OpenCloseIndicator.CLOSE,
        }
        order = OrderRequest(**kwargs)
        resp = client.place_order(order)
        client.close()
        return jsonify({"message": f"Order placed: {resp.order_id}", "order_id": resp.order_id})
    except Exception as e:
        return jsonify({"error": str(e)})

# =============================================================================
# BACKTESTER
# =============================================================================

@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    """Run a backtest"""
    try:
        params = request.json
        ticker = params['ticker']
        period = params.get('period', '1y')
        strategy = params.get('strategy', 'sma_cross')
        capital = params.get('capital', 10000)
        position_size = params.get('position_size', 1.0)
        
        # Get historical data
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty:
            return jsonify({"error": "No data available"})
        
        df = hist[['Close']].copy()
        df.columns = ['close']
        
        # Generate signals based on strategy
        if strategy in ('sma_cross', 'sma_crossover'):
            fast = params.get('fast', 10)
            slow = params.get('slow', 30)
            df['fast_sma'] = df['close'].rolling(fast).mean()
            df['slow_sma'] = df['close'].rolling(slow).mean()
            df['signal'] = 0
            df.loc[df['fast_sma'] > df['slow_sma'], 'signal'] = 1
            df.loc[df['fast_sma'] < df['slow_sma'], 'signal'] = -1
        elif strategy == 'rsi':
            period_rsi = params.get('rsi_period', 14)
            oversold = params.get('oversold', 30)
            overbought = params.get('overbought', 70)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period_rsi).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period_rsi).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            df['signal'] = 0
            df.loc[df['rsi'] < oversold, 'signal'] = 1
            df.loc[df['rsi'] > overbought, 'signal'] = -1
        elif strategy == 'breakout':
            bp = params.get('breakout_period', 20)
            df['high_n'] = df['close'].rolling(bp).max()
            df['low_n'] = df['close'].rolling(bp).min()
            df['signal'] = 0
            df.loc[df['close'] >= df['high_n'].shift(1), 'signal'] = 1
            df.loc[df['close'] <= df['low_n'].shift(1), 'signal'] = -1
        else:
            df['signal'] = 0
        
        df = df.dropna()
        
        # Simulate trades
        cash = capital
        position = 0
        entry_price = 0
        equity = []
        trades = []
        
        for i, (date, row) in enumerate(df.iterrows()):
            if row['signal'] == 1 and position == 0:
                # Buy
                shares = int((cash * position_size) / row['close'])
                if shares > 0:
                    cost = shares * row['close']
                    cash -= cost
                    position = shares
                    entry_price = row['close']
                    trades.append({"date": str(date.date()), "type": "BUY", "price": row['close'], "shares": shares, "pnl": 0})
            elif row['signal'] == -1 and position > 0:
                # Sell
                proceeds = position * row['close']
                pnl = proceeds - (position * entry_price)
                cash += proceeds
                trades.append({"date": str(date.date()), "type": "SELL", "price": row['close'], "shares": position, "pnl": pnl})
                position = 0
            
            # Track equity
            current_equity = cash + (position * row['close'])
            equity.append({"date": str(date.date()), "value": current_equity})
        
        # Close any open position
        if position > 0:
            final_price = df['close'].iloc[-1]
            proceeds = position * final_price
            pnl = proceeds - (position * entry_price)
            cash += proceeds
            trades.append({"date": str(df.index[-1].date()), "type": "SELL", "price": final_price, "shares": position, "pnl": pnl})
        
        # Calculate metrics
        final_equity = cash
        total_return = ((final_equity - capital) / capital) * 100
        
        equity_values = [e['value'] for e in equity]
        returns = np.diff(equity_values) / equity_values[:-1] if len(equity_values) > 1 else [0]
        sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0
        
        # Max drawdown
        peak = equity_values[0]
        max_dd = 0
        for v in equity_values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        # Win rate
        winning_trades = len([t for t in trades if t['type'] == 'SELL' and t['pnl'] > 0])
        total_trades = len([t for t in trades if t['type'] == 'SELL'])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Profit factor
        gross_profit = sum(t['pnl'] for t in trades if t['type'] == 'SELL' and t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['type'] == 'SELL' and t['pnl'] < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else gross_profit if gross_profit > 0 else 0
        
        return jsonify({
            "metrics": {
                "total_return": total_return,
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "win_rate": win_rate,
                "trades": total_trades,
                "profit_factor": profit_factor,
            },
            "equity": {
                "dates": [e['date'] for e in equity],
                "values": [e['value'] for e in equity],
            },
            "trades": trades,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)})

# =============================================================================
# PAPER TRADING
# =============================================================================

@app.route('/api/paper/portfolio')
def api_paper_portfolio():
    """Get paper trading portfolio"""
    portfolio = get_paper()
    # Calculate positions value
    positions_value = 0
    positions_list = []
    for sym, pos in portfolio.get('positions', {}).items():
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1d")
            price = float(hist['Close'].iloc[-1]) if not hist.empty else pos['avg_price']
            value = price * pos['quantity']
            pnl = (price - pos['avg_price']) * pos['quantity']
            positions_value += value
            positions_list.append({
                "symbol": sym,
                "quantity": pos['quantity'],
                "avg_price": pos['avg_price'],
                "current_price": price,
                "value": value,
                "gain_value": pnl,
                "gain_pct": (pnl / (pos['avg_price'] * pos['quantity'])) * 100 if pos['quantity'] > 0 else 0,
            })
        except:
            pass
    return jsonify({
        "cash": portfolio.get('cash', 10000),
        "starting": portfolio.get('starting', 10000),
        "positions": portfolio.get('positions', {}),
        "positions_list": positions_list,
        "positions_value": positions_value,
        "wins": portfolio.get('wins', 0),
        "losses": portfolio.get('losses', 0),
    })

@app.route('/api/paper/trades')
def api_paper_trades():
    """Get paper trading history"""
    return jsonify(get_trades())

@app.route('/api/paper/trade', methods=['POST'])
def api_paper_trade():
    """Execute paper trade"""
    try:
        data = request.json
        symbol = data['symbol'].upper()
        side = data['side']
        quantity = int(data['quantity'])
        
        # Get current price
        t = yf.Ticker(symbol)
        hist = t.history(period="1d")
        if hist.empty:
            return jsonify({"error": f"Cannot get price for {symbol}"})
        price = float(hist['Close'].iloc[-1])
        
        portfolio = get_paper()
        trades = get_trades()
        
        if side == 'BUY':
            cost = price * quantity
            if cost > portfolio['cash']:
                return jsonify({"error": f"Insufficient funds. Need ${cost:.2f}, have ${portfolio['cash']:.2f}"})
            portfolio['cash'] -= cost
            positions = portfolio.get('positions', {})
            if symbol in positions:
                # Average in
                old_qty = positions[symbol]['quantity']
                old_avg = positions[symbol]['avg_price']
                new_qty = old_qty + quantity
                new_avg = ((old_qty * old_avg) + (quantity * price)) / new_qty
                positions[symbol] = {'quantity': new_qty, 'avg_price': new_avg}
            else:
                positions[symbol] = {'quantity': quantity, 'avg_price': price}
            portfolio['positions'] = positions
            trades.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "symbol": symbol, "side": "BUY", "quantity": quantity, "price": price, "pnl": 0})
        else:  # SELL
            positions = portfolio.get('positions', {})
            if symbol not in positions or positions[symbol]['quantity'] < quantity:
                return jsonify({"error": f"Insufficient position in {symbol}"})
            avg_price = positions[symbol]['avg_price']
            pnl = (price - avg_price) * quantity
            portfolio['cash'] += price * quantity
            positions[symbol]['quantity'] -= quantity
            if positions[symbol]['quantity'] == 0:
                del positions[symbol]
            portfolio['positions'] = positions
            if pnl > 0:
                portfolio['wins'] = portfolio.get('wins', 0) + 1
            else:
                portfolio['losses'] = portfolio.get('losses', 0) + 1
            trades.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "symbol": symbol, "side": "SELL", "quantity": quantity, "price": price, "pnl": pnl})
        
        save_paper(portfolio)
        save_trades(trades)
        return jsonify({"message": f"{side} {quantity} {symbol} @ ${price:.2f}"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/paper/reset', methods=['POST'])
def api_paper_reset():
    """Reset paper portfolio"""
    save_paper({"cash": 10000.0, "starting": 10000.0, "positions": {}, "wins": 0, "losses": 0})
    save_trades([])
    return jsonify({"message": "Portfolio reset"})

# =============================================================================
# SCALPER GAME
# =============================================================================

@app.route('/api/scalper/scores')
def api_scalper_scores():
    """Get scalper high scores"""
    return jsonify(get_scores())

@app.route('/api/scalper/update', methods=['POST'])
def api_scalper_update():
    """Update scalper scores"""
    data = request.json
    scores = get_scores()
    if data.get('pnl', 0) > scores.get('high', 0):
        scores['high'] = data['pnl']
    scores['games'].append({
        "date": datetime.now().isoformat(),
        "pnl": data.get('pnl', 0),
        "trades": data.get('trades', 0),
        "wins": data.get('wins', 0),
    })
    scores['games'] = scores['games'][-100:]  # Keep last 100
    save_scores(scores)
    return jsonify({"message": "Scores updated"})

# =============================================================================
# STRATEGIES
# =============================================================================

@app.route('/api/strategies')
def api_strategies():
    """Get saved strategies"""
    return jsonify(get_strategies())

@app.route('/api/strategy/save', methods=['POST'])
def api_strategy_save():
    """Save a strategy"""
    data = request.json
    strategies = get_strategies()
    data['created'] = datetime.now().isoformat()
    strategies.append(data)
    save_strategies(strategies)
    return jsonify({"message": "Strategy saved"})

@app.route('/api/strategy/toggle/<int:idx>', methods=['POST'])
def api_strategy_toggle(idx):
    """Toggle strategy live status"""
    strategies = get_strategies()
    if 0 <= idx < len(strategies):
        strategies[idx]['live'] = not strategies[idx].get('live', False)
        save_strategies(strategies)
    return jsonify({"message": "Strategy toggled"})

@app.route('/api/strategy/delete/<int:idx>', methods=['POST'])
def api_strategy_delete(idx):
    """Delete a strategy"""
    strategies = get_strategies()
    if 0 <= idx < len(strategies):
        del strategies[idx]
        save_strategies(strategies)
    return jsonify({"message": "Strategy deleted"})

# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("Options Copilot — Public.com Trading Dashboard")
    print("="*60)
    print(f"Server: http://localhost:5006")
    print(f"API configured: {bool(get_api_secret() and get_account_id())}")
    print("="*60 + "\n")
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5006)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)