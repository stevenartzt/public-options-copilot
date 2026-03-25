/**
 * Options Copilot - Frontend Application
 * Public.com Competition Entry
 */

// State
let currentSection = 'dashboard';
let apiAvailable = false;
let currentTicker = null;
let spyGameInterval = null;

// API Helper
async function api(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        return { success: false, error: error.message };
    }
}

// Navigation
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const section = item.dataset.section;
        showSection(section);
    });
});

function showSection(section) {
    // Update nav
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.section === section);
    });
    
    // Update sections
    document.querySelectorAll('.section').forEach(s => {
        s.classList.toggle('active', s.id === section);
    });
    
    currentSection = section;
    
    // Load section data
    switch(section) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'portfolio':
            loadPortfolio();
            break;
        case 'scanner':
            // Ready for scan
            break;
        case 'paper':
            loadPaperPortfolio();
            break;
        case 'spy-game':
            startSpyGame();
            break;
        case 'settings':
            loadIndicatorConfig();
            break;
    }
}

// Tabs
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabId = tab.dataset.tab;
        const parent = tab.closest('.section');
        
        parent.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        parent.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        tab.classList.add('active');
        parent.querySelector(`#${tabId}`).classList.add('active');
    });
});

// Initialize
async function init() {
    const status = await api('/api/status');
    apiAvailable = status.api_available;
    
    const statusEl = document.getElementById('api-status');
    const dot = statusEl.querySelector('.status-dot');
    const text = statusEl.querySelector('.status-text');
    
    if (apiAvailable) {
        dot.classList.add('connected');
        text.textContent = 'API Connected';
    } else {
        dot.classList.add('disconnected');
        text.textContent = 'Paper Only';
    }
    
    loadDashboard();
}

// Dashboard
async function loadDashboard() {
    // Load sentiment
    const sentiment = await api('/api/sentiment');
    
    if (sentiment.success) {
        const data = sentiment.sentiment;
        
        // VIX
        document.getElementById('vix-value').textContent = data.vix.value;
        document.getElementById('vix-interpretation').textContent = data.vix.interpretation;
        
        // Overall sentiment
        const overallEl = document.getElementById('overall-sentiment');
        overallEl.textContent = data.overall_sentiment;
        overallEl.className = 'stat-value';
        
        // Breadth
        document.getElementById('breadth-info').textContent = 
            `${data.market_breadth.advancing} advancing / ${data.market_breadth.declining} declining`;
        
        // Sector grid
        const grid = document.getElementById('sector-grid');
        grid.innerHTML = data.sectors.map(sector => {
            const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
            const cls = (v) => v >= 0 ? 'positive' : 'negative';
            return `
            <div class="sector-card">
                <div class="icon">${sector.icon}</div>
                <div class="name">${sector.sector}</div>
                <div class="change ${cls(sector.change_pct)}">${fmt(sector.change_pct)}</div>
                <div class="change-detail">
                    <span class="${cls(sector.week_change_pct)}">W ${fmt(sector.week_change_pct)}</span>
                    <span class="${cls(sector.month_change_pct)}">M ${fmt(sector.month_change_pct)}</span>
                </div>
                <div class="sentiment ${sector.sentiment.toLowerCase()}">${sector.sentiment}</div>
            </div>`;
        }).join('');
    }
    
    // Load SPY
    const spy = await api('/api/quote/SPY');
    if (spy.success && spy.quote) {
        document.getElementById('spy-price').textContent = `$${spy.quote.price?.toFixed(2) || '--'}`;
        const change = spy.quote.change_percent || 0;
        const changeEl = document.getElementById('spy-change');
        changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
        changeEl.className = `stat-change ${change >= 0 ? 'positive' : 'negative'}`;
    }
}

