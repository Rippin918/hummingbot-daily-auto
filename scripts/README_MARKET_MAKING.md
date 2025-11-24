# Linea Multi-DEX Market Making Infrastructure
**Institutional-Grade Avellaneda-Stoikov Framework with Cross-DEX Analytics**

Complete tick-level market making analytics system for Linea DEX ecosystem, integrating adverse selection detection, optimal spread calculation, inventory management, and cross-venue arbitrage.

---

## 🎯 Overview

This infrastructure provides **professional market making capabilities** combining:

1. **Multi-DEX Support** - Unified interface for 5 DEXes on Linea
2. **Adverse Selection Detection** - VPIN toxicity monitoring
3. **Avellaneda-Stoikov Optimization** - Inventory-aware spread calculation
4. **Price Impact Analysis** - Kyle's Lambda estimation
5. **Regime Detection** - Orderflow imbalance & mean-reversion analysis
6. **Cross-DEX Analytics** - Arbitrage detection, spread matrix, unified liquidity
7. **Integration Ready** - Feeds Sapient HRM → Hummingbot MCP

---

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Multi-DEX Market Making System                     │
└─────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴──────────┐
                    │   DEX Adapters       │
                    └───────────┬──────────┘
         ┌──────────────┬───────┴───────┬──────────────┐
         │              │               │              │
    ┌────▼────┐   ┌────▼────┐   ┌──────▼──┐   ┌──────▼──┐   ┌────────┐
    │ Lynex   │   │ Etherex │   │  Nile   │   │SyncSwap │   │ Kyber  │
    │ (V3)    │   │  (REX)  │   │  (V3)   │   │  (AMM)  │   │  (V3)  │
    └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘   └────┬───┘
         │              │               │              │              │
         └──────────────┴───────────────┴──────────────┴──────────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Tick Stream         │
                    │  Collector           │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Market Making       │
                    │  Analytics Engine    │
                    └───────────┬──────────┘
             ┌──────────────────┼──────────────────┐
             │                  │                  │
      ┌──────▼─────┐  ┌─────────▼────────┐  ┌────▼──────┐
      │  VPIN      │  │ Volatility       │  │ Inventory │
      │  Toxicity  │  │ Estimators       │  │ Manager   │
      └──────┬─────┘  └─────────┬────────┘  └────┬──────┘
             │                  │                  │
      ┌──────▼─────┐  ┌─────────▼────────┐  ┌────▼──────┐
      │ Kyle's     │  │ Orderflow        │  │ Avellaneda│
      │ Lambda     │  │ Imbalance        │  │ -Stoikov  │
      └──────┬─────┘  └─────────┬────────┘  └────┬──────┘
             │                  │                  │
             └──────────────────┴──────────────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Unified MM Signal   │
                    │  Generator           │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Cross-DEX Analytics │
                    │  • Arbitrage         │
                    │  • Spread Matrix     │
                    │  • Best Execution    │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Redis Pub/Sub       │
                    │  • Per-DEX channels  │
                    │  • Arb channel       │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Sapient HRM         │
                    │  Automated Decisions │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Hummingbot MCP      │
                    │  Strategy Execution  │
                    └──────────────────────┘
```

---

## 📦 Components

### 1. **DEX Adapters** (`dex_adapters/`)

Unified interface for multiple DEXes on Linea:

- **`base_adapter.py`** - Abstract base class with common interface
- **`lynex_adapter.py`** - Lynex (Uniswap V3 style)
- **`etherex_adapter.py`** - Etherex/REX (configured: ETHEREX-LINEA-WETH-6600, ~$2.86M liquidity)
- **`nile_adapter.py`** - Nile (V3 fork)
- **`syncswap_adapter.py`** - SyncSwap (zkSync AMM)
- **`kyber_adapter.py`** - KyberSwap Elastic

**Common Methods:**
```python
await adapter.initialize()
await adapter.get_current_price()
await adapter.get_liquidity_distribution()
await adapter.capture_snapshot()
await adapter.subscribe_to_swaps(callback)
```

### 2. **VPIN Toxicity Module** (`mm_analytics/vpin.py`)

**Volume-Synchronized Probability of Informed Trading**

Detects adverse selection (toxic orderflow) to prevent market makers from being picked off by informed traders.

**Key Metrics:**
- VPIN Score (0-1): Probability of informed trading
- Toxicity Levels: safe (<0.3), normal (0.3-0.5), elevated (0.5-0.7), high (>0.7)

**Strategy:**
```
VPIN < 0.3  → Tighten spreads (uninformed flow)
VPIN 0.3-0.5 → Standard spreads
VPIN 0.5-0.7 → Widen spreads  
VPIN > 0.7  → Pause quoting or widen significantly
```

**Usage:**
```python
from mm_analytics.vpin import VPINCalculator

