#!/usr/bin/env python3
"""
Base DEX Adapter - Abstract Interface for Multi-DEX Market Making
Unified interface for Lynex, Nile, SyncSwap, KyberSwap, and Etherex on Linea
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from web3 import Web3


class SwapEvent:
    """Standardized swap event across all DEX types"""
    def __init__(
        self,
        timestamp: int,
        block: int,
        tx_hash: str,
        sender: str,
        amount0: int,
        amount1: int,
        sqrt_price_x96: Optional[int],
        tick: Optional[int],
        liquidity: Optional[int],
        price: float,
        side: str  # "buy" or "sell"
    ):
        self.timestamp = timestamp
        self.block = block
        self.tx_hash = tx_hash
        self.sender = sender
        self.amount0 = amount0
        self.amount1 = amount1
        self.sqrt_price_x96 = sqrt_price_x96
        self.tick = tick
        self.liquidity = liquidity
        self.price = price
        self.side = side

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "block": self.block,
            "tx_hash": self.tx_hash,
            "sender": self.sender,
            "amount0": self.amount0,
            "amount1": self.amount1,
            "sqrt_price_x96": str(self.sqrt_price_x96) if self.sqrt_price_x96 else None,
            "tick": self.tick,
            "liquidity": str(self.liquidity) if self.liquidity else None,
            "price": self.price,
            "side": self.side
        }


class TickSnapshot:
    """Standardized tick/orderbook snapshot across all DEX types"""
    def __init__(
        self,
        timestamp: int,
        block: int,
        dex: str,
        pool: str,
        token0: str,
        token1: str,
        current_price: float,
        current_tick: Optional[int],
        liquidity: int,
        tick_liquidity: Dict[int, Dict],
        reserves: Optional[Tuple[int, int]] = None,
        metadata: Optional[Dict] = None
    ):
        self.timestamp = timestamp
        self.block = block
        self.dex = dex
        self.pool = pool
        self.token0 = token0
        self.token1 = token1
        self.current_price = current_price
        self.current_tick = current_tick
        self.liquidity = liquidity
        self.tick_liquidity = tick_liquidity
        self.reserves = reserves
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "block": self.block,
            "dex": self.dex,
            "pool": self.pool,
            "token0": self.token0,
            "token1": self.token1,
            "current_price": self.current_price,
            "current_tick": self.current_tick,
            "liquidity": str(self.liquidity),
            "tick_liquidity": {
                str(tick): {
                    "liquidityGross": str(data.get("liquidityGross", 0)),
                    "liquidityNet": str(data.get("liquidityNet", 0)),
                    "price": data.get("price"),
                    "initialized": data.get("initialized", False)
                }
                for tick, data in self.tick_liquidity.items()
            },
            "reserves": {"reserve0": str(self.reserves[0]), "reserve1": str(self.reserves[1])} if self.reserves else None,
            "metadata": self.metadata
        }


class BaseDEXAdapter(ABC):
    """
    Abstract base class for DEX adapters
    All adapters must implement these methods for unified market making analytics
    """

    # Class constants
    LINEA_CHAIN_ID = 59144
    LINEA_RPC = "https://rpc.linea.build"

    def __init__(
        self,
        pool_address: str,
        rpc_url: str = None,
        w3: Optional[Web3] = None
    ):
        self.pool_address = Web3.to_checksum_address(pool_address)
        self.rpc_url = rpc_url or self.LINEA_RPC

        # Use provided Web3 instance or create new one
        if w3:
            self.w3 = w3
        else:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to RPC: {self.rpc_url}")

        # Pool metadata (to be populated by child classes)
        self.token0 = None
        self.token1 = None
        self.decimals0 = None
        self.decimals1 = None
        self.symbol0 = None
        self.symbol1 = None
        self.fee = None

    @property
    @abstractmethod
    def dex_name(self) -> str:
        """Return the name of the DEX (e.g., 'lynex', 'etherex')"""
        pass

    @property
    @abstractmethod
    def dex_type(self) -> str:
        """Return the type of DEX ('uniswap_v3', 'classic_amm', 'stable_swap', etc.)"""
        pass

    @abstractmethod
    async def initialize(self):
        """Initialize pool metadata (tokens, decimals, fee, etc.)"""
        pass

    @abstractmethod
    async def get_current_tick(self) -> Optional[int]:
        """
        Get current tick (for tick-based DEXes like Uniswap V3)
        Returns None for AMM-style pools without ticks
        """
        pass

    @abstractmethod
    async def get_current_price(self) -> float:
        """Get current mid price (token1/token0)"""
        pass

    @abstractmethod
    async def get_liquidity(self) -> int:
        """Get current active liquidity"""
        pass

    @abstractmethod
    async def get_tick_data(self, tick: int) -> Optional[Dict]:
        """
        Get liquidity data for a specific tick
        Returns None if not applicable (e.g., classic AMM)
        """
        pass

    @abstractmethod
    async def get_liquidity_distribution(
        self,
        center_tick: Optional[int] = None,
        tick_range: int = 200
    ) -> Dict[int, Dict]:
        """
        Get liquidity distribution around current price
        For V3-style: tick-based distribution
        For AMM: simulate tick distribution from reserves
        """
        pass

    @abstractmethod
    async def get_recent_swaps(
        self,
        num_swaps: int = 100,
        from_block: Optional[int] = None
    ) -> List[SwapEvent]:
        """
        Get recent swap events for orderflow analysis
        Returns standardized SwapEvent objects
        """
        pass

    @abstractmethod
    async def capture_snapshot(self) -> TickSnapshot:
        """
        Capture complete orderbook snapshot
        Returns standardized TickSnapshot object
        """
        pass

    @abstractmethod
    async def subscribe_to_swaps(self, callback):
        """
        Subscribe to real-time swap events
        Callback receives SwapEvent objects
        """
        pass

    # Common utility methods (implemented here)

    def sqrt_price_to_price(self, sqrt_price_x96: int) -> float:
        """Convert sqrtPriceX96 to human-readable price"""
        Q96 = 2 ** 96
        price = (sqrt_price_x96 / Q96) ** 2
        decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
        return price * decimal_adjustment

    def tick_to_price(self, tick: int) -> float:
        """Convert tick to price"""
        price = 1.0001 ** tick
        decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
        return price * decimal_adjustment

    def price_to_tick(self, price: float) -> int:
        """Convert price to tick"""
        import math
        decimal_adjustment = 10 ** (self.decimals0 - self.decimals1)
        adjusted_price = price / decimal_adjustment
        return int(math.log(adjusted_price) / math.log(1.0001))

    def get_token_contract(self, token_address: str):
        """Get ERC20 token contract"""
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
            },
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            }
        ]
        return self.w3.eth.contract(address=token_address, abi=erc20_abi)

    async def get_block_timestamp(self, block_number: Optional[int] = None) -> int:
        """Get timestamp for a block"""
        if block_number is None:
            block_number = self.w3.eth.block_number
        block = self.w3.eth.get_block(block_number)
        return block['timestamp']

    def __repr__(self):
        return f"{self.__class__.__name__}(pool={self.pool_address}, dex={self.dex_name})"
