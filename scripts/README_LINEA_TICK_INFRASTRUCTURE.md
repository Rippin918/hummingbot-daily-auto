# Linea Tick-Level Micropulse Infrastructure

**Institutional-grade orderbook analytics for Lynex DEX on Linea**

This infrastructure provides tick-by-tick micropulse analysis using Coulter counting methodology for the Liquid Appreciation trading strategy. It matches your existing Uniswap V3/EtherEx monitor architecture for unified backtesting and automated strategy execution via Sapient HRM.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Linea Tick Infrastructure                    │
└─────────────────────────────────────────────────────────────────┘
         │
         ├── 1. Tick Stream Collector (linea_tick_collector.py)
         │      ├── Direct Web3 connection to Lynex pool contracts
         │      ├── Block-by-block orderbook snapshots (~2s intervals)
         │      ├── sqrtPriceX96, tick, liquidity distribution
         │      └── Tick bitmap reads for range liquidity
         │
         ├── 2. Redis Pub/Sub Streamer (linea_redis_streamer.py)
         │      ├── Channel: linea:lynex:{pair}:ticks
         │      ├── Real-time snapshot publishing
         │      └── Integration with existing monitors
         │
         ├── 3. Coulter Micropulse Analyzer (linea_micropulse_analyzer.py)
         │      ├── Bid/ask pressure calculation
         │      ├── Liquidity hole detection (gaps > X%)
         │      ├── Imbalance velocity (rate of change)
         │      ├── Fibonacci level detection
         │      └── Trading signal generation
         │
         ├── 4. Integrated Pipeline (linea_integrated_pipeline.py)
         │      ├── End-to-end orchestration
         │      ├── Multi-pool parallel streaming
         │      └── Automated analysis & signal generation
         │
         └── 5. Configuration (config/lynex_pools.json)
                ├── Pool addresses (WETH-USDC, REX-WETH, etc.)
                ├── Redis settings
                └── Analysis parameters
```

---

## 📦 Components

### 1. **Tick Stream Collector** (`linea_tick_collector.py`)

Connects directly to Lynex pool contracts to capture orderbook state at block-level granularity.

**Key Methods:**
- `get_slot0()` - Current tick, sqrtPriceX96, observations
- `get_tick_data(tick)` - Liquidity at specific tick
- `get_tick_range_liquidity(center, range)` - Full orderbook reconstruction
- `capture_snapshot()` - Complete state snapshot
- `stream_ticks()` - Continuous block-by-block collection

**Usage:**
```bash
# Collect WETH-USDC ticks for 10 minutes
python3 linea_tick_collector.py \
  --pool 0x... \
  --duration 600 \
  --tick-range 200 \
  --output weth_usdc_ticks.json
```

**Output Format:**
```json
{
  "timestamp": 1732435200,
  "block": 1234567,
  "pool": "0x...",
  "current_tick": 204240,
  "sqrtPriceX96": "79228162514264337593543950336",
  "price": 1850.42,
  "liquidity": "12345678901234",
  "tick_liquidity": {
    "204180": {
      "liquidityGross": "1000000000000",
      "liquidityNet": "500000000000",
      "price": 1849.12,
      "initialized": true
    }
  }
}
```

---

### 2. **Redis Pub/Sub Streamer** (`linea_redis_streamer.py`)

Publishes tick snapshots to Redis channels for real-time consumption by existing monitors.

**Channel Convention:**
```
linea:lynex:{pair}:ticks
```

Examples:
- `linea:lynex:weth-usdc:ticks`
- `linea:lynex:rex-weth:ticks`

**Usage:**
```bash
# Stream WETH-USDC to Redis
python3 linea_redis_streamer.py \
  --pool 0x... \
  --pair WETH-USDC \
  --redis-host localhost \
  --redis-port 6379

# Test subscriber
python3 linea_redis_streamer.py \
  --pool 0x... \
  --pair WETH-USDC \
  --test-subscribe \
  --duration 60
