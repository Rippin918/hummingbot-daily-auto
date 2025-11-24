#!/usr/bin/env python3
"""
Unified Market Making Analyzer
Combines all MM analytics for comprehensive trading signals

Integrates:
- VPIN (toxicity / adverse selection)
- Volatility estimation (Avellaneda-Stoikov σ)
- Inventory management (reservation price)
- Kyle's Lambda (price impact)
- Orderflow imbalance (regime detection)

Outputs actionable MM signals for Sapient HRM → Hummingbot MCP
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json

from .vpin import VPINCalculator, VPINResult
from .volatility import VolatilityEstimator, VolatilityResult
from .avellaneda_stoikov import (
    InventoryManager,
    KyleLambdaEstimator,
    AvellanedaStoikovCalculator,
    InventorySignal,
    KyleLambdaResult,
    AvellanedaStoikovSpread
)
from .orderflow import OrderflowAnalyzer, ImbalanceResult


@dataclass
class UnifiedMMSignal:
    """Comprehensive market making signal"""
    timestamp: int
    pair: str
    dex: str

    # Current market state
    mid_price: float
    bid_price: float
    ask_price: float
    spread_bps: float  # Basis points

    # Analytics components
    vpin: Optional[VPINResult]
    volatility: Optional[VolatilityResult]
    inventory: Optional[InventorySignal]
    kyle_lambda: Optional[KyleLambdaResult]
    orderflow: Optional[ImbalanceResult]
    avellaneda_stoikov: Optional[AvellanedaStoikovSpread]

    # Unified recommendation
    action: str  # "quote_tight", "quote_normal", "quote_wide", "pause", "rebalance_inventory"
    confidence: float  # 0-1
    reasoning: List[str]  # Human-readable explanation

    # Risk assessment
    toxicity_risk: str  # "low", "medium", "high"
    inventory_risk: str  # "low", "medium", "high", "critical"
    liquidity_risk: str  # "low", "medium", "high"

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        def convert_dataclass(obj):
            if obj is None:
                return None
            return asdict(obj)

        return {
            "timestamp": self.timestamp,
            "pair": self.pair,
            "dex": self.dex,
            "mid_price": self.mid_price,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "spread_bps": self.spread_bps,
            "vpin": convert_dataclass(self.vpin),
            "volatility": convert_dataclass(self.volatility),
            "inventory": convert_dataclass(self.inventory),
            "kyle_lambda": convert_dataclass(self.kyle_lambda),
            "orderflow": convert_dataclass(self.orderflow),
            "avellaneda_stoikov": convert_dataclass(self.avellaneda_stoikov),
            "action": self.action,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "toxicity_risk": self.toxicity_risk,
            "inventory_risk": self.inventory_risk,
            "liquidity_risk": self.liquidity_risk
        }


class UnifiedMMAnalyzer:
    """
    Unified market making analyzer
    Combines all analytics modules for comprehensive signals
    """

    def __init__(
        self,
        pair: str,
        dex: str,
        max_inventory: float = 100.0,
        gamma: float = 0.1,  # Risk aversion
        vpin_bucket_size: float = 50.0,
        vol_window: int = 100
    ):
        """
        Initialize unified analyzer

        Args:
            pair: Trading pair symbol
            dex: DEX name
            max_inventory: Maximum inventory position
            gamma: Risk aversion parameter
            vpin_bucket_size: Volume per VPIN bucket
            vol_window: Volatility estimation window
        """
        self.pair = pair
        self.dex = dex

        # Initialize analytics modules
        self.vpin = VPINCalculator(bucket_size=vpin_bucket_size)
        self.volatility = VolatilityEstimator(window_periods=vol_window)
        self.inventory_mgr = InventoryManager(max_inventory=max_inventory, gamma=gamma)
        self.kyle_lambda = KyleLambdaEstimator(window_size=100)
        self.orderflow = OrderflowAnalyzer(window_size=100)
        self.as_calculator = AvellanedaStoikovCalculator(gamma=gamma)

        # State
        self.last_mid_price = None

    def process_tick_snapshot(
        self,
        snapshot: Dict,
        current_inventory: Optional[float] = None
    ) -> UnifiedMMSignal:
        """
        Process a tick snapshot and generate comprehensive MM signal

        Args:
            snapshot: Tick snapshot from DEX adapter
            current_inventory: Optional current inventory position

        Returns:
            UnifiedMMSignal with all analytics
        """
        timestamp = snapshot["timestamp"]
        mid_price = snapshot["current_price"]
        tick_liquidity = snapshot.get("tick_liquidity", {})

        # Calculate bid/ask liquidity from tick distribution
        current_tick = snapshot.get("current_tick")
        bid_liq, ask_liq = self._calculate_bid_ask_liquidity(tick_liquidity, current_tick)

        # Update inventory if provided
        if current_inventory is not None:
            self.inventory_mgr.update_inventory(current_inventory)

        # Update orderflow analyzer
        self.orderflow.add_observation(bid_liq, ask_liq, timestamp)

        # Get analytics results
        vpin_result = self.vpin.calculate_vpin() if len(self.vpin.buckets) >= self.vpin.num_buckets else None
        vol_result = self.volatility.estimate()
        inventory_signal = self.inventory_mgr.get_inventory_signal(
            mid_price,
            vol_result.recommended_vol if vol_result else 0.2
        )
        kyle_result = self.kyle_lambda.estimate_lambda()
        orderflow_result = self.orderflow.classify_regime()

        # Calculate Avellaneda-Stoikov optimal spread
        as_spread = None
        if vol_result:
            as_spread = self.as_calculator.calculate_optimal_spread(
                mid_price=mid_price,
                volatility=vol_result.recommended_vol,
                inventory=self.inventory_mgr.current_inventory,
                kyle_lambda=kyle_result.lambda_value if kyle_result else None
            )

        # Generate unified recommendation
        action, confidence, reasoning, risks = self._generate_recommendation(
            vpin_result,
            vol_result,
            inventory_signal,
            kyle_result,
            orderflow_result,
            as_spread
        )

        # Calculate current spread
        if as_spread:
            bid_price = as_spread.bid_price
            ask_price = as_spread.ask_price
        else:
            # Fallback to simple spread
            bid_price = mid_price * 0.999
            ask_price = mid_price * 1.001

        spread_bps = ((ask_price - bid_price) / mid_price) * 10000

        return UnifiedMMSignal(
            timestamp=timestamp,
            pair=self.pair,
            dex=self.dex,
            mid_price=mid_price,
            bid_price=bid_price,
            ask_price=ask_price,
            spread_bps=spread_bps,
            vpin=vpin_result,
            volatility=vol_result,
            inventory=inventory_signal,
            kyle_lambda=kyle_result,
            orderflow=orderflow_result,
            avellaneda_stoikov=as_spread,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            toxicity_risk=risks["toxicity"],
            inventory_risk=risks["inventory"],
            liquidity_risk=risks["liquidity"]
        )

    def _calculate_bid_ask_liquidity(
        self,
        tick_liquidity: Dict,
        current_tick: Optional[int]
    ) -> tuple:
        """Calculate total bid and ask liquidity from tick distribution"""
        if not tick_liquidity or current_tick is None:
            return (1000.0, 1000.0)  # Default

        bid_liq = 0.0
        ask_liq = 0.0

        for tick_str, tick_data in tick_liquidity.items():
            tick = int(tick_str)
            liquidity = float(tick_data.get("liquidityGross", 0))

            if tick < current_tick:
                bid_liq += liquidity
            else:
                ask_liq += liquidity

        return (bid_liq, ask_liq)

    def _generate_recommendation(
        self,
        vpin: Optional[VPINResult],
        volatility: Optional[VolatilityResult],
        inventory: InventorySignal,
        kyle_lambda: Optional[KyleLambdaResult],
        orderflow: ImbalanceResult,
        as_spread: Optional[AvellanedaStoikovSpread]
    ) -> tuple:
        """
        Generate unified trading recommendation

        Returns:
            (action, confidence, reasoning, risks)
        """
        reasoning = []
        confidence_factors = []

        # Initialize risk levels
        toxicity_risk = "low"
        inventory_risk = "low"
        liquidity_risk = "low"

        # Analyze VPIN (toxicity)
        if vpin:
            if vpin.toxicity_level == "high":
                reasoning.append(f"High VPIN ({vpin.vpin:.2f}) - toxic flow detected")
                toxicity_risk = "high"
                confidence_factors.append(vpin.confidence)
            elif vpin.toxicity_level == "elevated":
                reasoning.append(f"Elevated VPIN ({vpin.vpin:.2f}) - caution advised")
                toxicity_risk = "medium"
                confidence_factors.append(vpin.confidence * 0.7)

        # Analyze inventory
        if inventory.urgency in ["high", "critical"]:
            reasoning.append(f"Inventory {inventory.urgency}: {inventory.recommendation}")
            inventory_risk = inventory.urgency
            confidence_factors.append(0.9)

        # Analyze Kyle's Lambda (liquidity)
        if kyle_lambda:
            if kyle_lambda.spread_multiplier > 2.0:
                reasoning.append(f"High price impact (λ={kyle_lambda.lambda_value:.6f}) - illiquid")
                liquidity_risk = "high"
                confidence_factors.append(kyle_lambda.confidence)

        # Analyze orderflow regime
        if orderflow.regime == "mean_reverting" and orderflow.confidence > 0.5:
            reasoning.append(f"Mean-reverting regime (HL={orderflow.half_life:.1f}) - tighten spreads" if orderflow.half_life else "Mean-reverting regime")
            confidence_factors.append(orderflow.confidence)
        elif orderflow.regime == "trending" and orderflow.confidence > 0.5:
            reasoning.append(f"Trending regime (AC={orderflow.autocorrelation:.2f}) - widen spreads")
            confidence_factors.append(orderflow.confidence)

        # Determine action
        action = "quote_normal"

        # Critical inventory takes priority
        if inventory_risk == "critical":
            action = "rebalance_inventory"
        # High toxicity → pause or wide spreads
        elif toxicity_risk == "high":
            action = "pause"
        # High inventory + elevated toxicity → pause
        elif inventory_risk == "high" and toxicity_risk == "medium":
            action = "quote_wide"
        # Mean-reverting + low toxicity → tight spreads
        elif orderflow.regime == "mean_reverting" and toxicity_risk == "low":
            action = "quote_tight"
        # Trending or elevated toxicity → wide spreads
        elif orderflow.regime == "trending" or toxicity_risk == "medium":
            action = "quote_wide"

        # Calculate overall confidence
        confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5

        risks = {
            "toxicity": toxicity_risk,
            "inventory": inventory_risk,
            "liquidity": liquidity_risk
        }

        return (action, confidence, reasoning, risks)

    def process_swap_event(self, swap_event):
        """
        Process a swap event for VPIN and Kyle's Lambda

        Args:
            swap_event: SwapEvent from DEX adapter
        """
        # Update VPIN
        volume = abs(swap_event.amount0) / (10 ** 18)  # Adjust decimals
        self.vpin.add_trade(swap_event.price, volume)

        # Update Kyle's Lambda
        if self.last_mid_price:
            self.kyle_lambda.add_trade(
                self.last_mid_price,
                swap_event.price,
                volume,
                swap_event.side
            )

        self.last_mid_price = swap_event.price

        # Update inventory if it's our trade
        # (In real implementation, would check if sender == our_address)


# Example usage
if __name__ == "__main__":
    # Initialize analyzer
    analyzer = UnifiedMMAnalyzer(
        pair="WETH-USDC",
        dex="lynex",
        max_inventory=100.0,
        gamma=0.1
    )

    # Simulate tick snapshot
    snapshot = {
        "timestamp": 1700000000,
        "block": 1000000,
        "current_price": 1850.0,
        "current_tick": 204240,
        "liquidity": "12345678901234",
        "tick_liquidity": {
            "204180": {"liquidityGross": "500000000000", "price": 1849.0},
            "204240": {"liquidityGross": "800000000000", "price": 1850.0},
            "204300": {"liquidityGross": "400000000000", "price": 1851.0}
        }
    }

    # Process snapshot
    signal = analyzer.process_tick_snapshot(snapshot, current_inventory=50.0)

    # Print results
    print(json.dumps(signal.to_dict(), indent=2))
