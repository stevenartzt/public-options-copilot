/**
 * Options Copilot - Frontend Application
 * Public.com Competition Entry
 */

// State
let currentSection = 'dashboard';
let apiAvailable = false;
let currentTicker = null;
let spyGameInterval = null;
let conditionTypes = { entry_conditions: [], exit_conditions: [] };

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

// Toast notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
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
        case 'algo':
            loadAlgoSection();
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
        
        // Load tab-specific data
        if (tabId === 'strategies') {
            loadStrategiesList();
        } else if (tabId === 'backtester') {
            loadBacktestStrategies();
        }
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
    
    // Load condition types for algo trading
    const conditions = await api('/api/algo/conditions');
    if (conditions.success) {
        conditionTypes = conditions.conditions;
    }
    
    loadDashboard();
    setupModalListeners();
}

// Modal close on ESC and outside click
function setupModalListeners() {
    // ESC key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.active').forEach(modal => {
                modal.classList.remove('active');
            });
            if (spyGameInterval && currentSection !== 'spy-game') {
                clearInterval(spyGameInterval);
            }
        }
    });
    
    // Click outside modal
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
    
    // Close buttons
    document.querySelectorAll('.close-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').classList.remove('active');
        });
    });
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
        window._sectorData = data.sectors;
        grid.innerHTML = data.sectors.map((sector, i) => {
            const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
            const cls = (v) => v >= 0 ? 'positive' : 'negative';
            return `
            <div class="sector-card" onclick="showSectorDetail(${i})">
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
            
            // Calculate total positions value
            const totalValue = portfolio.positions.reduce((sum, pos) => sum + (pos.current_price * pos.quantity), 0);
            
            // Positions table with clickable rows
            const tbody = document.querySelector('#real-positions-table tbody');
            tbody.innerHTML = portfolio.positions.map(pos => {
                const positionPct = totalValue > 0 ? ((pos.current_price * pos.quantity) / account.equity * 100).toFixed(1) : 0;
                return `
                <tr class="clickable" onclick="showAnalysisModal('${pos.symbol}')">
                    <td>
                        ${pos.symbol}
                        <div class="position-size">${positionPct}% of portfolio</div>
                    </td>
                    <td>${pos.quantity}</td>
                    <td>$${pos.average_price.toFixed(2)}</td>
                    <td>$${pos.current_price.toFixed(2)}</td>
                    <td class="${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                        $${pos.unrealized_pl.toFixed(2)} (${pos.unrealized_pl_percent.toFixed(1)}%)
                    </td>
                    <td>
                        <button class="btn btn-danger btn-small" onclick="event.stopPropagation(); openOrderModal('${pos.symbol}', 'SELL', ${pos.current_price})">Sell</button>
                    </td>
                </tr>
            `}).join('');
        }
    }
    
    // Also load paper portfolio in the second tab
    await loadPaperPortfolioTab();
}

async function loadPaperPortfolioTab() {
    const portfolio = await api('/api/paper/portfolio');
    
    if (portfolio.success) {
        const totalValue = portfolio.positions.reduce((sum, pos) => sum + pos.market_value, 0);
        
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
                    ${portfolio.positions.map(pos => {
                        const positionPct = portfolio.total_equity > 0 ? (pos.market_value / portfolio.total_equity * 100).toFixed(1) : 0;
                        return `
                        <tr class="clickable" onclick="showAnalysisModal('${pos.symbol}')">
                            <td>
                                ${pos.symbol}
                                <div class="position-size">${positionPct}% of portfolio</div>
                            </td>
                            <td>${pos.quantity}</td>
                            <td>$${pos.average_price.toFixed(2)}</td>
                            <td>$${pos.current_price.toFixed(2)}</td>
                            <td class="${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                                $${pos.unrealized_pl.toFixed(2)}
                            </td>
                        </tr>
                    `}).join('') || '<tr><td colspan="5" style="text-align:center;">No positions</td></tr>'}
                </tbody>
            </table>
        `;
    }
}