// Portfolio
async function loadPortfolio() {
    if (apiAvailable) {
        const portfolio = await api('/api/portfolio');
        
        if (portfolio.success) {
            document.getElementById('no-api-message').style.display = 'none';
            document.getElementById('portfolio-data').style.display = 'block';
            
            const account = portfolio.account;
            document.getElementById('real-equity').textContent = `$${account.equity.toLocaleString()}`;
            document.getElementById('real-cash').textContent = `$${account.cash.toLocaleString()}`;
            document.getElementById('real-buying-power').textContent = `$${account.buying_power.toLocaleString()}`;
            
            // Positions table
            const tbody = document.querySelector('#real-positions-table tbody');
            tbody.innerHTML = portfolio.positions.map(pos => `
                <tr>
                    <td>${pos.symbol}</td>
                    <td>${pos.quantity}</td>
                    <td>$${pos.average_price.toFixed(2)}</td>
                    <td>$${pos.current_price.toFixed(2)}</td>
                    <td class="${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                        $${pos.unrealized_pl.toFixed(2)} (${pos.unrealized_pl_percent.toFixed(1)}%)
                    </td>
                    <td>
                        <button class="btn btn-danger btn-small" onclick="openOrderModal('${pos.symbol}', 'SELL', ${pos.current_price})">Sell</button>
                    </td>
                </tr>
            `).join('');
        }
    }
    
    // Also load paper portfolio in the second tab
    await loadPaperPortfolioTab();
}

async function loadPaperPortfolioTab() {
    const portfolio = await api('/api/paper/portfolio');
    
    if (portfolio.success) {
        const tab = document.getElementById('paper-portfolio');
        tab.innerHTML = `
            <div class="cards-row">
                <div class="card stat-card">
                    <div class="stat-label">Total Equity</div>
                    <div class="stat-value">$${portfolio.total_equity.toLocaleString()}</div>
                </div>
                <div class="card stat-card">
                    <div class="stat-label">Cash</div>
                    <div class="stat-value">$${portfolio.cash.toLocaleString()}</div>
                </div>
                <div class="card stat-card">
                    <div class="stat-label">Return</div>
                    <div class="stat-value ${portfolio.total_return >= 0 ? 'positive' : 'negative'}">
                        $${portfolio.total_return.toFixed(2)} (${portfolio.total_return_pct.toFixed(1)}%)
                    </div>
                </div>
            </div>
            <h3>Paper Positions</h3>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Qty</th>
                        <th>Avg Price</th>
                        <th>Current</th>
                        <th>P/L</th>
                    </tr>
                </thead>
                <tbody>
                    ${portfolio.positions.map(pos => `
                        <tr>
                            <td>${pos.symbol}</td>
                            <td>${pos.quantity}</td>
                            <td>$${pos.average_price.toFixed(2)}</td>
                            <td>$${pos.current_price.toFixed(2)}</td>
                            <td class="${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                                $${pos.unrealized_pl.toFixed(2)}
                            </td>
                        </tr>
                    `).join('') || '<tr><td colspan="5" style="text-align:center;">No positions</td></tr>'}
                </tbody>
            </table>
        `;
    }
}

// Paper Trading
async function loadPaperPortfolio() {
    const portfolio = await api('/api/paper/portfolio');
    
    if (portfolio.success) {
        document.getElementById('paper-equity').textContent = `$${portfolio.total_equity.toLocaleString()}`;
        document.getElementById('paper-cash').textContent = `$${portfolio.cash.toLocaleString()}`;
        document.getElementById('paper-return').textContent = 
            `$${portfolio.total_return.toFixed(2)} (${portfolio.total_return_pct.toFixed(1)}%)`;
        document.getElementById('paper-winrate').textContent = `${portfolio.stats.win_rate}%`;
        
        // Positions
        const tbody = document.querySelector('#paper-positions-table tbody');
        tbody.innerHTML = portfolio.positions.map(pos => `
            <tr>
                <td>${pos.symbol}</td>
                <td>${pos.quantity}</td>
                <td>$${pos.average_price.toFixed(2)}</td>
                <td>$${pos.current_price.toFixed(2)}</td>
                <td class="${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                    $${pos.unrealized_pl.toFixed(2)} (${pos.unrealized_pl_pct.toFixed(1)}%)
                </td>
                <td>
                    <button class="btn btn-danger" onclick="paperSell('${pos.symbol}', ${pos.quantity})">Sell All</button>
                </td>
            </tr>
        `).join('') || '<tr><td colspan="6" style="text-align:center;">No positions</td></tr>';
    }
    
    // Trade history
    const history = await api('/api/paper/history');
    if (history.success) {
        const tbody = document.querySelector('#paper-history-table tbody');
        tbody.innerHTML = history.trades.map(t => `
            <tr>
                <td>${new Date(t.timestamp).toLocaleString()}</td>
                <td>${t.symbol}</td>
                <td class="${t.trade_type === 'BUY' ? 'positive' : 'negative'}">${t.trade_type}</td>
                <td>${t.quantity}</td>
                <td>$${t.price.toFixed(2)}</td>
                <td>$${t.total_value.toFixed(2)}</td>
            </tr>
        `).join('') || '<tr><td colspan="6" style="text-align:center;">No trades yet</td></tr>';
    }
}

