#!/usr/bin/env python3
"""
Lynex DEX Adapter - Uniswap V3 Style Concentrated Liquidity
Primary DEX on Linea for market making
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from web3 import Web3

from .base_adapter import BaseDEXAdapter, SwapEvent, TickSnapshot


class LynexAdapter(BaseDEXAdapter):
    """
    Lynex adapter for Uniswap V3-style concentrated liquidity pools
    """

    # Tick mathematics
    Q96 = 2 ** 96
    MIN_TICK = -887272
    MAX_TICK = 887272

    @property
    def dex_name(self) -> str:
        return "lynex"

    @property
    def dex_type(self) -> str:
        return "uniswap_v3"

    def __init__(self, pool_address: str, rpc_url: str = None, w3: Optional[Web3] = None):
        super().__init__(pool_address, rpc_url, w3)

        # Load ABI
        abi_path = Path(__file__).parent.parent / "abis" / "lynex_pool_abi.json"
        with open(abi_path, 'r') as f:
            pool_abi = json.load(f)

        self.pool_contract = self.w3.eth.contract(
            address=self.pool_address,
            abi=pool_abi
        )

        self.tick_spacing = None

    async def initialize(self):
        """Initialize pool metadata"""
        # Get token addresses
        self.token0 = self.pool_contract.functions.token0().call()
        self.token1 = self.pool_contract.functions.token1().call()
        self.fee = self.pool_contract.functions.fee().call()
        self.tick_spacing = self.pool_contract.functions.tickSpacing().call()

        # Get token metadata
        token0_contract = self.get_token_contract(self.token0)
        token1_contract = self.get_token_contract(self.token1)

        self.decimals0 = token0_contract.functions.decimals().call()
        self.decimals1 = token1_contract.functions.decimals().call()
        self.symbol0 = token0_contract.functions.symbol().call()
        self.symbol1 = token1_contract.functions.symbol().call()

    async def get_current_tick(self) -> int:
        """Get current tick from slot0"""
        slot0 = self.pool_contract.functions.slot0().call()
        return slot0[1]  # tick is second element

    async def get_current_price(self) -> float:
        """Get current price from sqrtPriceX96"""
        slot0 = self.pool_contract.functions.slot0().call()
        sqrt_price_x96 = slot0[0]
        return self.sqrt_price_to_price(sqrt_price_x96)

    async def get_liquidity(self) -> int:
        """Get current active liquidity"""
        return self.pool_contract.functions.liquidity().call()

    async def get_tick_data(self, tick: int) -> Optional[Dict]:
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
            return {
                "tick": tick,
                "liquidityGross": 0,
                "liquidityNet": 0,
                "initialized": False
            }

    async def get_liquidity_distribution(
        self,
        center_tick: Optional[int] = None,
        tick_range: int = 200
    ) -> Dict[int, Dict]:
        """Get liquidity distribution around current tick"""
        if center_tick is None:
            center_tick = await self.get_current_tick()

        # Align to tick spacing
        aligned_center = (center_tick // self.tick_spacing) * self.tick_spacing

        # Calculate range
        lower_tick = max(aligned_center - (tick_range * self.tick_spacing), self.MIN_TICK)
        upper_tick = min(aligned_center + (tick_range * self.tick_spacing), self.MAX_TICK)

        # Collect tick data
        tick_liquidity = {}
        current_tick = lower_tick

        while current_tick <= upper_tick:
            tick_data = await self.get_tick_data(current_tick)
            if tick_data["initialized"] and tick_data["liquidityGross"] > 0:
                tick_data["price"] = self.tick_to_price(current_tick)
                tick_liquidity[current_tick] = tick_data
            current_tick += self.tick_spacing

        return tick_liquidity

    async def get_recent_swaps(
        self,
        num_swaps: int = 100,
        from_block: Optional[int] = None
    ) -> List[SwapEvent]:
        """Get recent swap events"""
        if from_block is None:
            current_block = self.w3.eth.block_number
            from_block = max(0, current_block - 1000)  # Last ~1000 blocks

        # Get Swap events
        swap_filter = self.pool_contract.events.Swap.create_filter(
            fromBlock=from_block,
            toBlock='latest'
        )

        events = swap_filter.get_all_entries()
        swap_events = []

        for event in events[-num_swaps:]:
            args = event['args']
            block_number = event['blockNumber']
            block = self.w3.eth.get_block(block_number)

            # Determine side
            amount0 = args['amount0']
            amount1 = args['amount1']
            side = "buy" if amount0 < 0 else "sell"

            swap_event = SwapEvent(
                timestamp=block['timestamp'],
                block=block_number,
                tx_hash=event['transactionHash'].hex(),
                sender=args['sender'],
                amount0=amount0,
                amount1=amount1,
                sqrt_price_x96=args['sqrtPriceX96'],
                tick=args['tick'],
                liquidity=args['liquidity'],
                price=self.sqrt_price_to_price(args['sqrtPriceX96']),
                side=side
            )
            swap_events.append(swap_event)

        return swap_events

    async def capture_snapshot(self) -> TickSnapshot:
        """Capture complete orderbook snapshot"""
        block = self.w3.eth.block_number
        timestamp = await self.get_block_timestamp(block)

        # Get current state
        current_tick = await self.get_current_tick()
        current_price = await self.get_current_price()
        liquidity = await self.get_liquidity()

        # Get liquidity distribution
        tick_liquidity = await self.get_liquidity_distribution(current_tick)

        # Get slot0 for metadata
        slot0 = self.pool_contract.functions.slot0().call()

        snapshot = TickSnapshot(
            timestamp=timestamp,
            block=block,
            dex=self.dex_name,
            pool=self.pool_address,
            token0=self.token0,
            token1=self.token1,
            current_price=current_price,
            current_tick=current_tick,
            liquidity=liquidity,
            tick_liquidity=tick_liquidity,
            metadata={
                "sqrtPriceX96": str(slot0[0]),
                "observationIndex": slot0[2],
                "observationCardinality": slot0[3],
                "feeProtocol": slot0[5],
                "tick_spacing": self.tick_spacing,
                "fee": self.fee,
                "decimals0": self.decimals0,
                "decimals1": self.decimals1,
                "symbol0": self.symbol0,
                "symbol1": self.symbol1
            }
        )

        return snapshot

    async def subscribe_to_swaps(self, callback):
        """
        Subscribe to real-time swap events
        Note: This requires an async event loop and WebSocket connection
        """
        # Create event filter
        event_filter = self.pool_contract.events.Swap.create_filter(fromBlock='latest')

        while True:
            for event in event_filter.get_new_entries():
                args = event['args']
                block_number = event['blockNumber']
                timestamp = await self.get_block_timestamp(block_number)

                # Determine side
                amount0 = args['amount0']
                side = "buy" if amount0 < 0 else "sell"

                swap_event = SwapEvent(
                    timestamp=timestamp,
                    block=block_number,
                    tx_hash=event['transactionHash'].hex(),
                    sender=args['sender'],
                    amount0=amount0,
                    amount1=args['amount1'],
                    sqrt_price_x96=args['sqrtPriceX96'],
                    tick=args['tick'],
                    liquidity=args['liquidity'],
                    price=self.sqrt_price_to_price(args['sqrtPriceX96']),
                    side=side
                )

                await callback(swap_event)

            # Wait a bit before checking again
            import asyncio
            await asyncio.sleep(2)  # Linea block time
