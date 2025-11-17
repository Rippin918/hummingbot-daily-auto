# Hummingbot Automation for Linea

Dockerized Hummingbot deployment with automatic daily updates, configured for market making and liquidity mining on Linea L2.

## 🎯 Features

- **Automated Updates**: Daily rebuild and restart at 6 AM
- **Linea Integration**: Native support for Linea RPC endpoints
- **Strategy Configs**: Pre-configured for Renzo R7 pairs
- **Risk Management**: Kill switches and inventory management
- **Monitoring**: Health checks and notifications
- **Backup System**: Automatic backups before updates
- **🤖 Sapient HRM Curator**: AI-powered liquidity monitoring for Linea Ignition rewards

## 🚀 Quick Start

### 1. Prerequisites

- Docker & Docker Compose installed
- Git configured
- Linea RPC access (public or Infura/Alchemy)

### 2. Setup

```bash
# Navigate to directory
cd hummingbot-auto

# Copy environment template
cp .env.example .env

# Edit .env with your keys
nano .env  # or vim, code, etc.
```

### 3. Start Hummingbot

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

## 📝 Configuration

### Environment Variables

Edit `.env` file with your settings:

```bash
# Linea RPC
LINEA_RPC_URL=https://rpc.linea.build

# Wallet (⚠️ NEVER commit this file!)
WALLET_PRIVATE_KEY=your_private_key_here

# Strategy
STRATEGY=pure_market_making
TRADING_PAIR=RENZO-USDC
```

See `.env.example` for all available options.

### Trading Strategies

Two pre-configured strategies:

1. **Pure Market Making** (`conf/pure_market_making_renzo.yml`)
   - Pair: RENZO-USDC
   - Spread: 0.5%
   - Order levels: 3
   - Inventory skew enabled

2. **Liquidity Mining** (`conf/liquidity_mining_r7.yml`)
   - Multiple R7 pairs
   - Wider spreads (1%)
   - Volatility management

### Customize Strategy

Edit config files in `conf/`:

```bash
nano conf/pure_market_making_renzo.yml
```

## 🔄 Daily Updates

### Automatic Updates

Cron job runs daily at 6 AM:

```bash
# Setup cron
crontab -e

# Add this line (replace PATH):
0 6 * * * cd /path/to/hummingbot-auto && ./daily_update.sh >> logs/cron.log 2>&1
```

See [CRON_SETUP.md](CRON_SETUP.md) for detailed instructions.

### Manual Update

```bash
# Standard update
./daily_update.sh

# Force rebuild
./daily_update.sh --force

# Skip backup
./daily_update.sh --skip-backup
```

## 📊 Monitoring

### View Logs

```bash
# Real-time logs
docker-compose logs -f

# Update logs
tail -f logs/daily_update_*.log

# Filter for errors
docker-compose logs | grep ERROR
```

### Health Check

```bash
# Check if healthy
docker inspect hummingbot-linea --format='{{.State.Health.Status}}'

# View health check logs
docker inspect hummingbot-linea --format='{{json .State.Health}}' | jq
```

### API Access

Hummingbot HTTP API (if enabled):
- URL: http://localhost:8080
- WebSocket: ws://localhost:8081

## 🔐 Security

### Protected Files

NEVER commit these files:
- `.env` - Contains private keys
- `certs/` - Wallet certificates
- `data/` - Trading data
- `logs/` - May contain sensitive info

### Backup Management

Backups are created before each update:
```bash
# Location
ls -lh backups/

# Restore backup
tar -xzf backups/backup_YYYYMMDD_HHMMSS.tar.gz
```

## 🛠️ Commands

### Docker Operations

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Restart
docker-compose restart

# Rebuild
docker-compose up -d --build --force-recreate

# Remove everything
docker-compose down -v
```

### Hummingbot CLI

```bash
# Enter container
docker exec -it hummingbot-linea bash

# Run hummingbot command
docker exec -it hummingbot-linea hummingbot status
```

## 🤖 Sapient HRM Liquidity Curator

**NEW**: Intelligent AI-powered curator for optimizing Linea Ignition rewards!

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure your wallet
cp .env.example .env
nano .env  # Add your WALLET_ADDRESS and PRIVATE_KEY

# Run the curator
./scripts/run_curator.sh
```

### Features

- **AI-Powered Decisions**: Uses Sapient HRM (Hierarchical Reasoning Model) for intelligent position management
- **Linea Ignition Optimized**: Specifically tuned for maximizing LXP-L rewards
- **Auto-Rebalancing**: Automatically rebalances positions based on market conditions
- **Risk Management**: Built-in stop-loss, drawdown limits, and IL monitoring
- **Multi-Pool Support**: Monitors and manages positions across multiple DEXes
- **Gas Optimization**: Batches transactions to minimize fees on Linea

### Configuration

Edit `conf/curator_config.yml` to customize:
- Position size limits and thresholds
- Risk management parameters
- Alert settings (Discord, Telegram)
- Monitoring intervals

For detailed documentation, see **[Curator Documentation](docs/CURATOR.md)**

## 📈 Strategies

### Pure Market Making

Best for:
- Liquid pairs
- Stable spreads
- Earning trading fees

Configuration highlights:
- `bid_spread`: 0.5%
- `ask_spread`: 0.5%
- `order_levels`: 3
- `inventory_skew_enabled`: true

### Liquidity Mining

Best for:
- Campaign participation
- Multiple pairs
- Lower maintenance

Configuration highlights:
- `spread`: 1.0%
- Multiple markets
- Volatility-based spread adjustment

## 🐛 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs

# Verify .env file
cat .env | grep -v "^#" | grep -v "^$"

# Test RPC connection
curl -X POST $LINEA_RPC_URL \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
```

### Update Script Fails

```bash
# Check permissions
ls -la daily_update.sh

# Make executable
chmod +x daily_update.sh

# Test manually
./daily_update.sh --skip-backup
```

### Connection Issues

```bash
# Test Linea RPC
docker exec hummingbot-linea curl https://rpc.linea.build

# Check DNS
docker exec hummingbot-linea ping -c 3 rpc.linea.build

# Verify network
docker network inspect hummingbot-auto_linea-network
```

### Out of Gas

```bash
# Check ETH balance (for gas)
# Ensure wallet has sufficient ETH for Linea gas fees

# Adjust gas settings in .env:
MAX_GAS_PRICE=50  # Increase if needed
```

## 📚 Additional Resources

- [Hummingbot Documentation](https://docs.hummingbot.org/)
- [Linea Documentation](https://docs.linea.build/)
- [Strategy Configurations](https://docs.hummingbot.org/strategies/)
- [CRON Setup Guide](CRON_SETUP.md)

## 🤝 Support

- GitHub Issues: [Create Issue](https://github.com/Rippin918/hummingbot-automation/issues)
- Discord: [Your Discord]
- Telegram: [Your Telegram]

## ⚠️ Disclaimer

Cryptocurrency trading involves substantial risk of loss. This software is provided as-is without warranties. Never trade with funds you cannot afford to lose. Always test strategies on testnet first.

---

**Repository**: [hummingbot-automation](https://github.com/Rippin918/hummingbot-automation)
**License**: MIT
**Maintained by**: Rippin918