// Paper buy/sell
document.getElementById('paper-buy-btn').addEventListener('click', async () => {
    const symbol = document.getElementById('paper-symbol').value.toUpperCase();
    const qty = parseInt(document.getElementById('paper-qty').value);
    const price = parseFloat(document.getElementById('paper-price').value) || null;
    
    if (!symbol || !qty) {
        alert('Enter symbol and quantity');
        return;
    }
    
    const result = await api('/api/paper/buy', {
        method: 'POST',
        body: JSON.stringify({ symbol, quantity: qty, price })
    });
    
    alert(result.message || result.error);
    if (result.success) {
        document.getElementById('paper-symbol').value = '';
        document.getElementById('paper-qty').value = '';
        document.getElementById('paper-price').value = '';
        loadPaperPortfolio();
    }
});

document.getElementById('paper-sell-btn').addEventListener('click', async () => {
    const symbol = document.getElementById('paper-symbol').value.toUpperCase();
    const qty = parseInt(document.getElementById('paper-qty').value);
    const price = parseFloat(document.getElementById('paper-price').value) || null;
    
    if (!symbol || !qty) {
        alert('Enter symbol and quantity');
        return;
    }
    
    const result = await api('/api/paper/sell', {
        method: 'POST',
        body: JSON.stringify({ symbol, quantity: qty, price })
    });
    
    alert(result.message || result.error);
    if (result.success) {
        document.getElementById('paper-symbol').value = '';
        document.getElementById('paper-qty').value = '';
        document.getElementById('paper-price').value = '';
        loadPaperPortfolio();
    }
});

async function paperSell(symbol, qty) {
    const result = await api('/api/paper/sell', {
        method: 'POST',
        body: JSON.stringify({ symbol, quantity: qty })
    });
    alert(result.message || result.error);
    loadPaperPortfolio();
}

document.getElementById('paper-reset-btn').addEventListener('click', async () => {
    if (confirm('Reset paper portfolio? This cannot be undone.')) {
        await api('/api/paper/reset', { method: 'POST' });
        loadPaperPortfolio();
    }
});

// Trading - Ticker Analysis
document.getElementById('search-btn').addEventListener('click', analyzeTicker);
document.getElementById('ticker-search').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') analyzeTicker();
});

async function analyzeTicker() {
    const symbol = document.getElementById('ticker-search').value.toUpperCase();
    if (!symbol) return;
    
    currentTicker = symbol;
    
    // Get analysis
    const analysis = await api(`/api/analysis/${symbol}`);
    if (!analysis.success) {
        alert(analysis.error || 'Could not analyze ticker');
        return;
    }
    
    const data = analysis.analysis;
    document.getElementById('ticker-analysis').style.display = 'block';
    
    document.getElementById('ticker-symbol').textContent = symbol;
    document.getElementById('ticker-price').textContent = `$${data.price.toFixed(2)}`;
    
    const trendBadge = document.getElementById('trend-badge');
    trendBadge.textContent = data.trend;
    trendBadge.className = `trend-badge ${data.trend.toLowerCase()}`;
    
    document.getElementById('trend-strength').textContent = data.trend_strength.toFixed(0);
    document.getElementById('ticker-rsi').textContent = data.rsi.toFixed(1);
    document.getElementById('ticker-iv').textContent = data.iv_rank.toFixed(1);
    document.getElementById('ticker-regime').textContent = data.regime;
    
    // Load chart
    await loadChart(symbol);
    
    // Load option expirations
    await loadExpirations(symbol);
}

