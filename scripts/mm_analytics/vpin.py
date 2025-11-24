#!/usr/bin/env python3
"""
VPIN (Volume-Synchronized Probability of Informed Trading) Module
Detects adverse selection / toxic orderflow for market makers

VPIN measures the probability that informed traders are in the market.
High VPIN = toxic flow → widen spreads or pause quoting
Low VPIN = uninformed flow → tighten spreads

Reference: Easley, López de Prado, O'Hara (2012)
"""

import numpy as np
from typing import List, Dict, Optional
from collections import deque
from dataclasses import dataclass


@dataclass
class VPINResult:
    """VPIN calculation result"""
    vpin: float  # Main VPIN metric (0-1)
    toxicity_level: str  # "safe", "normal", "elevated", "high"
    buy_volume: float
    sell_volume: float
    total_volume: float
    imbalance: float  # |buy - sell| / total
    recommendation: str  # Spread adjustment recommendation
    confidence: float  # Confidence in the signal (0-1)


class VPINCalculator:
    """
    Calculate VPIN for adverse selection detection

    Market Making Strategy:
    - VPIN < 0.3: Safe to tighten spreads (uninformed flow)
    - VPIN 0.3-0.5: Normal, use standard spreads
    - VPIN 0.5-0.7: Elevated toxicity, widen spreads
    - VPIN > 0.7: High toxicity, widen significantly or pause
    """

    def __init__(
        self,
        bucket_size: float = 50.0,  # Volume per bucket (e.g., 50 ETH)
        num_buckets: int = 50,      # Number of buckets for rolling window
        price_change_threshold: float = 0.0  # Minimum price change to classify
    ):
        """
        Initialize VPIN calculator

        Args:
            bucket_size: Target volume per bucket (in base token units)
            num_buckets: Number of buckets in rolling window
            price_change_threshold: Minimum price change to classify trade direction
        """
        self.bucket_size = bucket_size
        self.num_buckets = num_buckets
        self.price_change_threshold = price_change_threshold

        # State
        self.buckets = deque(maxlen=num_buckets)
        self.current_bucket = {"buy_volume": 0.0, "sell_volume": 0.0, "total_volume": 0.0}
        self.last_price = None

    def classify_trade(
        self,
        price: float,
        volume: float,
        prev_price: Optional[float] = None
    ) -> str:
        """
        Classify trade as buy or sell using price change (bulk volume classification)

        Args:
            price: Trade price
            volume: Trade volume
            prev_price: Previous trade price (or mid-price)

        Returns:
            "buy" or "sell"
        """
        if prev_price is None:
            # First trade, default to neutral (split 50/50)
            return "neutral"

        price_change = price - prev_price

        if abs(price_change) < self.price_change_threshold:
            return "neutral"
        elif price_change > 0:
            return "buy"  # Price moved up = buyer-initiated
        else:
            return "sell"  # Price moved down = seller-initiated

    def add_trade(self, price: float, volume: float) -> Optional[VPINResult]:
        """
        Add a trade to the VPIN calculation

        Args:
            price: Trade price
            volume: Trade volume (in base token)

        Returns:
            VPINResult if a bucket completed, otherwise None
        """
        # Classify trade direction
        trade_type = self.classify_trade(price, volume, self.last_price)

        # Add to current bucket
        if trade_type == "buy":
            self.current_bucket["buy_volume"] += volume
        elif trade_type == "sell":
            self.current_bucket["sell_volume"] += volume
        else:  # neutral
            # Split volume 50/50
            self.current_bucket["buy_volume"] += volume / 2
            self.current_bucket["sell_volume"] += volume / 2

        self.current_bucket["total_volume"] += volume

        self.last_price = price

        # Check if bucket is full
        if self.current_bucket["total_volume"] >= self.bucket_size:
            # Close current bucket
            self.buckets.append(dict(self.current_bucket))

            # Reset current bucket
            self.current_bucket = {"buy_volume": 0.0, "sell_volume": 0.0, "total_volume": 0.0}

            # Calculate VPIN if we have enough buckets
            if len(self.buckets) >= self.num_buckets:
                return self.calculate_vpin()

        return None

    def add_swap_event(self, swap_event) -> Optional[VPINResult]:
        """
        Convenience method to add a SwapEvent

        Args:
            swap_event: SwapEvent object from DEX adapter

        Returns:
            VPINResult if bucket completed
        """
        # Extract volume (use absolute value of amount0)
        volume = abs(swap_event.amount0) / (10 ** swap_event.metadata.get("decimals0", 18))
        return self.add_trade(swap_event.price, volume)

    def calculate_vpin(self) -> VPINResult:
        """
        Calculate VPIN from current bucket window

        VPIN = Σ|Buy_i - Sell_i| / ΣVolume_i over window

        Returns:
            VPINResult with toxicity assessment
        """
        if len(self.buckets) < self.num_buckets:
            # Not enough data
            return VPINResult(
                vpin=0.0,
                toxicity_level="unknown",
                buy_volume=0.0,
                sell_volume=0.0,
                total_volume=0.0,
                imbalance=0.0,
                recommendation="insufficient_data",
                confidence=0.0
            )

        # Calculate total imbalance and volume
        total_imbalance = 0.0
        total_volume = 0.0
        total_buy = 0.0
        total_sell = 0.0

        for bucket in self.buckets:
            buy_vol = bucket["buy_volume"]
            sell_vol = bucket["sell_volume"]
            imbalance = abs(buy_vol - sell_vol)

            total_imbalance += imbalance
            total_volume += bucket["total_volume"]
            total_buy += buy_vol
            total_sell += sell_vol

        # Calculate VPIN
        vpin = total_imbalance / total_volume if total_volume > 0 else 0.0

        # Overall imbalance direction
        imbalance_ratio = (total_buy - total_sell) / total_volume if total_volume > 0 else 0.0

        # Determine toxicity level and recommendation
        toxicity_level, recommendation, confidence = self._assess_toxicity(vpin, imbalance_ratio)

        return VPINResult(
            vpin=vpin,
            toxicity_level=toxicity_level,
            buy_volume=total_buy,
            sell_volume=total_sell,
            total_volume=total_volume,
            imbalance=imbalance_ratio,
            recommendation=recommendation,
            confidence=confidence
        )

    def _assess_toxicity(
        self,
        vpin: float,
        imbalance_ratio: float
    ) -> tuple:
        """
        Assess toxicity level and generate spread recommendation

        Returns:
            (toxicity_level, recommendation, confidence)
        """
        # Confidence based on how extreme VPIN is
        confidence = min(abs(vpin - 0.4) * 2, 1.0)  # Most confident at extremes

        if vpin < 0.3:
            return (
                "safe",
                "tighten_spreads",
                confidence
            )
        elif vpin < 0.5:
            return (
                "normal",
                "standard_spreads",
                confidence
            )
        elif vpin < 0.7:
            return (
                "elevated",
                f"widen_spreads_{'buy' if imbalance_ratio > 0 else 'sell'}_side",
                confidence
            )
        else:
            return (
                "high",
                "pause_quoting_or_widen_significantly",
                confidence
            )

    def get_recent_vpin_stats(self, lookback: int = 10) -> Dict:
        """
        Get statistics over recent VPIN calculations

        Args:
            lookback: Number of recent buckets to analyze

        Returns:
            Dictionary with statistics
        """
        if len(self.buckets) < lookback:
            lookback = len(self.buckets)

        if lookback == 0:
            return {"error": "no_data"}

        recent_buckets = list(self.buckets)[-lookback:]

        vpins = []
        for i in range(len(recent_buckets)):
            if i < self.num_buckets:
                continue

            window = recent_buckets[max(0, i - self.num_buckets):i]
            total_imbalance = sum(abs(b["buy_volume"] - b["sell_volume"]) for b in window)
            total_volume = sum(b["total_volume"] for b in window)

            if total_volume > 0:
                vpins.append(total_imbalance / total_volume)

        if not vpins:
            return {"error": "insufficient_data"}

        return {
            "mean_vpin": np.mean(vpins),
            "std_vpin": np.std(vpins),
            "min_vpin": np.min(vpins),
            "max_vpin": np.max(vpins),
            "current_vpin": vpins[-1] if vpins else 0.0,
            "trend": "increasing" if len(vpins) > 1 and vpins[-1] > vpins[0] else "decreasing"
        }


