#!/usr/bin/env python3
"""
RSI & Stochastic Neural Network Training
=========================================
Trains a neural network on RSI and Stochastic indicators.
Outputs Sharpe ratio and other metrics.

Usage:
    python training/train_rsi_stochastic.py --symbol SPY --days 365
    python training/train_rsi_stochastic.py --symbol SPY --days 730 --epochs 100
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

try:
    import yfinance as yf
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install yfinance torch scikit-learn")
    sys.exit(1)


# ============================================================================
# INDICATOR CALCULATIONS
# ============================================================================

def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculate RSI indicator."""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gains = np.zeros(len(prices))
    avg_losses = np.zeros(len(prices))
    
    # Initial averages
    avg_gains[period] = np.mean(gains[:period])
    avg_losses[period] = np.mean(losses[:period])
    
    # Smoothed averages
    for i in range(period + 1, len(prices)):
        avg_gains[i] = (avg_gains[i-1] * (period - 1) + gains[i-1]) / period
        avg_losses[i] = (avg_losses[i-1] * (period - 1) + losses[i-1]) / period
    
    rs = np.divide(avg_gains, avg_losses, out=np.zeros_like(avg_gains), where=avg_losses != 0)
    rsi = 100 - (100 / (1 + rs))
    rsi[:period] = 50  # Fill initial values
    
    return rsi


def calculate_stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, 
                          k_period: int = 14, d_period: int = 3) -> tuple:
    """Calculate Stochastic %K and %D."""
    stoch_k = np.zeros(len(close))
    stoch_d = np.zeros(len(close))
    
    for i in range(k_period - 1, len(close)):
        highest_high = np.max(high[i - k_period + 1:i + 1])
        lowest_low = np.min(low[i - k_period + 1:i + 1])
        
        if highest_high != lowest_low:
            stoch_k[i] = ((close[i] - lowest_low) / (highest_high - lowest_low)) * 100
        else:
            stoch_k[i] = 50
    
    # %D is SMA of %K
    for i in range(k_period + d_period - 2, len(close)):
        stoch_d[i] = np.mean(stoch_k[i - d_period + 1:i + 1])
    
    return stoch_k, stoch_d


def calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
    """Calculate Simple Moving Average."""
    sma = np.zeros(len(prices))
    for i in range(period - 1, len(prices)):
        sma[i] = np.mean(prices[i - period + 1:i + 1])
    return sma


# ============================================================================
# NEURAL NETWORK MODEL
# ============================================================================

class RSIStochNet(nn.Module):
    """Neural network for RSI + Stochastic signals."""
    
    def __init__(self, input_size: int = 8, hidden_size: int = 32):
        super().__init__()
        
        self.net = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_size // 2, 3),  # 3 classes: down, neutral, up
        )
    
    def forward(self, x):
        return self.net(x)


# ============================================================================
# DATA PREPARATION
# ============================================================================