async function loadChart(symbol) {
    const chart = await api(`/api/chart/${symbol}`);
    if (!chart.success) return;
    
    const data = chart.data;
    const indicators = chart.indicators;
    
    const traces = [{
        x: data.dates,
        close: data.close,
        high: data.high,
        low: data.low,
        open: data.open,
        type: 'candlestick',
        name: symbol
    }];
    
    // Add indicators
    if (indicators.sma_20) {
        traces.push({
            x: data.dates,
            y: indicators.sma_20,
            type: 'scatter',
            mode: 'lines',
            name: 'SMA 20',
            line: { color: '#f59e0b', width: 1 }
        });
    }
    
    if (indicators.sma_50) {
        traces.push({
            x: data.dates,
            y: indicators.sma_50,
            type: 'scatter',
            mode: 'lines',
            name: 'SMA 50',
            line: { color: '#6366f1', width: 1 }
        });
    }
    
    if (indicators.bollinger_upper) {
        traces.push({
            x: data.dates,
            y: indicators.bollinger_upper,
            type: 'scatter',
            mode: 'lines',
            name: 'BB Upper',
            line: { color: '#10b981', width: 1, dash: 'dot' }
        });
        traces.push({
            x: data.dates,
            y: indicators.bollinger_lower,
            type: 'scatter',
            mode: 'lines',
            name: 'BB Lower',
            line: { color: '#10b981', width: 1, dash: 'dot' }
        });
    }
    
    const layout = {
        title: `${symbol} Price Chart`,
        xaxis: { rangeslider: { visible: false } },
        yaxis: { title: 'Price' },
        paper_bgcolor: '#16161f',
        plot_bgcolor: '#16161f',
        font: { color: '#a0a0b0' }
    };
    
    Plotly.newPlot('price-chart', traces, layout);
}

async function loadExpirations(symbol) {
    const result = await api(`/api/options/${symbol}/expirations`);
    
    const select = document.getElementById('expiration-select');
    select.innerHTML = '<option value="">Select Expiration</option>';
    
    if (result.success && result.expirations) {
        result.expirations.forEach(exp => {
            select.innerHTML += `<option value="${exp}">${exp}</option>`;
        });
    }
}

document.getElementById('expiration-select').addEventListener('change', async (e) => {
    const exp = e.target.value;
    if (!exp || !currentTicker) return;
    
    const chain = await api(`/api/options/${currentTicker}/chain?expiration=${exp}`);
    if (!chain.success) return;
    
    // Calls table
    const callsTbody = document.querySelector('#calls-table tbody');
    callsTbody.innerHTML = chain.calls.map(opt => `
        <tr>
            <td>$${opt.strike.toFixed(2)}</td>
            <td>${opt.bid?.toFixed(2) || '--'}</td>
            <td>${opt.ask?.toFixed(2) || '--'}</td>
            <td>${opt.volume || 0}</td>
            <td>${opt.open_interest || 0}</td>
            <td><button class="btn btn-primary btn-small" onclick="openOrderModal('${opt.symbol || currentTicker + exp + 'C' + opt.strike}', 'BUY', ${(opt.bid + opt.ask) / 2 || opt.last})">Trade</button></td>
        </tr>
    `).join('');
    
    // Puts table
    const putsTbody = document.querySelector('#puts-table tbody');
    putsTbody.innerHTML = chain.puts.map(opt => `
        <tr>
            <td>$${opt.strike.toFixed(2)}</td>
            <td>${opt.bid?.toFixed(2) || '--'}</td>
            <td>${opt.ask?.toFixed(2) || '--'}</td>
            <td>${opt.volume || 0}</td>
            <td>${opt.open_interest || 0}</td>
            <td><button class="btn btn-primary btn-small" onclick="openOrderModal('${opt.symbol || currentTicker + exp + 'P' + opt.strike}', 'BUY', ${(opt.bid + opt.ask) / 2 || opt.last})">Trade</button></td>
        </tr>
    `).join('');
});