```

**Message Format:**
```json
{
  "type": "tick_snapshot",
  "source": "lynex",
  "network": "linea",
  "pair": "WETH-USDC",
  "timestamp": 1732435200,
  "block": 1234567,
  "orderbook": {
    "current_tick": 204240,
    "current_price": 1850.42,
    "total_liquidity": "12345678901234",
    "tick_distribution": { ... }
  }
}
```

---

### 3. **Coulter Micropulse Analyzer** (`linea_micropulse_analyzer.py`)

Implements Coulter counting methodology for orderbook microstructure analysis.

**Analysis Signals:**

#### Bid/Ask Pressure
```python
{
  "bid_liquidity": 10000000,
  "ask_liquidity": 8000000,
  "bid_pressure": 0.556,    # Weighted by distance
  "ask_pressure": 0.444,
  "imbalance": 0.111        # +/- indicates direction
}
```

#### Liquidity Holes
```python
{
  "tick_lower": 204180,
  "tick_upper": 204360,
  "gap_ticks": 180,
  "gap_percent": 8.5,       # Price gap percentage
  "side": "ask",            # bid or ask
  "severity": "critical"    # critical or moderate
}
```

#### Imbalance Velocity
```python
{
  "current_velocity": 0.025,     # Imbalance change per second
  "avg_velocity": 0.018,
  "acceleration": 0.007,
  "trend": "bullish",           # bullish/bearish/neutral
  "magnitude": 0.025
}
```

#### Trading Signals
```python
{
  "action": "buy",              # buy/sell/hold
  "confidence": 0.78,           # 0-1 confidence score
  "reasons": [
    "Strong bid pressure (bullish)",
    "Bullish momentum (velocity: 0.0250)"
  ],
  "risk": "medium"
}
```

**Usage:**
```bash
# Analyze saved snapshots
python3 linea_micropulse_analyzer.py \
  --input data/ticks/weth_usdc_20231124.json \
  --output data/analysis/weth_usdc_analysis.json \
  --lookback 20
```

---

### 4. **Integrated Pipeline** (`linea_integrated_pipeline.py`)

End-to-end orchestration: collection → streaming → analysis.

**Features:**
- Multi-pool parallel streaming
- Real-time Coulter analysis
- Automated signal generation
- Graceful shutdown (SIGINT/SIGTERM)
- Auto-save results

**Usage:**
```bash
# Run full pipeline for WETH-USDC
python3 linea_integrated_pipeline.py \
  --pairs WETH-USDC \
  --duration 3600

# Run multiple pairs in parallel
python3 linea_integrated_pipeline.py \
  --pairs "WETH-USDC,REX-WETH,FOXY-WETH" \
  --duration 7200

# Continuous mode (no duration limit)
python3 linea_integrated_pipeline.py \
  --pairs WETH-USDC
```

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

Required:
- `web3>=6.0.0` - Ethereum/Linea RPC interaction
- `redis>=5.0.0` - Pub/sub streaming
- `numpy>=1.24.0` - Numerical analysis
- `aiohttp>=3.9.0` - Async HTTP

### 2. Configure Pool Addresses

Edit `scripts/config/lynex_pools.json` and fill in pool contract addresses:

```json
{
  "pools": {
    "WETH-USDC": {
      "address": "0x...",  // <-- Add real pool address
      "symbol": "WETH-USDC",
      "fee": 3000,
      "tick_spacing": 60,
      "priority": "high"
    }
  }
}
```

**Finding Pool Addresses:**

Method 1: Use discovery tool
```bash
python3 linea_data_collector.py --discover
```

Method 2: Query Lynex subgraph
```bash
curl -X POST https://api.goldsky.com/api/public/project_clv14x49kz9kz01saerx7bxpg/subgraphs/lynex/1.0.0/gn \
  -H "Content-Type: application/json" \
  -d '{"query":"{ pools(first:20,orderBy:volumeUSD,orderDirection:desc) { id token0{symbol} token1{symbol} }}"}'
