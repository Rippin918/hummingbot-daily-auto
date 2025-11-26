#!/usr/bin/env python3
"""
SyncSwap Adapter - zkSync-Style AMM on Linea
Implements classic AMM (xy=k) logic with simulated tick distribution
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional
from web3 import Web3

from .base_adapter import BaseDEXAdapter, SwapEvent, TickSnapshot


class SyncSwapAdapter(BaseDEXAdapter):
    """SyncSwap - Classic AMM + Stable pools using constant product formula (xy=k)"""

    def __init__(self, pool_address: str, rpc_url: str = None, w3: Optional[Web3] = None):
        super().__init__(pool_address, rpc_url, w3)

        # Load ABI
        abi_path = Path(__file__).parent.parent / "abis" / "syncswap_pool_abi.json"
        with open(abi_path, 'r') as f:
            pool_abi = json.load(f)

        self.pool_contract = self.w3.eth.contract(
            address=self.pool_address,
            abi=pool_abi
        )

        # Cache for reserves
        self._reserve0 = None
        self._reserve1 = None

    @property
    def dex_name(self) -> str:
        return "syncswap"

    @property
    def dex_type(self) -> str:
        return "classic_amm"

    async def initialize(self):
        """Initialize pool metadata"""
        # Get token addresses
        self.token0 = self.pool_contract.functions.token0().call()
        self.token1 = self.pool_contract.functions.token1().call()

        # Get swap fee (SyncSwap uses basis points, typically 30 = 0.3%)
        try:
            self.fee = self.pool_contract.functions.getSwapFee().call()
        except Exception:
            self.fee = 30  # Default 0.3%

        # Get token metadata
        token0_contract = self.get_token_contract(self.token0)
        token1_contract = self.get_token_contract(self.token1)

        self.decimals0 = token0_contract.functions.decimals().call()
        self.decimals1 = token1_contract.functions.decimals().call()
        self.symbol0 = token0_contract.functions.symbol().call()
        self.symbol1 = token1_contract.functions.symbol().call()

    async def _get_reserves(self) -> tuple:
        """Get current reserves from the pool"""
        reserves = self.pool_contract.functions.getReserves().call()
        self._reserve0 = reserves[0]
        self._reserve1 = reserves[1]
        return self._reserve0, self._reserve1

    async def get_current_tick(self) -> Optional[int]:
        """
        Classic AMM doesn't have ticks.
        Returns a simulated tick based on current price for compatibility.
        """
        price = await self.get_current_price()
        if price <= 0:
            return None
        # Convert price to tick using Uniswap V3 formula for compatibility
        return self.price_to_tick(price)

    async def get_current_price(self) -> float:
        """Get current price from reserves (token1/token0)"""
        reserve0, reserve1 = await self._get_reserves()

        if reserve0 == 0:
            return 0.0

        # Calculate price with decimal adjustment
        price = reserve1 / reserve0
        decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
        return price * decimal_adjustment

    async def get_liquidity(self) -> int:
        """
        Get current liquidity as sqrt(k) where k = reserve0 * reserve1
        This represents the geometric mean of reserves
        """
        reserve0, reserve1 = await self._get_reserves()
        return int(math.sqrt(reserve0 * reserve1))

    async def get_tick_data(self, tick: int) -> Optional[Dict]:
        """
        Classic AMM doesn't have tick-based liquidity.
        Returns None as tick data is not applicable.
        """
        return None

    async def get_liquidity_distribution(
        self,
        center_tick: Optional[int] = None,
        tick_range: int = 200
    ) -> Dict[int, Dict]:
        """
        Simulate tick distribution from xy=k curve.
        For classic AMM, liquidity is effectively infinite at all prices,
        but we simulate a distribution for visualization/compatibility.
        """
        reserve0, reserve1 = await self._get_reserves()
        current_price = await self.get_current_price()

        if current_price <= 0:
            return {}

        # Calculate k (constant product)
        k = reserve0 * reserve1

        # Simulate tick distribution
        # In classic AMM, we model liquidity as concentrated around current price
        tick_liquidity = {}
        tick_spacing = 10  # Use standard spacing for simulation

        if center_tick is None:
            center_tick = self.price_to_tick(current_price)

        # Align to tick spacing
        aligned_center = (center_tick // tick_spacing) * tick_spacing

        # Create simulated ticks around current price
        # For AMM, liquidity depth decreases as we move away from current price
        for i in range(-tick_range, tick_range + 1):
            tick = aligned_center + (i * tick_spacing)
            tick_price = self.tick_to_price(tick)

            if tick_price <= 0:
                continue

            # Calculate virtual liquidity at this price level
            # Using the constant product formula to estimate liquidity depth
            distance_from_center = abs(i)
            decay_factor = math.exp(-distance_from_center * 0.02)

            # Virtual liquidity based on reserves and distance from center
            virtual_liquidity = int(math.sqrt(k) * decay_factor)

            if virtual_liquidity > 0:
                tick_liquidity[tick] = {
                    "tick": tick,
                    "liquidityGross": virtual_liquidity,
                    "liquidityNet": virtual_liquidity if i >= 0 else -virtual_liquidity,
                    "price": tick_price,
                    "initialized": True,
                    "virtual": True  # Flag indicating this is simulated
                }

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

            # Calculate net amounts (AMM style: in - out)
            amount0 = args['amount0In'] - args['amount0Out']
            amount1 = args['amount1In'] - args['amount1Out']

            # Determine side: if amount0 is positive (token0 coming in), it's a sell
            # If amount0 is negative (token0 going out), it's a buy
            side = "sell" if amount0 > 0 else "buy"

            # Calculate execution price
            if abs(amount0) > 0:
                price = abs(amount1) / abs(amount0)
                decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
                price = price * decimal_adjustment
            else:
                price = 0.0

            swap_event = SwapEvent(
                timestamp=block['timestamp'],
                block=block_number,
                tx_hash=event['transactionHash'].hex(),
                sender=args['sender'],
                amount0=amount0,
                amount1=amount1,
                sqrt_price_x96=None,  # Not applicable for AMM
                tick=None,  # Not applicable for AMM
                liquidity=None,  # Not applicable for AMM
                price=price,
                side=side
            )
            swap_events.append(swap_event)

        return swap_events

    async def capture_snapshot(self) -> TickSnapshot:
        """Capture complete pool state snapshot"""
        block = self.w3.eth.block_number
        timestamp = await self.get_block_timestamp(block)

        # Get current state
        reserve0, reserve1 = await self._get_reserves()
        current_price = await self.get_current_price()
        current_tick = await self.get_current_tick()
        liquidity = await self.get_liquidity()

        # Get simulated liquidity distribution
        tick_liquidity = await self.get_liquidity_distribution(current_tick)

        # Calculate k for metadata
        k = reserve0 * reserve1

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
            reserves=(reserve0, reserve1),
            metadata={
                "k": str(k),
                "reserve0": str(reserve0),
                "reserve1": str(reserve1),
                "fee": self.fee,
                "decimals0": self.decimals0,
                "decimals1": self.decimals1,
                "symbol0": self.symbol0,
                "symbol1": self.symbol1,
                "pool_type": "classic_amm"
            }
        )

        return snapshot

    async def subscribe_to_swaps(self, callback):
        """
        Subscribe to real-time swap events
        Note: This requires an async event loop
        """
        import asyncio

        # Create event filter
        event_filter = self.pool_contract.events.Swap.create_filter(fromBlock='latest')

        while True:
            for event in event_filter.get_new_entries():
                args = event['args']
                block_number = event['blockNumber']
                timestamp = await self.get_block_timestamp(block_number)

                # Calculate net amounts
                amount0 = args['amount0In'] - args['amount0Out']
                amount1 = args['amount1In'] - args['amount1Out']

                # Determine side
                side = "sell" if amount0 > 0 else "buy"

                # Calculate execution price
                if abs(amount0) > 0:
                    price = abs(amount1) / abs(amount0)
                    decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
                    price = price * decimal_adjustment
                else:
                    price = 0.0

                swap_event = SwapEvent(
                    timestamp=timestamp,
                    block=block_number,
                    tx_hash=event['transactionHash'].hex(),
                    sender=args['sender'],
                    amount0=amount0,
                    amount1=amount1,
                    sqrt_price_x96=None,
                    tick=None,
                    liquidity=None,
                    price=price,
                    side=side
                )

                await callback(swap_event)

            # Wait before checking again
            await asyncio.sleep(2)  # Linea block time