// Scanner
document.getElementById('scan-btn').addEventListener('click', async () => {
    const preset = document.getElementById('preset-select').value;
    const minVolume = parseInt(document.getElementById('min-volume').value);
    const minOi = parseInt(document.getElementById('min-oi').value);
    const maxDte = parseInt(document.getElementById('max-dte').value);
    const limit = parseInt(document.getElementById('scan-limit').value);
    
    document.getElementById('scan-results').innerHTML = '<div class="loading">Scanning...</div>';
    
    // Use preset
    await api(`/api/scanner/preset/${preset}`, { method: 'POST' });
    
    // Scan
    const result = await api('/api/scanner/scan', {
        method: 'POST',
        body: JSON.stringify({ min_volume: minVolume, min_oi: minOi, max_dte: maxDte, limit })
    });
    
    if (!result.success || !result.results.length) {
        document.getElementById('scan-results').innerHTML = '<p class="placeholder-text">No options found matching criteria</p>';
        return;
    }
    
    document.getElementById('scan-results').innerHTML = result.results.map(opt => `
        <div class="scan-result-card">
            <div class="header">
                <span class="symbol">${opt.underlying} ${opt.option_type.toUpperCase()} $${opt.strike} ${opt.expiration}</span>
                <span class="signal ${opt.signal.toLowerCase().replace('_', '-')}">${opt.signal}</span>
            </div>
            <div class="details">
                <div class="detail-item">Bid/Ask: <strong>$${opt.bid.toFixed(2)} / $${opt.ask.toFixed(2)}</strong></div>
                <div class="detail-item">Volume: <strong>${opt.volume}</strong></div>
                <div class="detail-item">OI: <strong>${opt.open_interest}</strong></div>
                <div class="detail-item">DTE: <strong>${opt.days_to_expiry}</strong></div>
                <div class="detail-item">Score: <strong>${opt.score}</strong></div>
                <div class="detail-item">Win Prob: <strong>${opt.win_probability}%</strong></div>
                <div class="detail-item">IV Rank: <strong>${opt.iv_rank}%</strong></div>
                <div class="detail-item">R/R: <strong>${opt.risk_reward}:1</strong></div>
            </div>
            <div class="reasons">${opt.reasons.join(' • ')}</div>
            <button class="btn btn-primary" style="margin-top: 12px;" onclick="openOrderModal('${opt.symbol}', 'BUY', ${opt.mid})">Trade</button>
        </div>
    `).join('');
});

// SPY Scalper Game
function startSpyGame() {
    if (spyGameInterval) clearInterval(spyGameInterval);
    updateSpyGame();
    spyGameInterval = setInterval(updateSpyGame, 3000);
}

async function updateSpyGame() {
    const game = await api('/api/game/spy');
    if (!game.success) return;
    
    document.getElementById('game-spy-price').textContent = `$${game.spy_price?.toFixed(2) || '--'}`;
    document.getElementById('game-position').textContent = game.position ? 
        `${game.position.side.toUpperCase()} @ $${game.position.entry.toFixed(2)}` : 'None';
    
    const pnlEl = document.getElementById('game-current-pnl');
    pnlEl.textContent = `$${game.current_pnl.toFixed(2)}`;
    pnlEl.style.color = game.current_pnl >= 0 ? '#10b981' : '#ef4444';
    
    const sessionEl = document.getElementById('game-session-pnl');
    sessionEl.textContent = `$${game.session_pnl.toFixed(2)}`;
    sessionEl.style.color = game.session_pnl >= 0 ? '#10b981' : '#ef4444';
    
    document.getElementById('game-trades').textContent = game.trades;
    document.getElementById('game-high-score').textContent = `$${game.high_score.toFixed(2)}`;
}

document.getElementById('game-buy-btn').addEventListener('click', async () => {
    const result = await api('/api/game/spy/buy', { method: 'POST' });
    alert(result.message || result.error);
    updateSpyGame();
});