```

Method 3: DEX Screener
- Visit [DEX Screener - Linea](https://dexscreener.com/linea)
- Search for your token pair
- Copy pool contract address from URL or details

### 3. Start Redis (if using streaming)
```bash
docker run -d -p 6379:6379 redis:latest

# Or use your existing Redis instance
```

### 4. Test with WETH-USDC (High Liquidity)
```bash
# Verify pipeline works with established pair first
python3 linea_tick_collector.py \
  --pool <WETH-USDC-POOL-ADDRESS> \
  --duration 120 \
  --tick-range 200
```

### 5. Run Full Pipeline
```bash
# Production mode with Redis streaming
python3 linea_integrated_pipeline.py \
  --pairs "WETH-USDC,REX-WETH" \
  --duration 3600
```

---

## 📊 Data Flow

```
Lynex Pool Contract (Linea)
         ↓
   [Web3 RPC Call ~2s]
         ↓
  Tick Stream Collector
    (Current state + tick distribution)
         ↓
  Redis Pub/Sub Channel ← Subscribers (Existing Monitors)
         ↓
  Coulter Micropulse Analyzer
    (Pressure, velocity, holes, Fibonacci)
         ↓
  Trading Signals
    (Buy/Sell/Hold + Confidence)
         ↓
  Sapient HRM (Automated Strategy Execution)
```

---

## 🔧 Configuration

### Collector Settings (`config/lynex_pools.json`)
```json
{
  "collector": {
    "default_tick_range": 200,      // Ticks around current price
    "snapshot_interval": 2.0,       // Linea block time
    "max_snapshots": 10000,         // Memory limit
    "auto_save_interval": 300       // Save every 5 minutes
  }
}
```

### Analyzer Settings
```json
{
  "analyzer": {
    "lookback_periods": 20,         // History for velocity
    "hole_threshold": 0.05,         // 5% gap = liquidity hole
    "fibonacci_range_percent": 5.0, // Range for Fib levels
    "imbalance_threshold": 0.3,     // Strong imbalance trigger
    "velocity_threshold": 0.01      // Velocity significance
  }
}
```

---

## 🎯 Integration with Existing Infrastructure

This infrastructure is designed to **drop into your existing monitoring setup**:

### Matches Existing Format
- Block-by-block snapshots (like Uniswap V3 monitor)
- Redis pub/sub channels (like EtherEx monitor)
- JSON storage format (for unified backtesting)
- Coulter analysis signals (standardized format)

### Usage in Your Monitors
```python
import redis.asyncio as redis
from linea_micropulse_analyzer import CoulterMicropulseAnalyzer

# Subscribe to Linea tick stream
r = await redis.Redis(host='localhost', port=6379)
pubsub = r.pubsub()
await pubsub.subscribe('linea:lynex:weth-usdc:ticks')

analyzer = CoulterMicropulseAnalyzer()

async for message in pubsub.listen():
    if message['type'] == 'message':
        snapshot = json.loads(message['data'])

        # Your existing Coulter analysis pipeline
        analysis = analyzer.analyze_snapshot(snapshot)

        # Feed into Sapient HRM
        if analysis['trading_signal']['confidence'] > 0.7:
            await sapient_hrm.execute_signal(analysis)
```

---

## 📁 Directory Structure

```
scripts/
├── linea_tick_collector.py         # Tick stream collector
├── linea_redis_streamer.py          # Redis pub/sub integration
├── linea_micropulse_analyzer.py     # Coulter analysis
├── linea_integrated_pipeline.py     # End-to-end pipeline
├── linea_data_collector.py          # Original OHLCV collector
│
├── abis/
│   └── lynex_pool_abi.json          # Uniswap V3 compatible ABI
│
├── config/
│   └── lynex_pools.json             # Pool addresses & settings
│
└── README_LINEA_TICK_INFRASTRUCTURE.md

