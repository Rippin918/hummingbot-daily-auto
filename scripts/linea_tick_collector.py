#!/usr/bin/env python3
"""
Linea Lynex Tick Stream Collector
Real-time tick-level orderbook data collection from Lynex pool contracts
Matches existing Uniswap V3 monitor infrastructure for unified analysis
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import BlockNotFound
import aiohttp


class LynexTickCollector:
    """
    Collects tick-level data from Lynex pool contracts on Linea
    Captures orderbook state changes block-by-block for micropulse analysis
    """

    # Linea network configuration
    LINEA_RPC = "https://rpc.linea.build"
    LINEA_CHAIN_ID = 59144
    BLOCK_TIME = 2.0  # ~2 seconds on Linea

    # Tick mathematics (Uniswap V3 compatible)
    Q96 = 2 ** 96
    MIN_TICK = -887272
    MAX_TICK = 887272

    def __init__(
        self,
        pool_address: str,
        rpc_url: str = None,
        tick_range: int = 200,  # Ticks around current price to monitor
        data_dir: str = "data/ticks"
    ):
        self.pool_address = Web3.to_checksum_address(pool_address)
        self.rpc_url = rpc_url or self.LINEA_RPC
        self.tick_range = tick_range
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to Linea RPC: {self.rpc_url}")

        # Load pool contract ABI
        abi_path = Path(__file__).parent / "abis" / "lynex_pool_abi.json"
        with open(abi_path, 'r') as f:
            pool_abi = json.load(f)

        self.pool_contract = self.w3.eth.contract(
            address=self.pool_address,
            abi=pool_abi
        )

        # Pool metadata
        self.token0 = None
        self.token1 = None
        self.fee = None
        self.tick_spacing = None
        self.decimals0 = None
        self.decimals1 = None

        # State tracking
        self.last_block = None
        self.last_tick = None
        self.snapshots = []

    async def initialize(self):
        """Initialize pool metadata and token information"""
        print(f"Initializing Lynex pool: {self.pool_address}")

        # Get pool metadata
        self.token0 = self.pool_contract.functions.token0().call()
        self.token1 = self.pool_contract.functions.token1().call()
        self.fee = self.pool_contract.functions.fee().call()
        self.tick_spacing = self.pool_contract.functions.tickSpacing().call()

        # Get token decimals (using ERC20 ABI)
        erc20_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            }
        ]

        token0_contract = self.w3.eth.contract(address=self.token0, abi=erc20_abi)
        token1_contract = self.w3.eth.contract(address=self.token1, abi=erc20_abi)

        self.decimals0 = token0_contract.functions.decimals().call()
        self.decimals1 = token1_contract.functions.decimals().call()

        symbol0 = token0_contract.functions.symbol().call()
        symbol1 = token1_contract.functions.symbol().call()

        print(f"  Pool: {symbol0}/{symbol1}")
        print(f"  Fee: {self.fee / 10000}%")
        print(f"  Tick Spacing: {self.tick_spacing}")
        print(f"  Token0: {self.token0} (decimals: {self.decimals0})")
        print(f"  Token1: {self.token1} (decimals: {self.decimals1})")

    def get_slot0(self) -> Dict:
        """Get current pool state (slot0)"""
        slot0 = self.pool_contract.functions.slot0().call()
        return {
            "sqrtPriceX96": slot0[0],
            "tick": slot0[1],
            "observationIndex": slot0[2],
            "observationCardinality": slot0[3],
            "observationCardinalityNext": slot0[4],
            "feeProtocol": slot0[5],
            "unlocked": slot0[6]
        }

    def get_liquidity(self) -> int:
        """Get current pool liquidity"""
        return self.pool_contract.functions.liquidity().call()

    def get_tick_data(self, tick: int) -> Dict:
        """Get liquidity data for a specific tick"""
        try:
            tick_data = self.pool_contract.functions.ticks(tick).call()
            return {
                "tick": tick,
                "liquidityGross": tick_data[0],
                "liquidityNet": tick_data[1],
                "feeGrowthOutside0X128": tick_data[2],
                "feeGrowthOutside1X128": tick_data[3],
                "tickCumulativeOutside": tick_data[4],
                "secondsPerLiquidityOutsideX128": tick_data[5],
                "secondsOutside": tick_data[6],
                "initialized": tick_data[7]
            }
        except Exception:
            # Tick not initialized
            return {
                "tick": tick,
                "liquidityGross": 0,
                "liquidityNet": 0,
                "initialized": False
            }

    def get_tick_bitmap(self, word_position: int) -> int:
        """Get tick bitmap for a word position"""
        try:
            return self.pool_contract.functions.tickBitmap(word_position).call()
        except Exception:
            return 0

    def sqrt_price_to_price(self, sqrt_price_x96: int) -> float:
        """Convert sqrtPriceX96 to human-readable price"""
        price = (sqrt_price_x96 / self.Q96) ** 2
        # Adjust for token decimals
        decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
        return price * decimal_adjustment

    def tick_to_price(self, tick: int) -> float:
        """Convert tick to price"""
        price = 1.0001 ** tick
        decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
        return price * decimal_adjustment

    def get_tick_range_liquidity(self, center_tick: int, range_ticks: int = None) -> Dict[int, Dict]:
        """
        Get liquidity distribution around current tick
        This is the key method for orderbook reconstruction
        """
        if range_ticks is None:
            range_ticks = self.tick_range

        # Align to tick spacing
        aligned_center = (center_tick // self.tick_spacing) * self.tick_spacing

        # Calculate tick range
        lower_tick = aligned_center - (range_ticks * self.tick_spacing)
        upper_tick = aligned_center + (range_ticks * self.tick_spacing)

        # Clamp to valid tick range
        lower_tick = max(lower_tick, self.MIN_TICK)
        upper_tick = min(upper_tick, self.MAX_TICK)

        # Collect tick data
        tick_liquidity = {}
        current_tick = lower_tick

        while current_tick <= upper_tick:
            tick_data = self.get_tick_data(current_tick)
            if tick_data["initialized"] and tick_data["liquidityGross"] > 0:
                tick_data["price"] = self.tick_to_price(current_tick)
                tick_liquidity[current_tick] = tick_data
            current_tick += self.tick_spacing

        return tick_liquidity

    async def capture_snapshot(self) -> Dict:
        """
        Capture complete orderbook snapshot at current block
        Format matches existing Uniswap V3 monitor for unified analysis
        """
        block = self.w3.eth.block_number
        timestamp = int(time.time())

        # Get current pool state
        slot0 = self.get_slot0()
        liquidity = self.get_liquidity()
        current_tick = slot0["tick"]
        sqrt_price = slot0["sqrtPriceX96"]
        current_price = self.sqrt_price_to_price(sqrt_price)

        # Get tick distribution
        tick_liquidity = self.get_tick_range_liquidity(current_tick, self.tick_range)

        # Build snapshot
        snapshot = {
            "timestamp": timestamp,
            "block": block,
            "pool": self.pool_address,
            "token0": self.token0,
            "token1": self.token1,
            "current_tick": current_tick,
            "sqrtPriceX96": str(sqrt_price),
            "price": current_price,
            "liquidity": str(liquidity),
            "tick_liquidity": {
                str(tick): {
                    "liquidityGross": str(data["liquidityGross"]),
                    "liquidityNet": str(data["liquidityNet"]),
                    "price": data["price"],
                    "initialized": data["initialized"]
                }
                for tick, data in tick_liquidity.items()
            },
            "metadata": {
                "tick_spacing": self.tick_spacing,
                "fee": self.fee,
                "decimals0": self.decimals0,
                "decimals1": self.decimals1
            }
        }

        # Track state changes
        if self.last_tick is not None and current_tick != self.last_tick:
            snapshot["tick_change"] = current_tick - self.last_tick

        self.last_tick = current_tick
        self.last_block = block
        self.snapshots.append(snapshot)

        return snapshot

    async def stream_ticks(self, duration_seconds: int = None, callback=None):
        """
        Stream tick data block-by-block
        Similar to your existing Uniswap V3 monitor
        """
        await self.initialize()

        print(f"\n{'='*70}")
        print(f"Starting tick stream collection")
        print(f"Pool: {self.pool_address}")
        print(f"Tick range: ±{self.tick_range} ticks")
        print(f"{'='*70}\n")

        start_time = time.time()
        snapshot_count = 0

        try:
            while True:
                # Check duration limit
                if duration_seconds and (time.time() - start_time) > duration_seconds:
                    break

                # Capture snapshot
                snapshot = await self.capture_snapshot()
                snapshot_count += 1

                # Log progress
                print(f"[{datetime.fromtimestamp(snapshot['timestamp']).strftime('%H:%M:%S')}] "
                      f"Block {snapshot['block']} | "
                      f"Tick: {snapshot['current_tick']} | "
                      f"Price: {snapshot['price']:.6f} | "
                      f"Liquidity: {int(snapshot['liquidity']):,} | "
                      f"Active Ticks: {len(snapshot['tick_liquidity'])}")

                # Execute callback (for Redis streaming)
                if callback:
                    await callback(snapshot)

                # Wait for next block (~2 seconds on Linea)
                await asyncio.sleep(self.BLOCK_TIME)

        except KeyboardInterrupt:
            print("\n\nStopping tick stream...")
        finally:
            print(f"\nCollected {snapshot_count} snapshots over {time.time() - start_time:.1f}s")
            return self.snapshots

    def save_snapshots(self, filename: str = None):
        """Save collected snapshots to JSON file"""
        if not self.snapshots:
            print("No snapshots to save")
            return None

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lynex_ticks_{self.pool_address[:8]}_{timestamp}.json"

        filepath = self.data_dir / filename

        data = {
            "pool": self.pool_address,
            "token0": self.token0,
            "token1": self.token1,
            "tick_spacing": self.tick_spacing,
            "fee": self.fee,
            "collection_start": self.snapshots[0]["timestamp"],
            "collection_end": self.snapshots[-1]["timestamp"],
            "snapshot_count": len(self.snapshots),
            "snapshots": self.snapshots
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"✓ Saved {len(self.snapshots)} snapshots to {filepath}")
        return filepath


async def main():
    """Example usage"""
    import argparse

    parser = argparse.ArgumentParser(description="Collect tick-level data from Lynex pools")
    parser.add_argument("--pool", type=str, required=True, help="Lynex pool contract address")
    parser.add_argument("--rpc", type=str, help="Linea RPC URL (default: public RPC)")
    parser.add_argument("--duration", type=int, default=600, help="Collection duration in seconds (default: 600)")
    parser.add_argument("--tick-range", type=int, default=200, help="Ticks to monitor around current price (default: 200)")
    parser.add_argument("--output", type=str, help="Output filename")
    parser.add_argument("--data-dir", type=str, default="data/ticks", help="Data directory")

    args = parser.parse_args()

    # Initialize collector
    collector = LynexTickCollector(
        pool_address=args.pool,
        rpc_url=args.rpc,
        tick_range=args.tick_range,
        data_dir=args.data_dir
    )

    # Stream ticks
    snapshots = await collector.stream_ticks(duration_seconds=args.duration)

    # Save results
    collector.save_snapshots(filename=args.output)

    print("\n✓ Tick collection complete")


if __name__ == "__main__":
    asyncio.run(main())