// Position Analysis Modal
async function showAnalysisModal(symbol) {
    const modal = document.getElementById('analysis-modal');
    const loading = document.getElementById('analysis-loading');
    const content = document.getElementById('analysis-content');
    
    document.getElementById('analysis-modal-title').textContent = `${symbol} Analysis`;
    loading.style.display = 'block';
    content.style.display = 'none';
    modal.classList.add('active');
    
    const result = await api(`/api/analysis/full/${symbol}`);
    
    if (result.success) {
        const analysis = result.analysis;
        
        document.getElementById('modal-price').textContent = `$${analysis.price.toFixed(2)}`;
        
        const trendEl = document.getElementById('modal-trend');
        trendEl.textContent = analysis.trend;
        trendEl.className = `trend-badge ${analysis.trend.toLowerCase()}`;
        document.getElementById('modal-trend-strength').textContent = `${analysis.trend_strength.toFixed(0)}% strength`;
        
        const recEl = document.getElementById('modal-recommendation');
        recEl.textContent = result.recommendation;
        recEl.className = `trend-badge ${result.recommendation_class}`;
        
        document.getElementById('modal-rsi').textContent = analysis.rsi.toFixed(1);
        document.getElementById('modal-macd').textContent = analysis.macd_histogram.toFixed(4);
        document.getElementById('modal-atr').textContent = analysis.atr_pct.toFixed(2) + '%';
        document.getElementById('modal-adx').textContent = analysis.adx.toFixed(1);
        document.getElementById('modal-bb').textContent = analysis.bollinger_width.toFixed(2);
        
        const regimeEl = document.getElementById('modal-regime');
        regimeEl.textContent = analysis.regime;
        regimeEl.className = `regime-badge ${analysis.regime.toLowerCase()}`;
        
        document.getElementById('modal-support').textContent = `$${analysis.support.toFixed(2)}`;
        document.getElementById('modal-resistance').textContent = `$${analysis.resistance.toFixed(2)}`;
        document.getElementById('modal-sma20').textContent = `$${analysis.sma_20.toFixed(2)}`;
        document.getElementById('modal-sma50').textContent = `$${analysis.sma_50.toFixed(2)}`;
        
        const reasonsList = document.getElementById('modal-reasons');
        reasonsList.innerHTML = analysis.reasons.map(r => `<li>${r}</li>`).join('');
        
        // Mini chart
        if (result.chart_data) {
            const chartData = result.chart_data;
            Plotly.newPlot('modal-mini-chart', [{
                x: chartData.dates,
                y: chartData.close,
                type: 'scatter',
                mode: 'lines',
                fill: 'tozeroy',
                line: { color: '#6366f1', width: 2 },
                fillcolor: 'rgba(99, 102, 241, 0.1)'
            }], {
                margin: { t: 10, r: 20, b: 30, l: 50 },
                paper_bgcolor: '#16161f',
                plot_bgcolor: '#16161f',
                font: { color: '#a0a0b0' },
                xaxis: { showgrid: false },
                yaxis: { showgrid: true, gridcolor: '#2a2a3a' }
            }, { responsive: true, displayModeBar: false });
        }
        
        loading.style.display = 'none';
        content.style.display = 'block';
    } else {
        loading.textContent = result.error || 'Failed to load analysis';
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
        
        // Positions with position size
        const tbody = document.querySelector('#paper-positions-table tbody');
        tbody.innerHTML = portfolio.positions.map(pos => {
            const positionPct = portfolio.total_equity > 0 ? (pos.market_value / portfolio.total_equity * 100).toFixed(1) : 0;
            return `
            <tr class="clickable" onclick="showAnalysisModal('${pos.symbol}')">
                <td>
                    ${pos.symbol}
                    <div class="position-size">${positionPct}% of portfolio</div>
                </td>
                <td>${pos.quantity}</td>
                <td>$${pos.average_price.toFixed(2)}</td>
                <td>$${pos.current_price.toFixed(2)}</td>
                <td class="${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                    $${pos.unrealized_pl.toFixed(2)} (${pos.unrealized_pl_pct.toFixed(1)}%)
                </td>
                <td>
                    <button class="btn btn-danger btn-small" onclick="event.stopPropagation(); paperSell('${pos.symbol}', ${pos.quantity})">Sell All</button>
                </td>
            </tr>
        `}).join('') || '<tr><td colspan="6" style="text-align:center;">No positions</td></tr>';
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
        showToast('Enter symbol and quantity', 'error');
        return;
    }
    
    const result = await api('/api/paper/buy', {
        method: 'POST',
        body: JSON.stringify({ symbol, quantity: qty, price })
    });
    
    if (result.success) {
        showToast(result.message, 'success');
        document.getElementById('paper-symbol').value = '';
        document.getElementById('paper-qty').value = '';
        document.getElementById('paper-price').value = '';
        loadPaperPortfolio();
    } else {
        showToast(result.error, 'error');
    }
});