vpin = VPINCalculator(bucket_size=50.0, num_buckets=50)

for swap_event in swap_stream:
    result = vpin.add_swap_event(swap_event)
    if result and result.toxicity_level == "high":
        # Widen spreads or pause
        spread_multiplier = 2.0
```

### 3. **Volatility Estimators** (`mm_analytics/volatility.py`)

Provides **σ parameter** for Avellaneda-Stoikov spread calculation.

**Three Estimators:**
1. **Realized Volatility** - Classic close-to-close returns
2. **Parkinson Estimator** - High-low range (1.67x more efficient)
3. **Garman-Klass Estimator** - OHLC (7.4x more efficient) ⭐

**Usage:**
```python
from mm_analytics.volatility import VolatilityEstimator

vol_est = VolatilityEstimator(window_periods=100, annualize=True)

for candle in ohlc_data:
    vol_est.add_candle(open, high, low, close)

result = vol_est.estimate()
sigma = result.recommended_vol  # Use for Avellaneda-Stoikov
```

### 4. **Avellaneda-Stoikov Framework** (`mm_analytics/avellaneda_stoikov.py`)

**Optimal Market Making with Inventory Risk Management**

**Components:**

#### A. Inventory Manager
Calculates reservation price adjustment based on position risk:

```
r = s - q * γ * σ² * (T - t)

where:
  s = mid price
  q = current inventory
  γ = risk aversion
  σ = volatility
  T-t = time remaining
```

**Usage:**
```python
inventory_mgr = InventoryManager(max_inventory=100.0, gamma=0.1)
inventory_mgr.update_inventory(70.0)  # Long 70 units

signal = inventory_mgr.get_inventory_signal(mid_price=100.0, volatility=0.2)
# signal.reservation_price → inventory-adjusted mid
# signal.recommendation → "aggressively_sell", "prefer_sell", etc.
```

#### B. Kyle's Lambda Estimator
Measures **price impact** per unit of order flow:

```
ΔP_t = λ * Q_t + ε_t

High λ = illiquid → wider spreads
Low λ = liquid → tighter spreads
```

**Usage:**
```python
kyle = KyleLambdaEstimator()

for trade in trade_stream:
    kyle.add_trade(price_before, price_after, volume, side)

result = kyle.estimate_lambda()
spread_multiplier = result.spread_multiplier  # 1.0 to 3.0
```

#### C. Optimal Spread Calculator
Calculates Avellaneda-Stoikov optimal bid/ask spread:

```
δ = γσ²T + (2/γ)ln(1 + γ/k)

where:
  γ = risk aversion
  σ = volatility
  T = time horizon
  k = order arrival rate
```

**Usage:**
```python
as_calc = AvellanedaStoikovCalculator(gamma=0.1, k=1.5)

spread = as_calc.calculate_optimal_spread(
    mid_price=100.0,
    volatility=0.2,
    inventory=50.0,
    kyle_lambda=0.001
)

bid_price = spread.bid_price
ask_price = spread.ask_price
```

### 5. **Orderflow Imbalance Analyzer** (`mm_analytics/orderflow.py`)

**Regime Detection: Mean-Reverting vs Trending**

Determines market microstructure regime to adjust quoting aggressiveness.

**Key Metrics:**
- **Half-Life**: Time for imbalance to decay to 50% (AR(1) model)
- **Autocorrelation**: Persistence of order flow
- **Regime Classification**:
  - **Mean-Reverting**: Short half-life, low autocorrelation → tighten spreads, quote aggressively
  - **Trending**: Long half-life, high autocorrelation → widen spreads, skew in trend direction

**Usage:**
```python
analyzer = OrderflowAnalyzer(window_size=100)

for snapshot in tick_stream:
    analyzer.add_observation(bid_liquidity, ask_liquidity)

