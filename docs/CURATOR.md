# Sapient HRM Liquidity Curator

**Intelligent liquidity monitoring and management for the Linea Ignition Rewards Program**

## 🎯 Overview

The Sapient HRM Liquidity Curator uses advanced AI models to monitor and optimize your liquidity positions on Linea, helping you maximize rewards from the Linea Ignition program.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Create and activate virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your credentials (IMPORTANT!)
nano .env  # or use your preferred editor
```

**Minimum required variables:**
- `WALLET_ADDRESS` - Your Linea wallet address
- `PRIVATE_KEY` - Your wallet private key (keep this secure!)
- `LINEA_RPC_URL` - RPC endpoint for Linea network
- `HUGGINGFACE_TOKEN` - For accessing AI models (optional but recommended)

### 3. Configure Curator Settings

Edit `conf/curator_config.yml` to customize:
- Position management preferences
- Risk thresholds
- Alert settings
- Linea Ignition program parameters

### 4. Run the Curator

**Option A: Using the launcher script (recommended)**
```bash
./scripts/run_curator.sh
```

**Option B: Direct Python execution**
```bash
python scripts/liquidity_curator.py
```

**Option C: With custom parameters**
```bash
# Custom check interval (seconds)
./scripts/run_curator.sh --interval 300

# Dry run mode (no real transactions)
./scripts/run_curator.sh --dry-run

# Verbose logging
./scripts/run_curator.sh --verbose
```

## 🤖 Sapient HRM Integration

The curator uses Sapient HRM (Hierarchical Reasoning Model) for intelligent decision-making:

### Key Features

1. **Adaptive Learning** - Learns from market conditions and past performance
2. **Risk Assessment** - Continuously evaluates position risks and market volatility
3. **Reward Optimization** - Maximizes Linea Ignition rewards through strategic positioning
4. **Autonomous Rebalancing** - Automatically rebalances positions when needed
5. **Multi-factor Analysis** - Considers APR, IL, volume, and rewards simultaneously

### How It Works

```
┌─────────────────┐
│ Market Data     │ ──┐
│ (Prices, Volume)│   │
└─────────────────┘   │
                      ▼
┌─────────────────┐   ┌──────────────┐   ┌─────────────────┐
│ Your Positions  │──▶│ Sapient HRM  │──▶│ Action Decision │
└─────────────────┘   │  AI Model    │   │ (Hold/Rebalance)│
                      └──────────────┘   └─────────────────┘
┌─────────────────┐   │
│ Linea Ignition  │───┘
│ Reward Data     │
└─────────────────┘
```

## 📊 Monitoring & Alerts

The curator provides real-time monitoring with configurable alerts:

### Alert Types
- 🔴 **Critical** - Positions at risk, immediate action required
- 🟡 **Warning** - Approaching thresholds, review recommended
- 🟢 **Info** - General status updates

### Notification Channels
- Console output (always enabled)
- Log files (`logs/curator.log`)
- Discord webhooks (configure in `curator_config.yml`)
- Telegram bot (configure in `.env`)

## 🛡️ Risk Management

The curator includes built-in risk management:

- **Stop Loss** - Auto-exit positions exceeding loss thresholds
- **Max Drawdown** - Monitors overall portfolio drawdown
- **Impermanent Loss Tracking** - Alerts when IL becomes significant
- **Price Impact Analysis** - Avoids trades with high slippage
- **Gas Optimization** - Batches transactions to minimize fees

## 📈 Linea Ignition Optimization

Specifically tuned for Linea Ignition rewards:

1. **LXP-L Reward Tracking** - Monitors earned Linea Experience Points
2. **Optimal Pool Selection** - Prioritizes pools with best reward multipliers
3. **Volume Requirements** - Ensures positions meet minimum volume thresholds
4. **Reward Compounding** - Automatically reinvests earned rewards
5. **Campaign Awareness** - Adapts to different Linea Ignition campaign phases

## 🔧 Advanced Configuration

### Custom Strategies

You can customize the curator's behavior in `conf/curator_config.yml`:

```yaml
strategy:
  prefer_stable_pairs: true  # Lower IL, steadier rewards
  focus_on_linea_native: true  # Native Linea tokens often have multipliers
  compound_rewards: true  # Auto-compound for exponential growth
  gas_optimization: true  # Save on fees
```

### Performance Tuning

```yaml
monitoring:
  check_interval: 300  # Check every 5 minutes (adjust based on needs)

sapient:
  confidence_threshold: 0.75  # Higher = more conservative decisions
  learning_mode: true  # Enable AI to adapt over time
```

## 📝 Logs & Data

- **Logs**: `logs/curator.log` - Detailed operation logs
- **Data**: `data/curator.db` - Historical performance data (if DB enabled)
- **Checkpoints**: `.curator_state/` - AI model checkpoints and learning data

## 🔐 Security Best Practices

1. **Never commit `.env` file** - It contains your private key!
2. **Use hardware wallet** - Consider integrating with Ledger/Trezor for production
3. **Start with dry-run mode** - Test before running with real funds
4. **Set conservative limits** - Start with smaller position sizes
5. **Monitor regularly** - Even with automation, check in periodically

## 🐛 Troubleshooting

### Common Issues

**"No module named 'torch'"**
```bash
pip install torch transformers huggingface-hub
```

**"RPC connection failed"**
- Check your `LINEA_RPC_URL` in `.env`
- Try alternative RPC: `https://linea-mainnet.infura.io`

**"Insufficient gas"**
- Ensure your wallet has ETH on Linea for gas fees
- Adjust gas settings in config if needed

**"Model download failed"**
- Set `HUGGINGFACE_TOKEN` in `.env`
- Check internet connection
- Try a different model in `curator_config.yml`

## 📚 Additional Resources

- [Linea Ignition Program](https://linea.build/ignition)
- [Hummingbot Documentation](https://docs.hummingbot.org)
- [Transformers Documentation](https://huggingface.co/docs/transformers)

## 🤝 Support

For issues specific to this curator setup:
1. Check logs in `logs/curator.log`
2. Review configuration in `conf/curator_config.yml`
3. Test with `--dry-run` flag first
4. Open an issue on the GitHub repository

---

**⚠️ Disclaimer**: This tool involves automated trading with real funds. Use at your own risk. Always start with small amounts and monitor performance closely. The Sapient HRM model is experimental and should be thoroughly tested before production use.