document.getElementById('paper-sell-btn').addEventListener('click', async () => {
    const symbol = document.getElementById('paper-symbol').value.toUpperCase();
    const qty = parseInt(document.getElementById('paper-qty').value);
    const price = parseFloat(document.getElementById('paper-price').value) || null;
    
    if (!symbol || !qty) {
        showToast('Enter symbol and quantity', 'error');
        return;
    }
    
    const result = await api('/api/paper/sell', {
        method: 'POST',
        body: JSON.stringify({ symbol, quantity: qty, price })
    });
    
    if (result.success) {
        showToast(result.message, 'success');
        document.getElementById('paper-symbol').value = '';
        document.getElementById('paper-qty').value = '';
        document.getElementById('paper-price').value = '';
        loadPaperPortfolio();
    } else {
        showToast(result.error, 'error');
    }
});

async function paperSell(symbol, qty) {
    const result = await api('/api/paper/sell', {
        method: 'POST',
        body: JSON.stringify({ symbol, quantity: qty })
    });
    if (result.success) {
        showToast(result.message, 'success');
    } else {
        showToast(result.error, 'error');
    }
    loadPaperPortfolio();
}

document.getElementById('paper-reset-btn').addEventListener('click', async () => {
    if (confirm('Reset paper portfolio? This cannot be undone.')) {
        await api('/api/paper/reset', { method: 'POST' });
        showToast('Portfolio reset', 'info');
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
        showToast(analysis.error || 'Could not analyze ticker', 'error');
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

// ================== Algo Trading ==================

async function loadAlgoSection() {
    await populateConditionDropdowns();
    await loadStrategiesList();
    await loadBacktestStrategies();
}

function populateConditionDropdowns() {
    // Populate entry condition dropdowns
    document.querySelectorAll('#entry-conditions .condition-type').forEach(select => {
        populateConditionSelect(select, 'entry');
    });
    
    // Populate exit condition dropdowns
    document.querySelectorAll('#exit-conditions .condition-type').forEach(select => {
        populateConditionSelect(select, 'exit');
    });
}

function populateConditionSelect(select, group) {
    const conditions = group === 'entry' ? conditionTypes.entry_conditions : conditionTypes.exit_conditions;
    select.innerHTML = '<option value="">Select condition...</option>';
    conditions.forEach(c => {
        select.innerHTML += `<option value="${c.value}" data-needs-value="${c.needs_value}" data-default="${c.default || ''}">${c.label}</option>`;
    });
    
    // Handle value input visibility
    select.addEventListener('change', () => {
        const option = select.options[select.selectedIndex];
        const valueInput = select.parentElement.querySelector('.condition-value');
        if (option.dataset.needsValue === 'true') {
            valueInput.style.display = 'block';
            valueInput.value = option.dataset.default || '';
        } else {
            valueInput.style.display = 'none';
            valueInput.value = '';
        }
    });
}

// Add condition button
document.querySelectorAll('.add-condition').forEach(btn => {
    btn.addEventListener('click', () => {
        const group = btn.dataset.group;
        const container = document.getElementById(`${group}-conditions`);
        
        const row = document.createElement('div');
        row.className = 'condition-row';
        row.innerHTML = `
            <select class="select-input condition-type" data-group="${group}">
                <option value="">Select condition...</option>
            </select>
            <input type="number" class="num-input condition-value" placeholder="Value" style="display:none;">
            <button class="btn btn-danger btn-small remove-condition">✕</button>
        `;
        container.appendChild(row);
        
        const select = row.querySelector('.condition-type');
        populateConditionSelect(select, group);
        
        row.querySelector('.remove-condition').addEventListener('click', () => row.remove());
    });
});

// Remove condition buttons
document.querySelectorAll('.remove-condition').forEach(btn => {
    btn.addEventListener('click', () => {
        const row = btn.closest('.condition-row');
        const container = row.parentElement;
        if (container.querySelectorAll('.condition-row').length > 1) {
            row.remove();
        }
    });
});

// Create strategy
document.getElementById('create-strategy-btn').addEventListener('click', async () => {
    const name = document.getElementById('strat-name').value.trim();
    const symbolsStr = document.getElementById('strat-symbols').value.trim();
    const symbols = symbolsStr.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
    
    if (!name) {
        showToast('Enter strategy name', 'error');
        return;
    }
    if (symbols.length === 0) {
        showToast('Enter at least one symbol', 'error');
        return;
    }
    
    // Collect entry conditions
    const entryConditions = [];
    document.querySelectorAll('#entry-conditions .condition-row').forEach(row => {
        const type = row.querySelector('.condition-type').value;
        const value = parseFloat(row.querySelector('.condition-value').value) || null;
        if (type) {
            entryConditions.push({ type, value });
        }
    });
    
    // Collect exit conditions
    const exitConditions = [];
    document.querySelectorAll('#exit-conditions .condition-row').forEach(row => {
        const type = row.querySelector('.condition-type').value;
        const value = parseFloat(row.querySelector('.condition-value').value) || null;
        if (type) {
            exitConditions.push({ type, value });
        }
    });
    
    if (entryConditions.length === 0) {
        showToast('Add at least one entry condition', 'error');
        return;
    }
    if (exitConditions.length === 0) {
        showToast('Add at least one exit condition', 'error');
        return;
    }
    
    const result = await api('/api/algo/strategy', {
        method: 'POST',
        body: JSON.stringify({
            name,
            symbols,
            entry_conditions: entryConditions,
            exit_conditions: exitConditions,
            position_size_pct: parseFloat(document.getElementById('strat-pos-size').value) || 10,
            max_positions: parseInt(document.getElementById('strat-max-pos').value) || 5,
            stop_loss_pct: parseFloat(document.getElementById('strat-stop-loss').value) || null,
            take_profit_pct: parseFloat(document.getElementById('strat-take-profit').value) || null
        })
    });
    
    if (result.success) {
        showToast(`Strategy "${name}" created!`, 'success');
        document.getElementById('strat-name').value = '';
        document.getElementById('strat-symbols').value = '';
        loadStrategiesList();
        loadBacktestStrategies();
    } else {
        showToast(result.error, 'error');
    }
});

async function loadStrategiesList() {
    const result = await api('/api/algo/strategies');
    const container = document.getElementById('strategies-list');
    
    if (!result.success || result.strategies.length === 0) {
        container.innerHTML = '<p class="placeholder-text">No strategies yet. Create one in Strategy Builder.</p>';
        return;
    }
    
    container.innerHTML = result.strategies.map(strat => `
        <div class="strategy-card" data-id="${strat.id}">
            <div class="header">
                <span class="name">${strat.name}</span>
                <div class="status">
                    <div class="toggle-group">
                        <span>Enabled</span>
                        <label class="toggle-switch">
                            <input type="checkbox" ${strat.enabled ? 'checked' : ''} onchange="toggleStrategy('${strat.id}', 'enabled', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="toggle-group">
                        <span>Live</span>
                        <label class="toggle-switch">
                            <input type="checkbox" ${strat.is_live ? 'checked' : ''} onchange="toggleStrategy('${strat.id}', 'is_live', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                </div>
            </div>
            ${strat.is_live ? '<div class="live-warning">⚠️ LIVE MODE: This strategy will place REAL orders when enabled!</div>' : ''}
            <div class="details">
                <div>Symbols: <strong>${strat.symbols.join(', ')}</strong></div>
                <div>Position Size: <strong>${strat.position_size_pct}%</strong></div>
                <div>Max Positions: <strong>${strat.max_positions}</strong></div>
                <div>Stop Loss: <strong>${strat.stop_loss_pct ? strat.stop_loss_pct + '%' : 'None'}</strong></div>
                <div>Take Profit: <strong>${strat.take_profit_pct ? strat.take_profit_pct + '%' : 'None'}</strong></div>
                <div>Created: <strong>${new Date(strat.created_at).toLocaleDateString()}</strong></div>
            </div>
            <div class="actions">
                <button class="btn btn-primary btn-small" onclick="runBacktestForStrategy('${strat.id}')">Backtest</button>
                <button class="btn btn-danger btn-small" onclick="deleteStrategy('${strat.id}')">Delete</button>
            </div>
        </div>
    `).join('');
}

async function toggleStrategy(id, field, value) {
    const data = {};
    data[field] = value;
    
    const result = await api(`/api/algo/toggle/${id}`, {
        method: 'POST',
        body: JSON.stringify(data)
    });
    
    if (result.success) {
        if (field === 'is_live' && value) {
            showToast('⚠️ Live mode enabled! Real orders will be placed.', 'error');
        } else {
            showToast('Strategy updated', 'success');
        }
        loadStrategiesList();
    } else {
        showToast(result.error, 'error');
    }
}

async function deleteStrategy(id) {
    if (!confirm('Delete this strategy?')) return;
    
    const result = await api(`/api/algo/strategy/${id}`, { method: 'DELETE' });
    
    if (result.success) {
        showToast('Strategy deleted', 'success');
        loadStrategiesList();
        loadBacktestStrategies();
    } else {
        showToast(result.error, 'error');
    }
}

async function loadBacktestStrategies() {
    const result = await api('/api/algo/strategies');
    const select = document.getElementById('backtest-strategy');
    
    select.innerHTML = '<option value="">Select a strategy...</option>';
    
    if (result.success) {
        result.strategies.forEach(strat => {
            select.innerHTML += `<option value="${strat.id}">${strat.name}</option>`;
        });
    }
}

async function runBacktestForStrategy(id) {
    // Switch to backtester tab
    document.querySelector('[data-tab="backtester"]').click();
    document.getElementById('backtest-strategy').value = id;
    document.getElementById('run-backtest-btn').click();
}

document.getElementById('run-backtest-btn').addEventListener('click', async () => {
    const strategyId = document.getElementById('backtest-strategy').value;
    const period = document.getElementById('backtest-period').value;
    const capital = parseFloat(document.getElementById('backtest-capital').value) || 10000;
    
    if (!strategyId) {
        showToast('Select a strategy', 'error');
        return;
    }
    
    document.getElementById('backtest-results').style.display = 'none';
    showToast('Running backtest...', 'info');
    
    const result = await api('/api/algo/backtest', {
        method: 'POST',
        body: JSON.stringify({
            strategy_id: strategyId,
            period,
            initial_capital: capital
        })
    });
    
    if (!result.success) {
        showToast(result.error || 'Backtest failed', 'error');
        return;
    }
    
    const bt = result.result;
    document.getElementById('backtest-results').style.display = 'block';
    
    // Update stats
    document.getElementById('bt-return').textContent = `$${bt.total_return.toLocaleString()}`;
    document.getElementById('bt-return-pct').textContent = `${bt.total_return_pct >= 0 ? '+' : ''}${bt.total_return_pct.toFixed(2)}%`;
    document.getElementById('bt-return-pct').className = `stat-change ${bt.total_return >= 0 ? 'positive' : 'negative'}`;
    document.getElementById('bt-winrate').textContent = `${bt.win_rate.toFixed(1)}%`;
    document.getElementById('bt-profit-factor').textContent = bt.profit_factor.toFixed(2);
    document.getElementById('bt-sharpe').textContent = bt.sharpe_ratio.toFixed(2);
    document.getElementById('bt-trades').textContent = bt.total_trades;
    document.getElementById('bt-drawdown').textContent = `-${bt.max_drawdown_pct.toFixed(2)}%`;
    document.getElementById('bt-avg-trade').textContent = `$${bt.avg_trade_pnl.toFixed(2)}`;
    document.getElementById('bt-hold-days').textContent = bt.avg_hold_days.toFixed(1);
    
    // Equity curve chart
    if (bt.equity_curve && bt.equity_curve.length > 0) {
        Plotly.newPlot('equity-chart', [{
            x: bt.equity_curve.map(p => p.date),
            y: bt.equity_curve.map(p => p.equity),
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            line: { color: bt.total_return >= 0 ? '#10b981' : '#ef4444', width: 2 },
            fillcolor: bt.total_return >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)'
        }], {
            title: 'Equity Curve',
            margin: { t: 40, r: 20, b: 40, l: 60 },
            paper_bgcolor: '#16161f',
            plot_bgcolor: '#16161f',
            font: { color: '#a0a0b0' },
            xaxis: { showgrid: false },
            yaxis: { showgrid: true, gridcolor: '#2a2a3a', title: 'Equity ($)' }
        }, { responsive: true });
    }
    
    // Trade log
    const tbody = document.querySelector('#bt-trades-table tbody');
    tbody.innerHTML = bt.trades.slice(0, 50).map(t => `
        <tr>
            <td>${t.symbol}</td>
            <td>${t.entry_date}<br><small>$${t.entry_price.toFixed(2)}</small></td>
            <td>${t.exit_date}<br><small>$${t.exit_price.toFixed(2)}</small></td>
            <td class="${t.pnl >= 0 ? 'positive' : 'negative'}">$${t.pnl.toFixed(2)}</td>
            <td class="${t.pnl >= 0 ? 'positive' : 'negative'}">${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(1)}%</td>
            <td>${t.hold_days}</td>
            <td>${t.exit_reason}</td>
        </tr>
    `).join('') || '<tr><td colspan="7">No trades</td></tr>';
    
    showToast('Backtest complete!', 'success');
});

// ================== SPY Scalper Game ==================

let spyPriceHistory = [];

function startSpyGame() {
    if (spyGameInterval) clearInterval(spyGameInterval);
    updateSpyGame();  // Load immediately
    spyGameInterval = setInterval(updateSpyGame, 2000);
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
    
    // Update price history and chart
    if (game.price_history && game.price_history.length > 0) {
        const times = game.price_history.map(p => new Date(p.time).toLocaleTimeString());
        const prices = game.price_history.map(p => p.price);
        
        Plotly.react('spy-chart', [{
            x: times,
            y: prices,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#6366f1', width: 2 },
            fill: 'tozeroy',
            fillcolor: 'rgba(99, 102, 241, 0.1)'
        }], {
            margin: { t: 10, r: 20, b: 40, l: 60 },
            paper_bgcolor: '#16161f',
            plot_bgcolor: '#16161f',
            font: { color: '#a0a0b0' },
            xaxis: { showgrid: false },
            yaxis: { showgrid: true, gridcolor: '#2a2a3a' }
        }, { responsive: true, displayModeBar: false });
    }
}

document.getElementById('game-buy-btn').addEventListener('click', async () => {
    const result = await api('/api/game/spy/buy', { method: 'POST' });
    showToast(result.message || result.error, result.success ? 'success' : 'error');
    updateSpyGame();
});

document.getElementById('game-sell-btn').addEventListener('click', async () => {
    const result = await api('/api/game/spy/sell', { method: 'POST' });
    showToast(result.message || result.error, result.success ? 'success' : 'error');
    updateSpyGame();
});

document.getElementById('game-reset-btn').addEventListener('click', async () => {
    await api('/api/game/spy/reset', { method: 'POST' });
    showToast('Game reset', 'info');
    updateSpyGame();
});

// ================== Settings ==================

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

// ================== Order Modal ==================

const modal = document.getElementById('order-modal');

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
    
    if (result.success) {
        showToast(result.message, 'success');
        modal.classList.remove('active');
        if (account === 'paper') loadPaperPortfolio();
    } else {
        showToast(result.error, 'error');
    }
});

