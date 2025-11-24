#!/usr/bin/env python3
"""
Linea Micropulse Analyzer - Coulter Counting Methodology
Institutional-grade orderbook analytics for Lynex tick data
Implements bid/ask pressure, imbalance velocity, liquidity hole detection, and Fibonacci levels
"""

import json
import math
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import deque
import numpy as np


class CoulterMicropulseAnalyzer:
    """
    Coulter counting methodology for orderbook micropulse analysis
    Analyzes tick-level liquidity distribution to detect market microstructure signals
    """

    # Fibonacci ratios for level detection
    FIBONACCI_RATIOS = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618, 2.618]

    # Liquidity hole detection thresholds
    DEFAULT_HOLE_THRESHOLD = 0.05  # 5% gap considered a "hole"
    SIGNIFICANT_HOLE_THRESHOLD = 0.10  # 10% gap is significant

    def __init__(
        self,
        lookback_periods: int = 20,
        hole_threshold: float = None,
        fibonacci_range_percent: float = 5.0
    ):
        """
        Initialize Coulter analyzer

        Args:
            lookback_periods: Number of snapshots to track for velocity calculation
            hole_threshold: Percentage gap to consider a liquidity hole (default: 5%)
            fibonacci_range_percent: Price range for Fibonacci level detection (default: 5%)
        """
        self.lookback_periods = lookback_periods
        self.hole_threshold = hole_threshold or self.DEFAULT_HOLE_THRESHOLD
        self.fibonacci_range_percent = fibonacci_range_percent

        # Historical snapshots for velocity analysis
        self.snapshot_history = deque(maxlen=lookback_periods)

        # Previous state for delta calculations
        self.prev_snapshot = None
        self.prev_signals = None

    def calculate_bid_ask_pressure(
        self,
        tick_distribution: Dict[int, Dict],
        current_tick: int
    ) -> Dict:
        """
        Calculate bid and ask side liquidity pressure
        Coulter counting: weight liquidity by distance from current price
        """
        bid_liquidity = 0  # Liquidity below current price
        ask_liquidity = 0  # Liquidity above current price
        bid_ticks = 0
        ask_ticks = 0

        bid_weighted_liquidity = 0.0
        ask_weighted_liquidity = 0.0

        for tick_str, tick_data in tick_distribution.items():
            tick = int(tick_str)
            liquidity = int(tick_data["liquidityGross"])

            if liquidity == 0:
                continue

            # Distance weighting (closer ticks have more influence)
            distance = abs(tick - current_tick)
            weight = 1.0 / (1.0 + distance / 100.0)  # Normalize by ~100 ticks

            if tick < current_tick:
                # Bid side (support)
                bid_liquidity += liquidity
                bid_ticks += 1
                bid_weighted_liquidity += liquidity * weight
            else:
                # Ask side (resistance)
                ask_liquidity += liquidity
                ask_ticks += 1
                ask_weighted_liquidity += liquidity * weight

        # Calculate pressure metrics
        total_liquidity = bid_liquidity + ask_liquidity
        total_weighted = bid_weighted_liquidity + ask_weighted_liquidity

        if total_liquidity == 0:
            return {
                "bid_liquidity": 0,
                "ask_liquidity": 0,
                "bid_pressure": 0.5,
                "ask_pressure": 0.5,
                "imbalance": 0.0,
                "bid_ticks": 0,
                "ask_ticks": 0
            }

        bid_pressure = bid_weighted_liquidity / total_weighted if total_weighted > 0 else 0.5
        ask_pressure = ask_weighted_liquidity / total_weighted if total_weighted > 0 else 0.5

        # Imbalance: positive means bid-heavy (bullish), negative means ask-heavy (bearish)
        imbalance = (bid_liquidity - ask_liquidity) / total_liquidity

        return {
            "bid_liquidity": bid_liquidity,
            "ask_liquidity": ask_liquidity,
            "bid_weighted": bid_weighted_liquidity,
            "ask_weighted": ask_weighted_liquidity,
            "bid_pressure": bid_pressure,
            "ask_pressure": ask_pressure,
            "imbalance": imbalance,
            "bid_ticks": bid_ticks,
            "ask_ticks": ask_ticks,
            "total_liquidity": total_liquidity
        }

    def detect_liquidity_holes(
        self,
        tick_distribution: Dict[int, Dict],
        current_tick: int,
        tick_spacing: int
    ) -> List[Dict]:
        """
        Detect liquidity holes (gaps) in the orderbook
        Large gaps indicate potential for rapid price movement
        """
        if not tick_distribution:
            return []

        # Sort ticks
        sorted_ticks = sorted([int(t) for t in tick_distribution.keys()])

        holes = []

        for i in range(len(sorted_ticks) - 1):
            tick1 = sorted_ticks[i]
            tick2 = sorted_ticks[i + 1]

            # Calculate gap in ticks
            gap_ticks = tick2 - tick1

            # Expected gap is just the tick spacing
            expected_gap = tick_spacing

            if gap_ticks > expected_gap:
                # Calculate price difference
                price1 = 1.0001 ** tick1
                price2 = 1.0001 ** tick2
                price_gap_percent = abs(price2 - price1) / price1 * 100

                # Only report significant holes
                if price_gap_percent >= self.hole_threshold * 100:
                    side = "bid" if tick2 < current_tick else "ask"
                    distance_from_price = abs((tick1 + tick2) / 2 - current_tick)

                    holes.append({
                        "tick_lower": tick1,
                        "tick_upper": tick2,
                        "gap_ticks": gap_ticks,
                        "gap_percent": price_gap_percent,
                        "side": side,
                        "distance_ticks": distance_from_price,
                        "severity": "critical" if price_gap_percent >= self.SIGNIFICANT_HOLE_THRESHOLD * 100 else "moderate"
                    })

        # Sort holes by distance from current price
        holes.sort(key=lambda h: h["distance_ticks"])

        return holes

    def calculate_imbalance_velocity(self) -> Optional[Dict]:
        """
        Calculate rate of change of orderbook imbalance
        High velocity indicates aggressive buying/selling pressure building
        """
        if len(self.snapshot_history) < 2:
            return None

        # Get imbalance values over time
        imbalances = [s["signals"]["pressure"]["imbalance"] for s in self.snapshot_history]
        timestamps = [s["timestamp"] for s in self.snapshot_history]

        if len(imbalances) < 2:
            return None

        # Calculate velocity (change per second)
        time_deltas = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
        imbalance_changes = [imbalances[i] - imbalances[i-1] for i in range(1, len(imbalances))]

        velocities = [
            change / delta if delta > 0 else 0
            for change, delta in zip(imbalance_changes, time_deltas)
        ]

        # Current velocity (latest change)
        current_velocity = velocities[-1] if velocities else 0

        # Average velocity over lookback period
        avg_velocity = np.mean(velocities) if velocities else 0

        # Acceleration (change in velocity)
        acceleration = 0
        if len(velocities) >= 2:
            acceleration = velocities[-1] - velocities[-2]

        return {
            "current_velocity": current_velocity,
            "avg_velocity": avg_velocity,
            "acceleration": acceleration,
            "trend": "bullish" if current_velocity > 0 else "bearish" if current_velocity < 0 else "neutral",
            "magnitude": abs(current_velocity)
        }

    def detect_fibonacci_levels(
        self,
        current_price: float,
        tick_distribution: Dict[int, Dict],
        recent_high: float = None,
        recent_low: float = None
    ) -> List[Dict]:
        """
        Detect Fibonacci retracement/extension levels relative to current price
        Identifies potential support/resistance zones
        """
        # Use tick distribution to estimate recent range if not provided
        if recent_high is None or recent_low is None:
            prices = [tick_data["price"] for tick_data in tick_distribution.values() if "price" in tick_data]
            if prices:
                recent_high = max(prices)
                recent_low = min(prices)
            else:
                return []

        price_range = recent_high - recent_low
        if price_range == 0:
            return []

        fibonacci_levels = []

        for ratio in self.FIBONACCI_RATIOS:
            # Retracement levels (from high)
            retrace_price = recent_high - (price_range * ratio)
            retrace_distance = abs(retrace_price - current_price) / current_price * 100

            if retrace_distance <= self.fibonacci_range_percent:
                fibonacci_levels.append({
                    "type": "retracement",
                    "ratio": ratio,
                    "price": retrace_price,
                    "distance_percent": retrace_distance,
                    "side": "support" if retrace_price < current_price else "resistance"
                })

            # Extension levels (beyond low)
            extension_price = recent_low - (price_range * (ratio - 1))
            extension_distance = abs(extension_price - current_price) / current_price * 100

            if extension_distance <= self.fibonacci_range_percent and ratio > 1.0:
                fibonacci_levels.append({
                    "type": "extension",
                    "ratio": ratio,
                    "price": extension_price,
                    "distance_percent": extension_distance,
                    "side": "support" if extension_price < current_price else "resistance"
                })

        # Sort by distance from current price
        fibonacci_levels.sort(key=lambda f: f["distance_percent"])

        return fibonacci_levels

    def calculate_liquidity_concentration(
        self,
        tick_distribution: Dict[int, Dict],
        current_tick: int,
        tick_spacing: int
    ) -> Dict:
        """
        Calculate how concentrated liquidity is around current price
        High concentration = tight spread, low slippage
        Low concentration = wide spread, high slippage potential
        """
        if not tick_distribution:
            return {
                "concentration_score": 0,
                "tight_range_liquidity": 0,
                "total_liquidity": 0
            }

        total_liquidity = sum(int(t["liquidityGross"]) for t in tick_distribution.values())

        # Define "tight range" as ±50 ticks from current
        tight_range = 50 * tick_spacing

        tight_range_liquidity = sum(
            int(tick_data["liquidityGross"])
            for tick_str, tick_data in tick_distribution.items()
            if abs(int(tick_str) - current_tick) <= tight_range
        )

        concentration_score = tight_range_liquidity / total_liquidity if total_liquidity > 0 else 0

        return {
            "concentration_score": concentration_score,
            "tight_range_liquidity": tight_range_liquidity,
            "total_liquidity": total_liquidity,
            "interpretation": "tight" if concentration_score > 0.7 else "normal" if concentration_score > 0.4 else "dispersed"
        }

    def analyze_snapshot(self, snapshot: Dict) -> Dict:
        """
        Perform complete Coulter micropulse analysis on a tick snapshot
        Returns comprehensive signals for strategy decision-making
        """
        tick_distribution = snapshot.get("tick_liquidity", {})
        current_tick = snapshot["current_tick"]
        current_price = snapshot["price"]
        tick_spacing = snapshot["metadata"]["tick_spacing"]

        # Calculate all Coulter signals
        pressure = self.calculate_bid_ask_pressure(tick_distribution, current_tick)
        holes = self.detect_liquidity_holes(tick_distribution, current_tick, tick_spacing)
        concentration = self.calculate_liquidity_concentration(tick_distribution, current_tick, tick_spacing)
        fibonacci = self.detect_fibonacci_levels(current_price, tick_distribution)

        # Build analysis result
        analysis = {
            "timestamp": snapshot["timestamp"],
            "block": snapshot["block"],
            "pool": snapshot["pool"],
            "current_tick": current_tick,
            "current_price": current_price,
            "signals": {
                "pressure": pressure,
                "liquidity_holes": holes,
                "concentration": concentration,
                "fibonacci_levels": fibonacci
            },
            "metadata": snapshot["metadata"]
        }

        # Add to history for velocity calculation
        self.snapshot_history.append(analysis)

        # Calculate velocity if enough history
        velocity = self.calculate_imbalance_velocity()
        if velocity:
            analysis["signals"]["velocity"] = velocity

        # Generate trading signals
        trading_signal = self._generate_trading_signal(analysis)
        analysis["trading_signal"] = trading_signal

        self.prev_snapshot = snapshot

        return analysis

    def _generate_trading_signal(self, analysis: Dict) -> Dict:
        """
        Generate actionable trading signals from Coulter analysis
        For integration with Sapient HRM automated decision system
        """
        signals = analysis["signals"]
        pressure = signals["pressure"]
        holes = signals["liquidity_holes"]
        concentration = signals["concentration"]
        velocity = signals.get("velocity")

        # Initialize signal
        signal = {
            "action": "hold",
            "confidence": 0.0,
            "reasons": []
        }

        confidence_factors = []

        # Imbalance signal
        if abs(pressure["imbalance"]) > 0.3:
            if pressure["imbalance"] > 0:
                signal["reasons"].append("Strong bid pressure (bullish)")
                confidence_factors.append(abs(pressure["imbalance"]))
            else:
                signal["reasons"].append("Strong ask pressure (bearish)")
                confidence_factors.append(abs(pressure["imbalance"]))

        # Velocity signal
        if velocity and abs(velocity["current_velocity"]) > 0.01:
            if velocity["trend"] == "bullish":
                signal["reasons"].append(f"Bullish momentum (velocity: {velocity['current_velocity']:.4f})")
                confidence_factors.append(velocity["magnitude"] * 10)
            elif velocity["trend"] == "bearish":
                signal["reasons"].append(f"Bearish momentum (velocity: {velocity['current_velocity']:.4f})")
                confidence_factors.append(velocity["magnitude"] * 10)

        # Liquidity hole signal (risk indicator)
        critical_holes = [h for h in holes if h["severity"] == "critical"]
        if critical_holes:
            nearest_hole = critical_holes[0]
            signal["reasons"].append(f"Critical liquidity hole detected ({nearest_hole['gap_percent']:.1f}% gap)")
            signal["risk"] = "high"
            confidence_factors.append(0.2)  # Holes increase confidence in directional moves

        # Concentration signal
        if concentration["concentration_score"] < 0.3:
            signal["reasons"].append("Low liquidity concentration - high slippage risk")
            signal["risk"] = "high"

        # Determine action
        if pressure["imbalance"] > 0.3 and (velocity is None or velocity["trend"] in ["bullish", "neutral"]):
            signal["action"] = "buy"
        elif pressure["imbalance"] < -0.3 and (velocity is None or velocity["trend"] in ["bearish", "neutral"]):
            signal["action"] = "sell"

        # Calculate confidence
        if confidence_factors:
            signal["confidence"] = min(sum(confidence_factors) / len(confidence_factors), 1.0)

        return signal

    def save_analysis(self, analysis: Dict, filename: str):
        """Save analysis results to JSON file"""
        with open(filename, 'w') as f:
            json.dump(analysis, f, indent=2)


