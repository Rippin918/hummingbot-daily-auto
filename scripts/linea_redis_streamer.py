#!/usr/bin/env python3
"""
Linea Redis Pub/Sub Streamer
Streams Lynex tick data to Redis channels for real-time consumption
Integrates with existing Uniswap V3/EtherEx monitor infrastructure
"""

import asyncio
import json
import time
from typing import Dict, Optional
from datetime import datetime

import redis.asyncio as redis
from linea_tick_collector import LynexTickCollector


class LineaRedisStreamer:
    """
    Streams Lynex tick data to Redis pub/sub channels
    Channel format: linea:lynex:{pair}:ticks
    Message format matches existing Coulter analysis pipeline
    """

    def __init__(
        self,
        pool_address: str,
        pair_symbol: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        tick_range: int = 200,
        rpc_url: Optional[str] = None
    ):
        self.pool_address = pool_address
        self.pair_symbol = pair_symbol
        self.tick_range = tick_range

        # Redis configuration
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password
        self.redis_client = None

        # Channel naming convention
        self.channel = f"linea:lynex:{pair_symbol.lower()}:ticks"

        # Initialize tick collector
        self.collector = LynexTickCollector(
            pool_address=pool_address,
            rpc_url=rpc_url,
            tick_range=tick_range,
            data_dir="data/ticks"
        )

        # Statistics
        self.messages_published = 0
        self.start_time = None

    async def connect_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = await redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=True
            )
            await self.redis_client.ping()
            print(f"✓ Connected to Redis at {self.redis_host}:{self.redis_port}")
            print(f"  Publishing to channel: {self.channel}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")

    async def disconnect_redis(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            print("✓ Disconnected from Redis")

    async def publish_snapshot(self, snapshot: Dict):
        """
        Publish tick snapshot to Redis channel
        Format matches existing monitor pipeline for unified Coulter analysis
        """
        if not self.redis_client:
            raise RuntimeError("Redis client not connected. Call connect_redis() first.")

        # Build message matching Coulter analysis format
        message = {
            "type": "tick_snapshot",
            "source": "lynex",
            "network": "linea",
            "pair": self.pair_symbol,
            "pool": snapshot["pool"],
            "timestamp": snapshot["timestamp"],
            "block": snapshot["block"],
            "orderbook": {
                "current_tick": snapshot["current_tick"],
                "current_price": snapshot["price"],
                "sqrtPriceX96": snapshot["sqrtPriceX96"],
                "total_liquidity": snapshot["liquidity"],
                "tick_distribution": snapshot["tick_liquidity"],
                "tick_spacing": snapshot["metadata"]["tick_spacing"]
            },
            "metadata": snapshot["metadata"]
        }

        # Add tick change if available (for velocity calculation)
        if "tick_change" in snapshot:
            message["tick_change"] = snapshot["tick_change"]

        # Publish to channel
        try:
            await self.redis_client.publish(
                self.channel,
                json.dumps(message)
            )
            self.messages_published += 1

            # Also store latest snapshot in Redis key for subscribers
            await self.redis_client.setex(
                f"{self.channel}:latest",
                60,  # 60 second TTL
                json.dumps(message)
            )

        except Exception as e:
            print(f"Error publishing to Redis: {e}")

    async def stream(self, duration_seconds: Optional[int] = None):
        """
        Start streaming tick data to Redis
        Runs continuously until stopped or duration expires
        """
        await self.connect_redis()
        await self.collector.initialize()

        self.start_time = time.time()

        print(f"\n{'='*70}")
        print(f"Linea Redis Streamer - ACTIVE")
        print(f"{'='*70}")
        print(f"Pool:    {self.pool_address}")
        print(f"Pair:    {self.pair_symbol}")
        print(f"Channel: {self.channel}")
        print(f"Range:   ±{self.tick_range} ticks")
        if duration_seconds:
            print(f"Duration: {duration_seconds}s")
        print(f"{'='*70}\n")

        try:
            await self.collector.stream_ticks(
                duration_seconds=duration_seconds,
                callback=self.publish_snapshot
            )
        except KeyboardInterrupt:
            print("\n\nStopping stream...")
        finally:
            elapsed = time.time() - self.start_time
            rate = self.messages_published / elapsed if elapsed > 0 else 0

            print(f"\n{'='*70}")
            print(f"Stream Statistics")
            print(f"{'='*70}")
            print(f"Duration:           {elapsed:.1f}s")
            print(f"Messages published: {self.messages_published}")
            print(f"Publish rate:       {rate:.2f} msg/s")
            print(f"Snapshots saved:    {len(self.collector.snapshots)}")
            print(f"{'='*70}\n")

            await self.disconnect_redis()

    async def subscribe_test(self, duration_seconds: int = 10):
        """
        Test subscriber - verify messages are being published correctly
        Useful for debugging and integration testing
        """
        await self.connect_redis()

        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(self.channel)

        print(f"\n{'='*70}")
        print(f"Test Subscriber - Listening to {self.channel}")
        print(f"{'='*70}\n")

        start_time = time.time()
        message_count = 0

        try:
            async for message in pubsub.listen():
                if time.time() - start_time > duration_seconds:
                    break

                if message["type"] == "message":
                    data = json.loads(message["data"])
                    message_count += 1

                    print(f"[{datetime.fromtimestamp(data['timestamp']).strftime('%H:%M:%S')}] "
                          f"Block {data['block']} | "
                          f"Tick: {data['orderbook']['current_tick']} | "
                          f"Price: {data['orderbook']['current_price']:.6f} | "
                          f"Active Ticks: {len(data['orderbook']['tick_distribution'])}")

        except KeyboardInterrupt:
            print("\nStopping subscriber...")
        finally:
            await pubsub.unsubscribe(self.channel)
            await self.disconnect_redis()
            print(f"\n✓ Received {message_count} messages")


async def multi_pool_streamer(pools: list, duration_seconds: Optional[int] = None):
    """
    Stream multiple Lynex pools simultaneously
    Each pool publishes to its own channel
    """
    streamers = [
        LineaRedisStreamer(
            pool_address=pool["address"],
            pair_symbol=pool["symbol"],
            tick_range=pool.get("tick_range", 200),
            redis_host=pool.get("redis_host", "localhost"),
            redis_port=pool.get("redis_port", 6379),
            rpc_url=pool.get("rpc_url")
        )
        for pool in pools
    ]

    print(f"Starting {len(streamers)} parallel streamers...")

    tasks = [streamer.stream(duration_seconds) for streamer in streamers]
    await asyncio.gather(*tasks)


async def main():
    """CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description="Stream Lynex tick data to Redis")
    parser.add_argument("--pool", type=str, required=True, help="Lynex pool address")
    parser.add_argument("--pair", type=str, required=True, help="Pair symbol (e.g. WETH-USDC)")
    parser.add_argument("--redis-host", type=str, default="localhost", help="Redis host")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port")
    parser.add_argument("--redis-password", type=str, help="Redis password")
    parser.add_argument("--redis-db", type=int, default=0, help="Redis database")
    parser.add_argument("--rpc", type=str, help="Linea RPC URL")
    parser.add_argument("--duration", type=int, help="Stream duration in seconds (default: infinite)")
    parser.add_argument("--tick-range", type=int, default=200, help="Tick range to monitor")
    parser.add_argument("--test-subscribe", action="store_true", help="Run subscriber test")

    args = parser.parse_args()

    streamer = LineaRedisStreamer(
        pool_address=args.pool,
        pair_symbol=args.pair,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        redis_password=args.redis_password,
        tick_range=args.tick_range,
        rpc_url=args.rpc
    )

    if args.test_subscribe:
        await streamer.subscribe_test(duration_seconds=args.duration or 10)
    else:
        await streamer.stream(duration_seconds=args.duration)


if __name__ == "__main__":
    asyncio.run(main())