result = analyzer.classify_regime()

if result.regime == "mean_reverting":
    # Tighten spreads significantly
    spread_multiplier = 0.6
elif result.regime == "trending":
    # Widen spreads, skew in direction
    spread_multiplier = 1.8
```

### 6. **Unified MM Analyzer** (`mm_analytics/unified_mm_analyzer.py`)

**Combines all analytics into comprehensive trading signals**

Integrates:
- VPIN toxicity
- Volatility estimation
- Inventory management
- Kyle's Lambda
- Orderflow regime
- Avellaneda-Stoikov spreads

**Output Signal:**
```python
{
  "action": "quote_tight | quote_normal | quote_wide | pause | rebalance_inventory",
  "confidence": 0.85,
  "reasoning": [
    "Mean-reverting regime (HL=8.5) - tighten spreads",
    "Low VPIN (0.25) - safe to quote",
    "High inventory (ratio=0.7): prefer_sell"
  ],
  "toxicity_risk": "low",
  "inventory_risk": "high",
  "liquidity_risk": "medium",
  
  "bid_price": 99.85,
  "ask_price": 100.15,
  "spread_bps": 30
}
```

**Usage:**
```python
from mm_analytics.unified_mm_analyzer import UnifiedMMAnalyzer

analyzer = UnifiedMMAnalyzer(
    pair="WETH-USDC",
    dex="lynex",
    max_inventory=100.0,
    gamma=0.1
)

# Process tick snapshot
signal = analyzer.process_tick_snapshot(snapshot, current_inventory=50.0)

# Send to Sapient HRM for execution
if signal.confidence > 0.7:
    sapient_hrm.execute_mm_signal(signal)
```

### 7. **Cross-DEX Analytics** (`cross_dex_analytics.py`)

**Multi-Venue Analysis & Arbitrage Detection**

Analyzes opportunities across all 5 Linea DEXes simultaneously.

**Features:**

#### A. Spread Matrix
Real-time price comparison across all venues:
```python
analyzer = CrossDEXAnalyzer(dexes=["lynex", "etherex", "nile", "syncswap", "kyber"])

spread_matrix = analyzer.get_spread_matrix("WETH-USDC")
# {
#   "best_bid": 1850.3, "best_bid_dex": "etherex",
#   "best_ask": 1849.5, "best_ask_dex": "nile",
#   "nbbo_spread_bps": 43
# }
```

#### B. Arbitrage Detection
Cross-DEX arbitrage opportunities (net of gas):
```python
arbs = analyzer.detect_arbitrage("WETH-USDC", min_profit_bps=20)

for arb in arbs:
    print(f"Buy on {arb.buy_dex} @ {arb.buy_price}")
    print(f"Sell on {arb.sell_dex} @ {arb.sell_price}")
    print(f"Net Profit: {arb.est_net_profit_pct}%")
```

#### C. Unified Liquidity View
Aggregate liquidity across all venues:
```python
unified = analyzer.get_unified_liquidity("WETH-USDC")
# {
#   "total_liquidity": 345000,
#   "most_liquid_dex": "etherex",
#   "liquidity_by_dex": {...}
# }
```

#### D. Best Execution Routing
Determine optimal routing for large orders:
```python
route = analyzer.get_best_execution_route("WETH-USDC", "buy", size=10.0)
# {
#   "avg_price": 1850.2,
#   "route": [
#     {"dex": "nile", "size": 6.0, "price": 1849.5},
#     {"dex": "lynex", "size": 4.0, "price": 1851.2}
#   ]
# }
```

---

## 🚀 Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Dependencies added:
# - redis>=5.0.0 (for pub/sub streaming)
# - numpy>=1.24.0 (for analytics)
```

### Configuration

Edit `scripts/config/multi_dex_config.json`:

```json
{
  "dexes": {
    "etherex": {
      "pools": {
        "LINEA-WETH": {
          "address": "ETHEREX-LINEA-WETH-6600",
          "liquidity_usd": 2860000,
          "priority": "high"
        }
      }
    }
  },
  "market_making": {
    "inventory": {"max_inventory": 100.0, "gamma": 0.1},
    "vpin": {"bucket_size": 50.0, "num_buckets": 50},
    "volatility": {"window_periods": 100, "estimator": "garman_klass"}
  }
}
```