async def main():
    """Example usage - analyze saved snapshots"""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze Lynex tick data with Coulter methodology")
    parser.add_argument("--input", type=str, required=True, help="Input snapshot JSON file")
    parser.add_argument("--output", type=str, help="Output analysis JSON file")
    parser.add_argument("--lookback", type=int, default=20, help="Lookback periods for velocity")

    args = parser.parse_args()

    # Load snapshots
    with open(args.input, 'r') as f:
        data = json.load(f)

    snapshots = data.get("snapshots", [])
    print(f"Loaded {len(snapshots)} snapshots")

    # Initialize analyzer
    analyzer = CoulterMicropulseAnalyzer(lookback_periods=args.lookback)

    # Analyze all snapshots
    analyses = []
    for snapshot in snapshots:
        analysis = analyzer.analyze_snapshot(snapshot)
        analyses.append(analysis)

        # Print summary
        signal = analysis["trading_signal"]
        print(f"[Block {analysis['block']}] "
              f"Price: {analysis['current_price']:.6f} | "
              f"Imbalance: {analysis['signals']['pressure']['imbalance']:+.3f} | "
              f"Signal: {signal['action'].upper()} ({signal['confidence']:.2f})")

    # Save results
    if args.output:
        output_data = {
            "pool": data["pool"],
            "analysis_start": data["collection_start"],
            "analysis_end": data["collection_end"],
            "snapshot_count": len(analyses),
            "analyses": analyses
        }

        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"\n✓ Saved {len(analyses)} analyses to {args.output}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