class VPINMonitor:
    """
    Real-time VPIN monitoring for market making
    Tracks multiple pairs and sends alerts
    """

    def __init__(self, pairs: Dict[str, VPINCalculator]):
        """
        Initialize VPIN monitor

        Args:
            pairs: Dictionary of {pair_symbol: VPINCalculator}
        """
        self.pairs = pairs
        self.alerts = []

    def process_swap(self, pair: str, swap_event) -> Optional[VPINResult]:
        """
        Process a swap event for a pair

        Args:
            pair: Pair symbol
            swap_event: SwapEvent from DEX adapter

        Returns:
            VPINResult if bucket completed
        """
        if pair not in self.pairs:
            raise ValueError(f"Unknown pair: {pair}")

        calculator = self.pairs[pair]
        result = calculator.add_swap_event(swap_event)

        # Check for alerts
        if result and result.toxicity_level in ["elevated", "high"]:
            self.alerts.append({
                "pair": pair,
                "timestamp": swap_event.timestamp,
                "vpin": result.vpin,
                "toxicity": result.toxicity_level,
                "recommendation": result.recommendation
            })

        return result

    def get_all_vpin_states(self) -> Dict[str, VPINResult]:
        """Get current VPIN state for all pairs"""
        return {
            pair: calculator.calculate_vpin()
            for pair, calculator in self.pairs.items()
        }

    def get_alerts(self, clear: bool = True) -> List[Dict]:
        """
        Get recent alerts

        Args:
            clear: Clear alerts after returning

        Returns:
            List of alert dictionaries
        """
        alerts = list(self.alerts)
        if clear:
            self.alerts.clear()
        return alerts


# Example usage
if __name__ == "__main__":
    # Initialize calculator
    vpin_calc = VPINCalculator(
        bucket_size=50.0,  # 50 token units per bucket
        num_buckets=50     # 50 bucket rolling window
    )

    # Simulate trades
    trades = [
        (100.0, 10.0),  # (price, volume)
        (100.5, 15.0),
        (100.2, 20.0),
        (101.0, 25.0),  # Large buy
        (100.8, 10.0),
        (100.3, 30.0),  # Large sell
    ]

    for price, volume in trades:
        result = vpin_calc.add_trade(price, volume)
        if result:
            print(f"VPIN: {result.vpin:.3f} - {result.toxicity_level}")
            print(f"  Recommendation: {result.recommendation}")
            print(f"  Buy: {result.buy_volume:.1f}, Sell: {result.sell_volume:.1f}")
