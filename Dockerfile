# Hummingbot Docker Image with Linea CLOB Support
# Pulls latest hummingbot image daily for updates

FROM hummingbot/hummingbot:latest

# Set working directory
WORKDIR /home/hummingbot

# Install additional dependencies for Linea integration
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Linea-specific dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    web3>=6.0.0 \
    eth-account>=0.9.0 \
    python-dotenv>=1.0.0 \
    requests>=2.31.0

# Copy strategy configurations
COPY ./conf /home/hummingbot/conf

# Copy custom scripts
COPY ./scripts /home/hummingbot/scripts

# Expose Hummingbot ports
# 8080: HTTP API
# 8081: WebSocket
EXPOSE 8080 8081

# Health check to ensure bot is responsive
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/status || exit 1

# Set entrypoint to run hummingbot
ENTRYPOINT ["./bin/hummingbot_quickstart.py"]