### Usage Examples

#### 1. Single-DEX Market Making

```python
from dex_adapters.etherex_adapter import EtherexAdapter
from mm_analytics.unified_mm_analyzer import UnifiedMMAnalyzer

# Initialize adapter
adapter = EtherexAdapter(pool_address="ETHEREX-LINEA-WETH-6600")
await adapter.initialize()

# Initialize MM analyzer
mm_analyzer = UnifiedMMAnalyzer(
    pair="LINEA-WETH",
    dex="etherex",
    max_inventory=100.0
)

# Stream ticks and generate signals
async for snapshot in adapter.stream_ticks():
    signal = mm_analyzer.process_tick_snapshot(snapshot)
    
    if signal.action in ["quote_tight", "quote_normal"]:
        # Place quotes
        place_order("bid", signal.bid_price)
        place_order("ask", signal.ask_price)
    elif signal.action == "pause":
        # Cancel all quotes
        cancel_all_orders()
```

#### 2. Cross-DEX Market Making (XEMM)

```python
from cross_dex_analytics import CrossDEXAnalyzer

# Initialize cross-DEX analyzer
cross_dex = CrossDEXAnalyzer(dexes=["lynex", "etherex", "nile"])

# Monitor all venues
for dex in ["lynex", "etherex", "nile"]:
    adapter = get_adapter(dex)
    snapshot = await adapter.capture_snapshot()
    cross_dex.update_snapshot(convert_to_dex_snapshot(snapshot))

# Detect arbitrage
arbs = cross_dex.detect_arbitrage("WETH-USDC", min_profit_bps=20)

for arb in arbs:
    if arb.est_net_profit_pct > 0.5:  # >0.5% after gas
        execute_arbitrage(arb)

# Get best execution
route = cross_dex.get_best_execution_route("WETH-USDC", "buy", 10.0)
execute_smart_routing(route)
```

#### 3. Redis Streaming Integration

```python
import redis.asyncio as redis
from linea_redis_streamer import LineaRedisStreamer

# Start streamer for Etherex
streamer = LineaRedisStreamer(
    pool_address="ETHEREX-LINEA-WETH-6600",
    pair_symbol="LINEA-WETH",
    redis_host="localhost"
)

await streamer.stream()  # Publishes to linea:etherex:linea-weth:ticks

# Subscribe in your MM bot
r = await redis.Redis()
pubsub = r.pubsub()
await pubsub.subscribe("linea:etherex:linea-weth:ticks")

async for message in pubsub.listen():
    snapshot = json.loads(message['data'])
    signal = mm_analyzer.process_tick_snapshot(snapshot)
    # Execute strategy
```

---

## 📊 Redis Channels

### Per-DEX Tick Streams
```
linea:lynex:{pair}:ticks
linea:etherex:{pair}:ticks
linea:nile:{pair}:ticks
linea:syncswap:{pair}:ticks
linea:kyber:{pair}:ticks
```

### Cross-DEX Arbitrage
```
linea:cross-dex:{pair}:arb
```

**Message Format:**
```json
{
  "type": "arbitrage_opportunity",
  "pair": "WETH-USDC",
  "buy_dex": "nile",
  "sell_dex": "etherex",
  "gross_profit_pct": 0.35,
  "net_profit_pct": 0.22,
  "size_available": 5.2,
  "timestamp": 1700000000
}
```

---

## 🎓 Integration with Sapient HRM & Hummingbot

### Sapient HRM (Automated Decision System)

```python
# Sapient HRM consumes MM signals
sapient_hrm.subscribe_to_redis("linea:*:*:ticks")

def on_mm_signal(signal: UnifiedMMSignal):
    if signal.confidence > 0.8:
        if signal.action == "quote_tight":
            hummingbot.update_spreads(signal.spread_bps * 0.8)
        elif signal.action == "pause":
            hummingbot.cancel_all_orders()
        elif signal.action == "rebalance_inventory":
            hummingbot.rebalance_inventory(target=0)
```

### Hummingbot MCP (Strategy Execution)

```yaml
# hummingbot/conf/avellaneda_linea.yml
strategy: avellaneda_market_making
exchange: linea_etherex
market: LINEA-WETH
gamma: 0.1
kappa: 1.5
leverage: 1
order_amount: 1.0

# Custom parameters from MM analytics
use_external_signals: true
redis_host: localhost
redis_channel: linea:etherex:linea-weth:ticks
```