data/
├── ticks/                           # Raw tick snapshots
│   └── WETH-USDC_20231124_143022.json
│
└── analysis/                        # Coulter analysis results
    └── WETH-USDC_analysis_20231124_143022.json
```

---

## 🧪 Testing & Validation

### 1. Unit Test Components
```bash
# Test tick collector
python3 linea_tick_collector.py \
  --pool 0x... \
  --duration 60

# Test Redis streamer
python3 linea_redis_streamer.py \
  --pool 0x... \
  --pair WETH-USDC \
  --test-subscribe \
  --duration 30

# Test analyzer on saved data
python3 linea_micropulse_analyzer.py \
  --input data/ticks/saved_snapshot.json
```

### 2. Verify Data Quality
```python
import json

# Load snapshot
with open('data/ticks/WETH-USDC_snapshot.json', 'r') as f:
    data = json.load(f)

# Verify structure
assert 'snapshots' in data
assert len(data['snapshots']) > 0
assert 'tick_liquidity' in data['snapshots'][0]
assert 'current_tick' in data['snapshots'][0]

print(f"✓ {len(data['snapshots'])} valid snapshots")
```

### 3. Integration Test with Existing Monitors
```bash
# Terminal 1: Start Linea streamer
python3 linea_redis_streamer.py --pool 0x... --pair WETH-USDC

# Terminal 2: Your existing monitor subscribes
python3 ~/repos/liquid-appreciation-backtest/your_monitor.py \
  --subscribe linea:lynex:weth-usdc:ticks
```

---

## 🔍 Troubleshooting

### Pool Address Not Found
```
⚠ Skipping REX-WETH: Pool address not configured
```
**Solution:** Run discovery or query subgraph to find pool contracts

### Redis Connection Failed
```
ConnectionError: Failed to connect to Redis: Connection refused
```
**Solution:** Start Redis server
```bash
docker run -d -p 6379:6379 redis:latest
```

### RPC Rate Limiting
```
HTTPError: 429 Too Many Requests
```
**Solution:** Use private RPC endpoint or add delays
```json
{
  "rpc_url": "https://your-private-linea-rpc.com",
  "collector": {
    "snapshot_interval": 3.0  // Increase interval
  }
}
```

### Insufficient Tick Data
```
Warning: Only 2 initialized ticks found
```
**Solution:** Increase tick range or check if pool has liquidity
```bash
python3 linea_tick_collector.py --tick-range 500
```

---

## 📈 Performance

- **Latency:** ~2-3 seconds (Linea block time)
- **Throughput:** 0.5 snapshots/second per pool
- **Memory:** ~10MB per 1000 snapshots
- **Redis:** ~1KB per message
- **Parallel Pools:** 5-10 recommended (depends on RPC limits)

---

## 🎓 Next Steps

### 1. Discover Your Token Pool Addresses
```bash
python3 linea_data_collector.py --discover
```

Look for:
- REX (Etherex) - Check Lynex, SyncSwap
- FOXY - Check Lynex, SyncSwap
- LINEA - Native token
- EURE - Check NILE exchange

### 2. Verify Pipeline with WETH-USDC
Test infrastructure with high-liquidity pair before adding custom tokens.

### 3. Integrate with Sapient HRM
Connect trading signals to your automated strategy execution system.

### 4. Backtest
Use saved snapshots with your existing backtesting framework:
```python
from liquid_appreciation_backtest import BacktestEngine

engine = BacktestEngine()
engine.load_snapshots('data/ticks/WETH-USDC_*.json')
engine.run_strategy('coulter_micropulse')
```

---

## 📞 Support

For issues or questions:
1. Check `config/lynex_pools.json` for correct pool addresses
2. Verify Redis is running: `redis-cli ping`
3. Test RPC connection: `python3 -c "from web3 import Web3; print(Web3(Web3.HTTPProvider('https://rpc.linea.build')).is_connected())"`

---

**Built for institutional-grade orderbook analytics on Linea DEX.**