// ================== Start App ==================

init();
// Sector leading tickers
const SECTOR_LEADERS = {
    'Technology': ['AAPL','MSFT','NVDA','GOOGL','META','AMZN','CRM','ORCL','ADBE'],
    'Financials': ['JPM','BAC','GS','V','MA','BLK','SCHW','MS','C'],
    'Healthcare': ['UNH','JNJ','LLY','ABBV','MRK','PFE','TMO','ABT','ISRG'],
    'Energy': ['XOM','CVX','COP','SLB','EOG','MPC','OXY','VLO','DVN'],
    'Consumer Discretionary': ['AMZN','TSLA','HD','MCD','NKE','SBUX','LOW','TJX','CMG'],
    'Industrials': ['CAT','GE','HON','UPS','BA','RTX','DE','LMT','FDX'],
    'Materials': ['LIN','APD','SHW','FCX','NUE','ECL','VMC','MLM','NEM'],
    'Utilities': ['NEE','SO','DUK','CEG','SRE','AEP','D','EXC','PCG'],
    'Real Estate': ['PLD','AMT','EQIX','SPG','O','DLR','WELL','AVB','EQR'],
    'Consumer Staples': ['PG','KO','PEP','COST','WMT','PM','CL','MO','GIS'],
    'Communication': ['META','GOOGL','NFLX','DIS','CMCSA','TMUS','T','VZ','CHTR']
};