---

## 📈 Performance Metrics

### Etherex Pool (LINEA-WETH-6600)
- **Liquidity:** ~$2.86M
- **Fee:** 0.66%
- **Block Time:** ~2s
- **Tick Spacing:** 132

### Expected Performance
- **Signal Latency:** ~2-4 seconds (Linea block time)
- **VPIN Update Frequency:** Every 50 volume bucket (~every few minutes)
- **Volatility Recalculation:** Every new OHLC candle (configurable)
- **Cross-DEX Arb Detection:** Every 5 seconds (configurable)

---

## 🧪 Testing & Validation

### 1. Test Individual Modules

```bash
# Test VPIN
python3 scripts/mm_analytics/vpin.py

# Test volatility estimators
python3 scripts/mm_analytics/volatility.py

# Test Avellaneda-Stoikov
python3 scripts/mm_analytics/avellaneda_stoikov.py

# Test orderflow
python3 scripts/mm_analytics/orderflow.py
```

### 2. Test DEX Adapters

```bash
# Test Etherex adapter
python3 -c "
from dex_adapters.etherex_adapter import EtherexAdapter
import asyncio

async def test():
    adapter = EtherexAdapter('ETHEREX-LINEA-WETH-6600')
    await adapter.initialize()
    snapshot = await adapter.capture_snapshot()
    print(snapshot.to_dict())

asyncio.run(test())
"
```

### 3. Integration Test

```bash
# Full pipeline test
python3 scripts/linea_integrated_pipeline.py \
  --pairs "LINEA-WETH" \
  --duration 300
```

---

## 🔧 Tuning Parameters

### For Conservative Market Making (Lower Risk)
```json
{
  "inventory": {"gamma": 0.15},
  "vpin": {"toxicity_thresholds": {"safe": 0.25}},
  "avellaneda_stoikov": {"gamma": 0.15, "k": 2.0}
}
```

### For Aggressive Market Making (Higher Returns)
```json
{
  "inventory": {"gamma": 0.05},
  "vpin": {"toxicity_thresholds": {"safe": 0.35}},
  "avellaneda_stoikov": {"gamma": 0.05, "k": 1.0}
}
```

---

## 🌟 Key Features

✅ **Multi-DEX Support** - 5 DEXes on Linea with unified interface  
✅ **Adverse Selection Protection** - VPIN toxicity monitoring  
✅ **Optimal Spreads** - Avellaneda-Stoikov with inventory management  
✅ **Price Impact Awareness** - Kyle's Lambda estimation  
✅ **Regime Detection** - Mean-reverting vs trending  
✅ **Cross-DEX Arbitrage** - Real-time opportunity detection  
✅ **Redis Streaming** - Real-time pub/sub integration  
✅ **Sapient HRM Ready** - Automated decision integration  
✅ **Hummingbot Compatible** - MCP strategy execution  

---

## 📞 Support & Next Steps

### Discover Pool Addresses

```bash
# Method 1: Use built-in discovery
python3 scripts/linea_data_collector.py --discover

# Method 2: Query subgraphs
curl -X POST https://api.goldsky.com/api/public/.../subgraphs/lynex/1.0.0/gn \
  -d '{"query":"{ pools(first:20,orderBy:volumeUSD,orderDirection:desc) { id token0{symbol} token1{symbol} }}"}'

# Method 3: DEX Screener
# Visit: https://dexscreener.com/linea
```

### Configure Your Pairs

1. Find pool addresses for your tokens (REX, FOXY, LINEA, EURE)
2. Update `scripts/config/multi_dex_config.json`
3. Start streaming: `python3 scripts/linea_integrated_pipeline.py`

### Production Deployment

1. Set up Redis: `docker run -d -p 6379:6379 redis:latest`
2. Configure Sapient HRM endpoint
3. Install Hummingbot with MCP integration
4. Start multi-DEX monitoring
5. Enable automated strategy execution

---

**Built for professional market making on Linea with institutional-grade analytics.**

Combines academic research (Avellaneda-Stoikov, Kyle, Easley-O'Hara VPIN) with practical DEX microstructure for automated, profitable market making.
