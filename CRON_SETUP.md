# Cron Setup for Daily Hummingbot Updates

## Overview
This guide sets up automatic daily updates for Hummingbot at 6:00 AM.

## Prerequisites
- Docker and docker-compose installed
- Hummingbot repository cloned and configured
- Script permissions: `chmod +x daily_update.sh`

## Cron Configuration

### Step 1: Open Crontab Editor
```bash
crontab -e
```

### Step 2: Add Daily Update Job
Add the following line to run the update script daily at 6:00 AM:

```cron
# Hummingbot Daily Update - Runs at 6:00 AM every day
0 6 * * * cd /path/to/crypto-trading-workspace/hummingbot-auto && ./daily_update.sh >> logs/cron.log 2>&1

# Optional: Run with force rebuild on Sundays at 6:00 AM
0 6 * * 0 cd /path/to/crypto-trading-workspace/hummingbot-auto && ./daily_update.sh --force >> logs/cron.log 2>&1
```

**Important:** Replace `/path/to/crypto-trading-workspace/hummingbot-auto` with your actual path:
```bash
# Get full path
pwd
# Then use that in crontab
```

### Step 3: Alternative Schedules

**Every 12 hours (6 AM and 6 PM):**
```cron
0 6,18 * * * cd /path/to/crypto-trading-workspace/hummingbot-auto && ./daily_update.sh
```

**Weekly on Sunday at 6 AM:**
```cron
0 6 * * 0 cd /path/to/crypto-trading-workspace/hummingbot-auto && ./daily_update.sh --force
```

**Multiple times per day (every 8 hours):**
```cron
0 */8 * * * cd /path/to/crypto-trading-workspace/hummingbot-auto && ./daily_update.sh
```

### Step 4: Verify Cron Job
```bash
# List all cron jobs
crontab -l

# Check cron service is running
# macOS:
sudo launchctl list | grep cron

# Linux:
systemctl status cron
```

## Monitoring and Logs

### View Update Logs
```bash
# Real-time log monitoring
tail -f logs/daily_update_*.log

# View all updates today
ls -lh logs/daily_update_$(date +%Y%m%d)*.log

# Check cron execution log
tail -f logs/cron.log
```

### Check Last Update Status
```bash
# View most recent log file
cat logs/daily_update_$(ls -t logs/daily_update_*.log | head -1)

# Check if containers are running
docker-compose ps
```

## Notifications (Optional)

### Discord Webhook Integration
Add to your `.env` file:
```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN
```

The script will automatically send notifications on success/failure.

### Telegram Integration
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Troubleshooting

### Cron Not Running
```bash
# macOS: Check if cron has Full Disk Access
# System Preferences > Security & Privacy > Privacy > Full Disk Access > Add /usr/sbin/cron

# Linux: Check cron service
sudo systemctl status cron
sudo systemctl restart cron
```

### Script Errors
```bash
# Test script manually
./daily_update.sh

# Check script permissions
ls -la daily_update.sh
# Should show: -rwxr-xr-x

# Fix permissions if needed
chmod +x daily_update.sh
```

### Environment Variables Not Loading
Cron runs with limited environment. Add to crontab:
```cron
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
DOCKER_HOST=unix:///var/run/docker.sock

0 6 * * * cd /path/to/hummingbot-auto && ./daily_update.sh
```

### Docker Permission Issues
```bash
# Add user to docker group (Linux)
sudo usermod -aG docker $USER

# Verify docker access
docker ps
```

## Backup Management

Backups are automatically created before each update:
- Location: `backups/`
- Retention: 7 days (older backups auto-deleted)
- Skip backup: Use `--skip-backup` flag

### Manual Backup
```bash
# Create immediate backup
tar -czf backups/manual_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
    conf/ data/ logs/ .env
```

### Restore from Backup
```bash
# List available backups
ls -lh backups/

# Restore specific backup
tar -xzf backups/backup_YYYYMMDD_HHMMSS.tar.gz
```

## Security Considerations

1. **Protect .env file**: Never commit to git
2. **Limit cron log access**:
   ```bash
   chmod 600 logs/cron.log
   ```
3. **Secure backups**: Backups contain sensitive data
4. **Monitor failed updates**: Set up alerts for failures

## Testing

### Test Cron Entry
```bash
# Run at next minute for testing
# If current time is 10:30, set cron for 10:31
31 10 * * * cd /path/to/hummingbot-auto && ./daily_update.sh --skip-backup

# Remove after testing
crontab -e  # Delete the test line
```

### Manual Test Run
```bash
# Test update process without waiting for cron
./daily_update.sh --skip-backup

# Test with force rebuild
./daily_update.sh --force --skip-backup
```

## Advanced: Using systemd Timer (Linux Alternative)

For more robust scheduling on Linux:

### Create Service File
`/etc/systemd/system/hummingbot-update.service`:
```ini
[Unit]
Description=Hummingbot Daily Update
After=docker.service

[Service]
Type=oneshot
User=YOUR_USER
WorkingDirectory=/path/to/hummingbot-auto
ExecStart=/path/to/hummingbot-auto/daily_update.sh
StandardOutput=append:/path/to/hummingbot-auto/logs/systemd.log
StandardError=append:/path/to/hummingbot-auto/logs/systemd_error.log
```

### Create Timer File
`/etc/systemd/system/hummingbot-update.timer`:
```ini
[Unit]
Description=Hummingbot Daily Update Timer

[Timer]
OnCalendar=daily
OnCalendar=06:00
Persistent=true

[Install]
WantedBy=timers.target
```

### Enable Timer
```bash
sudo systemctl daemon-reload
sudo systemctl enable hummingbot-update.timer
sudo systemctl start hummingbot-update.timer

# Check status
systemctl status hummingbot-update.timer
systemctl list-timers
```