def fetch_data(symbol: str, days: int = 365) -> dict:
    """Fetch price data from Yahoo Finance."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print(f"Fetching {symbol} data from {start_date.date()} to {end_date.date()}...")
    
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date)
    
    if df.empty:
        raise ValueError(f"No data found for {symbol}")
    
    return {
        'open': df['Open'].values,
        'high': df['High'].values,
        'low': df['Low'].values,
        'close': df['Close'].values,
        'volume': df['Volume'].values,
        'dates': df.index.tolist(),
    }


def prepare_features(data: dict, lookback: int = 5, forecast: int = 5) -> tuple:
    """
    Prepare features and labels for training.
    
    Features:
    - RSI (14)
    - RSI change (1-bar)
    - Stochastic %K
    - Stochastic %D
    - %K - %D (crossover signal)
    - Price vs SMA20 (%)
    - Price vs SMA50 (%)
    - Volume ratio (vs 20-day avg)
    
    Labels:
    - 0: Down (< -1% in next N bars)
    - 1: Neutral (-1% to +1%)
    - 2: Up (> +1% in next N bars)
    """
    close = data['close']
    high = data['high']
    low = data['low']
    volume = data['volume']
    
    # Calculate indicators
    rsi = calculate_rsi(close, 14)
    stoch_k, stoch_d = calculate_stochastic(high, low, close, 14, 3)
    sma20 = calculate_sma(close, 20)
    sma50 = calculate_sma(close, 50)
    vol_sma20 = calculate_sma(volume.astype(float), 20)
    
    # Build feature matrix
    features = []
    labels = []
    
    start_idx = 50  # Ensure all indicators are valid
    end_idx = len(close) - forecast
    
    for i in range(start_idx, end_idx):
        # Features
        feat = [
            rsi[i] / 100,  # Normalize to 0-1
            (rsi[i] - rsi[i-1]) / 100,  # RSI change
            stoch_k[i] / 100,
            stoch_d[i] / 100,
            (stoch_k[i] - stoch_d[i]) / 100,  # Crossover signal
            (close[i] - sma20[i]) / sma20[i] if sma20[i] > 0 else 0,
            (close[i] - sma50[i]) / sma50[i] if sma50[i] > 0 else 0,
            volume[i] / vol_sma20[i] if vol_sma20[i] > 0 else 1,
        ]
        features.append(feat)
        
        # Label: future return
        future_return = (close[i + forecast] - close[i]) / close[i] * 100
        
        if future_return < -1:
            labels.append(0)  # Down
        elif future_return > 1:
            labels.append(2)  # Up
        else:
            labels.append(1)  # Neutral
    
    return np.array(features), np.array(labels), {
        'rsi': rsi[start_idx:end_idx],
        'stoch_k': stoch_k[start_idx:end_idx],
        'stoch_d': stoch_d[start_idx:end_idx],
        'close': close[start_idx:end_idx],
        'future_close': close[start_idx + forecast:end_idx + forecast],
    }


# ============================================================================
# TRAINING
# ============================================================================

def train_model(X_train, y_train, X_val, y_val, epochs: int = 50, lr: float = 0.001):
    """Train the neural network."""
    
    # Convert to tensors
    X_train_t = torch.FloatTensor(X_train)
    y_train_t = torch.LongTensor(y_train)
    X_val_t = torch.FloatTensor(X_val)
    y_val_t = torch.LongTensor(y_val)
    
    # Create data loaders
    train_dataset = TensorDataset(X_train_t, y_train_t)
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    
    # Model
    model = RSIStochNet(input_size=X_train.shape[1])
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    
    best_val_acc = 0
    best_model_state = None
    
    for epoch in range(epochs):
        model.train()
        train_loss = 0
        
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        
        # Validation
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val_t)
            val_preds = torch.argmax(val_outputs, dim=1)
            val_acc = (val_preds == y_val_t).float().mean().item()
        
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_model_state = model.state_dict().copy()
        
        if (epoch + 1) % 10 == 0:
            print(f"Epoch {epoch+1}/{epochs} - Loss: {train_loss/len(train_loader):.4f} - Val Acc: {val_acc:.4f}")
    
    # Load best model
    model.load_state_dict(best_model_state)
    return model


# ============================================================================
# BACKTESTING
# ============================================================================

def backtest(model, X_test, raw_data, threshold: float = 0.6) -> dict:
    """
    Backtest the model and calculate Sharpe ratio.
    
    Args:
        model: Trained model
        X_test: Test features
        raw_data: Raw price data for P/L calculation
        threshold: Confidence threshold for taking trades
    
    Returns:
        Dict with backtest results including Sharpe ratio
    """
    model.eval()
    
    X_test_t = torch.FloatTensor(X_test)
    
    with torch.no_grad():
        outputs = model(X_test_t)
        probs = torch.softmax(outputs, dim=1).numpy()
        preds = np.argmax(probs, axis=1)
        confidence = np.max(probs, axis=1)
    
    # Calculate returns
    close = raw_data['close']
    future_close = raw_data['future_close']
    actual_returns = (future_close - close) / close
    
    # Simulate trades
    trades = []
    
    for i in range(len(preds)):
        if confidence[i] < threshold:
            continue
        
        pred = preds[i]
        actual_ret = actual_returns[i]
        
        if pred == 2:  # Predicted UP
            trades.append({
                'direction': 'long',
                'return': actual_ret,
                'correct': actual_ret > 0
            })
        elif pred == 0:  # Predicted DOWN
            trades.append({
                'direction': 'short',
                'return': -actual_ret,  # Profit on shorts when price goes down
                'correct': actual_ret < 0
            })
    
    if not trades:
        return {
            'trades': 0,
            'win_rate': 0,
            'sharpe': 0,
            'total_return': 0,
            'avg_return': 0,
            'max_drawdown': 0,
        }
    
    returns = np.array([t['return'] for t in trades])
    wins = sum(1 for t in trades if t['correct'])
    
    # Sharpe ratio (annualized)
    if returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
    else:
        sharpe = 0
    
    # Cumulative returns for drawdown
    cumulative = np.cumprod(1 + returns) - 1
    running_max = np.maximum.accumulate(1 + cumulative)
    drawdown = (running_max - (1 + cumulative)) / running_max
    max_drawdown = drawdown.max()
    
    return {
        'trades': len(trades),
        'win_rate': wins / len(trades) * 100,
        'sharpe': sharpe,
        'total_return': cumulative[-1] * 100,
        'avg_return': returns.mean() * 100,
        'max_drawdown': max_drawdown * 100,
        'long_trades': sum(1 for t in trades if t['direction'] == 'long'),
        'short_trades': sum(1 for t in trades if t['direction'] == 'short'),
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Train RSI + Stochastic Neural Network')
    parser.add_argument('--symbol', type=str, default='SPY', help='Symbol to train on')
    parser.add_argument('--days', type=int, default=365, help='Days of historical data')
    parser.add_argument('--epochs', type=int, default=50, help='Training epochs')
    parser.add_argument('--forecast', type=int, default=5, help='Forecast horizon (bars)')
    parser.add_argument('--threshold', type=float, default=0.6, help='Confidence threshold')
    parser.add_argument('--output', type=str, default='training/results', help='Output directory')
    args = parser.parse_args()
    
    print("=" * 60)
    print("RSI & STOCHASTIC NEURAL NETWORK TRAINING")
    print("=" * 60)
    print(f"Symbol: {args.symbol}")
    print(f"Days: {args.days}")
    print(f"Epochs: {args.epochs}")
    print(f"Forecast: {args.forecast} bars")
    print("=" * 60)
    
    # Fetch data
    data = fetch_data(args.symbol, args.days)
    print(f"Loaded {len(data['close'])} bars")
    
    # Prepare features
    X, y, raw = prepare_features(data, forecast=args.forecast)
    print(f"Features shape: {X.shape}")
    print(f"Label distribution: Down={sum(y==0)}, Neutral={sum(y==1)}, Up={sum(y==2)}")
    
    # Split data (time-series aware)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    
    # Further split train into train/val
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.2, random_state=42
    )
    
    print(f"\nTrain: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
    
    # Normalize features
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)
    
    # Train
    print("\nTraining...")
    model = train_model(X_train, y_train, X_val, y_val, epochs=args.epochs)
    
    # Prepare test raw data
    test_raw = {
        'close': raw['close'][split_idx:],
        'future_close': raw['future_close'][split_idx:],
        'rsi': raw['rsi'][split_idx:],
        'stoch_k': raw['stoch_k'][split_idx:],
        'stoch_d': raw['stoch_d'][split_idx:],
    }
    
    # Backtest
    print("\nBacktesting...")
    results = backtest(model, X_test, test_raw, threshold=args.threshold)
    
    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total Trades: {results['trades']}")
    print(f"Win Rate: {results['win_rate']:.1f}%")
    print(f"Sharpe Ratio: {results['sharpe']:.2f}")
    print(f"Total Return: {results['total_return']:.1f}%")
    print(f"Avg Return/Trade: {results['avg_return']:.2f}%")
    print(f"Max Drawdown: {results['max_drawdown']:.1f}%")
    print(f"Long Trades: {results['long_trades']}")
    print(f"Short Trades: {results['short_trades']}")
    print("=" * 60)
    
    # Save results
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results_file = output_dir / f"{args.symbol}_rsi_stoch_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            'symbol': args.symbol,
            'days': args.days,
            'epochs': args.epochs,
            'forecast': args.forecast,
            'threshold': args.threshold,
            'timestamp': datetime.now().isoformat(),
            'results': results,
        }, f, indent=2)
    
    print(f"\nResults saved to: {results_file}")
    
    # Save model
    model_file = output_dir / f"{args.symbol}_rsi_stoch_model.pt"
    torch.save({
        'model_state': model.state_dict(),
        'scaler_mean': scaler.mean_.tolist(),
        'scaler_scale': scaler.scale_.tolist(),
    }, model_file)
    
    print(f"Model saved to: {model_file}")
    
    return results


if __name__ == '__main__':
    main()