document.getElementById('game-sell-btn').addEventListener('click', async () => {
    const result = await api('/api/game/spy/sell', { method: 'POST' });
    alert(result.message || result.error);
    updateSpyGame();
});

document.getElementById('game-reset-btn').addEventListener('click', async () => {
    await api('/api/game/spy/reset', { method: 'POST' });
    updateSpyGame();
});

// Settings - Indicator toggles
async function loadIndicatorConfig() {
    const config = await api('/api/indicators/config');
    if (!config.success) return;
    
    const container = document.getElementById('indicator-toggles');
    container.innerHTML = Object.entries(config.config).map(([key, cfg]) => `
        <label class="indicator-toggle">
            <input type="checkbox" ${cfg.enabled ? 'checked' : ''} data-indicator="${key}">
            ${cfg.name}
        </label>
    `).join('');
    
    container.querySelectorAll('input').forEach(input => {
        input.addEventListener('change', async () => {
            await api('/api/indicators/toggle', {
                method: 'POST',
                body: JSON.stringify({
                    indicator: input.dataset.indicator,
                    enabled: input.checked
                })
            });
        });
    });
}

// Order Modal
const modal = document.getElementById('order-modal');
const closeBtn = modal.querySelector('.close-btn');

closeBtn.addEventListener('click', () => modal.classList.remove('active'));
modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('active');
});

function openOrderModal(symbol, side, price) {
    document.getElementById('order-symbol').value = symbol;
    document.getElementById('order-side').value = side;
    document.getElementById('order-price').value = price?.toFixed(2) || '';
    document.getElementById('order-account').value = apiAvailable ? 'real' : 'paper';
    document.getElementById('preflight-info').innerHTML = '';
    modal.classList.add('active');
}

document.getElementById('preview-btn').addEventListener('click', async () => {
    const symbol = document.getElementById('order-symbol').value;
    const side = document.getElementById('order-side').value;
    const quantity = parseInt(document.getElementById('order-quantity').value);
    const price = parseFloat(document.getElementById('order-price').value);
    const account = document.getElementById('order-account').value;
    
    if (account === 'paper') {
        const total = price * quantity * 100; // Options are 100 shares
        document.getElementById('preflight-info').innerHTML = 
            `<strong>Paper Order Preview</strong><br>Total: $${total.toFixed(2)}`;
        return;
    }
    
    const result = await api('/api/order/preflight', {
        method: 'POST',
        body: JSON.stringify({ symbol, side, quantity, limit_price: price })
    });
    
    if (result.success) {
        const pf = result.preflight;
        document.getElementById('preflight-info').innerHTML = `
            <strong>Order Preview</strong><br>
            Order Value: $${pf.order_value.toFixed(2)}<br>
            Commission: $${pf.estimated_commission.toFixed(2)}<br>
            Total Cost: $${pf.estimated_cost.toFixed(2)}<br>
            Buying Power Required: $${pf.buying_power_requirement.toFixed(2)}
        `;
    } else {
        document.getElementById('preflight-info').innerHTML = `Error: ${result.error}`;
    }
});

document.getElementById('order-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const symbol = document.getElementById('order-symbol').value;
    const side = document.getElementById('order-side').value;
    const quantity = parseInt(document.getElementById('order-quantity').value);
    const price = parseFloat(document.getElementById('order-price').value);
    const account = document.getElementById('order-account').value;
    
    let result;
    if (account === 'paper') {
        const endpoint = side === 'BUY' ? '/api/paper/buy' : '/api/paper/sell';
        result = await api(endpoint, {
            method: 'POST',
            body: JSON.stringify({ symbol, quantity, price, asset_type: 'OPTION' })
        });
    } else {
        result = await api('/api/order/place', {
            method: 'POST',
            body: JSON.stringify({ symbol, side, quantity, limit_price: price })
        });
    }
    
    alert(result.message || result.error);
    if (result.success) {
        modal.classList.remove('active');
        if (account === 'paper') loadPaperPortfolio();
    }
});

// Start app
init();