async function showSectorDetail(idx) {
    const sector = window._sectorData[idx];
    const detail = document.getElementById('sector-detail');
    const leaders = SECTOR_LEADERS[sector.sector] || [];
    
    // Highlight selected card
    document.querySelectorAll('.sector-card').forEach((c, i) => c.classList.toggle('selected', i === idx));
    
    detail.innerHTML = `<h3>${sector.icon} ${sector.sector} — ${sector.sentiment}</h3>
        <div style="display:flex;gap:24px;margin-bottom:16px;font-size:14px;">
            <span>Today: <b class="${sector.change_pct >= 0 ? 'positive' : 'negative'}">${sector.change_pct >= 0 ? '+' : ''}${sector.change_pct.toFixed(2)}%</b></span>
            <span>Week: <b class="${sector.week_change_pct >= 0 ? 'positive' : 'negative'}">${sector.week_change_pct >= 0 ? '+' : ''}${sector.week_change_pct.toFixed(1)}%</b></span>
            <span>Month: <b class="${sector.month_change_pct >= 0 ? 'positive' : 'negative'}">${sector.month_change_pct >= 0 ? '+' : ''}${sector.month_change_pct.toFixed(1)}%</b></span>
            <span>ETF: <b>${sector.etf}</b> @ $${sector.price.toFixed(2)}</span>
        </div>
        <div style="margin-bottom:8px;color:var(--text-secondary);font-size:13px;">${(sector.reasons||[]).join(' · ') || 'Mixed signals'}</div>
        <h4 style="margin:16px 0 8px;">Leading Tickers</h4>
        <div class="leader-grid" id="leader-grid"><div class="loading">Loading...</div></div>`;
    detail.classList.add('active');
    
    // Fetch leader data
    if (leaders.length > 0) {
        const quotes = await Promise.all(leaders.slice(0, 8).map(async (ticker) => {
            try {
                const q = await api('/api/quote/' + ticker);
                return q.success ? { ticker, ...q.quote } : { ticker, price: 0, change_percent: 0 };
            } catch { return { ticker, price: 0, change_percent: 0 }; }
        }));
        
        document.getElementById('leader-grid').innerHTML = quotes.map(q => {
            const chg = q.change_percent || 0;
            return `<div class="leader-card" onclick="analyzeTicker('${q.ticker}')" style="cursor:pointer;">
                <div class="ticker">${q.ticker}</div>
                <div style="font-size:12px;color:var(--text-secondary);">$${(q.price||0).toFixed(2)}</div>
                <div class="leader-change ${chg >= 0 ? 'positive' : 'negative'}">${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%</div>
            </div>`;
        }).join('');
    }
}

function analyzeTicker(ticker) {
    document.getElementById('ticker-input').value = ticker;
    showSection('trading');
    document.getElementById('analyze-btn')?.click();
}
