#!/usr/bin/env python3
"""
Orderflow Imbalance Analysis for Market Making
Detects mean-reverting vs trending regimes

Key Metrics:
1. Orderbook Imbalance - Bid vs ask liquidity
2. Imbalance Half-Life - How long imbalances persist
3. Autocorrelation - Persistence of order flow
4. Regime Classification - Mean-reverting vs trending

Trading Strategy:
- Short half-life (mean-reverting) → tighter spreads, more aggressive
- Long half-life (trending) → wider spreads, skew in trend direction
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import deque
from dataclasses import dataclass
import math


@dataclass
class ImbalanceResult:
    """Orderflow imbalance analysis result"""
    current_imbalance: float  # Current bid-ask imbalance
    half_life: Optional[float]  # Imbalance half-life (blocks/seconds)
    autocorrelation: float  # Order flow autocorrelation
    regime: str  # "mean_reverting", "trending", "neutral"
    persistence: float  # 0-1, how long imbalances last
    recommendation: str  # Strategy recommendation
    confidence: float  # Confidence in regime classification


class OrderflowAnalyzer:
    """
    Analyze orderflow imbalance dynamics
    Determines if market is mean-reverting or trending
    """

    def __init__(
        self,
        window_size: int = 100,  # Lookback window
        imbalance_threshold: float = 0.2  # Threshold for significant imbalance
    ):
        """
        Initialize orderflow analyzer

        Args:
            window_size: Number of periods for analysis
            imbalance_threshold: Minimum imbalance to consider significant
        """
        self.window_size = window_size
        self.imbalance_threshold = imbalance_threshold

        # Historical data
        self.imbalances = deque(maxlen=window_size)
        self.timestamps = deque(maxlen=window_size)

    def calculate_imbalance(
        self,
        bid_liquidity: float,
        ask_liquidity: float
    ) -> float:
        """
        Calculate orderbook imbalance

        Imbalance = (Bid - Ask) / (Bid + Ask)

        Ranges from -1 (all ask) to +1 (all bid)
        Positive = bullish (more bid liquidity)
        Negative = bearish (more ask liquidity)

        Args:
            bid_liquidity: Total bid side liquidity
            ask_liquidity: Total ask side liquidity

        Returns:
            Imbalance ratio
        """
        total = bid_liquidity + ask_liquidity
        if total == 0:
            return 0.0

        return (bid_liquidity - ask_liquidity) / total

    def add_observation(
        self,
        bid_liquidity: float,
        ask_liquidity: float,
        timestamp: Optional[int] = None
    ):
        """
        Add an orderbook observation

        Args:
            bid_liquidity: Bid side liquidity
            ask_liquidity: Ask side liquidity
            timestamp: Optional timestamp
        """
        imbalance = self.calculate_imbalance(bid_liquidity, ask_liquidity)
        self.imbalances.append(imbalance)
        if timestamp is not None:
            self.timestamps.append(timestamp)

    def calculate_half_life(self) -> Optional[float]:
        """
        Calculate imbalance half-life using autoregression

        Half-life = time for imbalance to decay to half its value
        Short half-life = mean-reverting
        Long half-life = trending/persistent

        Uses AR(1) model: x_t = φ*x_{t-1} + ε_t
        Half-life = -ln(2) / ln(φ)

        Returns:
            Half-life in periods (or None if insufficient data)
        """
        if len(self.imbalances) < 10:
            return None

        # Fit AR(1) model
        imbalances = np.array(self.imbalances)

        # Lag-1 autocorrelation coefficient (φ)
        x_t = imbalances[1:]
        x_t_1 = imbalances[:-1]

        # OLS: φ = Cov(x_t, x_{t-1}) / Var(x_{t-1})
        if np.var(x_t_1) == 0:
            return None

        phi = np.cov(x_t, x_t_1)[0, 1] / np.var(x_t_1)

        # Calculate half-life
        if phi <= 0 or phi >= 1:
            # No mean reversion or explosive
            return float('inf')

        half_life = -math.log(2) / math.log(phi)

        return half_life

    def calculate_autocorrelation(self, lag: int = 1) -> float:
        """
        Calculate autocorrelation of order flow

        High autocorrelation = persistent trends
        Low autocorrelation = random/mean-reverting

        Args:
            lag: Lag for autocorrelation (default 1)

        Returns:
            Autocorrelation coefficient (-1 to 1)
        """
        if len(self.imbalances) < lag + 10:
            return 0.0

        imbalances = np.array(self.imbalances)

        # Calculate autocorrelation
        x_t = imbalances[lag:]
        x_t_lag = imbalances[:-lag]

        # Pearson correlation
        if np.std(x_t) == 0 or np.std(x_t_lag) == 0:
            return 0.0

        autocorr = np.corrcoef(x_t, x_t_lag)[0, 1]

        return autocorr

    def classify_regime(self) -> ImbalanceResult:
        """
        Classify market regime based on orderflow dynamics

        Regime Types:
        - mean_reverting: Short half-life, low autocorrelation → tighten spreads
        - trending: Long half-life, high autocorrelation → widen spreads, skew
        - neutral: No clear pattern

        Returns:
            ImbalanceResult with regime classification
        """
        if len(self.imbalances) < 20:
            return ImbalanceResult(
                current_imbalance=0.0,
                half_life=None,
                autocorrelation=0.0,
                regime="unknown",
                persistence=0.0,
                recommendation="insufficient_data",
                confidence=0.0
            )

        # Calculate metrics
        current_imbalance = self.imbalances[-1]
        half_life = self.calculate_half_life()
        autocorr = self.calculate_autocorrelation(lag=1)

        # Persistence score (0-1)
        # Based on autocorrelation and half-life
        if half_life is not None and half_life != float('inf'):
            # Normalize half-life to 0-1 scale
            # Short half-life (e.g., 5) → low persistence
            # Long half-life (e.g., 50) → high persistence
            hl_score = min(half_life / 50.0, 1.0)
        else:
            hl_score = 1.0  # Assume high persistence if infinite

        ac_score = (autocorr + 1) / 2  # Convert from [-1,1] to [0,1]

        persistence = (hl_score + ac_score) / 2

        # Classify regime
        if persistence < 0.3:
            regime = "mean_reverting"
            recommendation = "tighten_spreads_aggressive_quotes"
        elif persistence > 0.7:
            regime = "trending"
            if abs(current_imbalance) > self.imbalance_threshold:
                direction = "bullish" if current_imbalance > 0 else "bearish"
                recommendation = f"widen_spreads_skew_{direction}"
            else:
                recommendation = "widen_spreads_neutral"
        else:
            regime = "neutral"
            recommendation = "standard_spreads"

        # Confidence based on sample size and consistency
        confidence = min(len(self.imbalances) / self.window_size, 1.0)

        return ImbalanceResult(
            current_imbalance=current_imbalance,
            half_life=half_life,
            autocorrelation=autocorr,
            regime=regime,
            persistence=persistence,
            recommendation=recommendation,
            confidence=confidence
        )

    def get_trade_aggressiveness(self, regime_result: ImbalanceResult) -> float:
        """
        Calculate how aggressive quotes should be based on regime

        Returns:
            Aggressiveness multiplier (0.5 to 2.0)
            < 1.0 = tighter spreads
            > 1.0 = wider spreads
        """
        if regime_result.regime == "mean_reverting":
            # Tighten spreads significantly
            return 0.5 + (regime_result.persistence * 0.3)
        elif regime_result.regime == "trending":
            # Widen spreads significantly
            return 1.5 + (regime_result.persistence * 0.5)
        else:
            # Neutral
            return 1.0

    def detect_regime_shift(self, lookback: int = 20) -> Optional[Dict]:
        """
        Detect recent regime shifts

        Useful for adapting strategy dynamically

        Args:
            lookback: Periods to check for shift

        Returns:
            Dictionary with shift info or None
        """
        if len(self.imbalances) < lookback * 2:
            return None

        # Split into recent and previous periods
        recent = list(self.imbalances)[-lookback:]
        previous = list(self.imbalances)[-lookback*2:-lookback]

        # Calculate autocorrelation for each
        recent_autocorr = np.corrcoef(recent[1:], recent[:-1])[0, 1] if len(recent) > 1 else 0
        prev_autocorr = np.corrcoef(previous[1:], previous[:-1])[0, 1] if len(previous) > 1 else 0

        # Check for significant change
        change = abs(recent_autocorr - prev_autocorr)

        if change > 0.3:  # Threshold for significant shift
            # Determine shift direction
            if recent_autocorr > prev_autocorr + 0.3:
                shift_type = "mean_reverting_to_trending"
            elif recent_autocorr < prev_autocorr - 0.3:
                shift_type = "trending_to_mean_reverting"
            else:
                shift_type = "unknown"

            return {
                "shift_detected": True,
                "shift_type": shift_type,
                "prev_autocorr": prev_autocorr,
                "recent_autocorr": recent_autocorr,
                "change": change,
                "recommendation": "adjust_strategy"
            }

        return None


# Example usage
if __name__ == "__main__":
    # Initialize analyzer
    analyzer = OrderflowAnalyzer(window_size=100)

    # Simulate mean-reverting regime
    print("Simulating Mean-Reverting Regime:")
    imbalance = 0.0
    for i in range(100):
        # Mean-reverting behavior: imbalance oscillates around 0
        imbalance = 0.7 * imbalance - 0.3 * imbalance + np.random.normal(0, 0.1)
        bid_liq = 1000 * (1 + imbalance)
        ask_liq = 1000 * (1 - imbalance)
        analyzer.add_observation(bid_liq, ask_liq)

    result = analyzer.classify_regime()
    print(f"  Regime: {result.regime}")
    print(f"  Half-life: {result.half_life:.1f}" if result.half_life else "  Half-life: N/A")
    print(f"  Autocorrelation: {result.autocorrelation:.3f}")
    print(f"  Persistence: {result.persistence:.3f}")
    print(f"  Recommendation: {result.recommendation}")

    # Reset and simulate trending regime
    analyzer = OrderflowAnalyzer(window_size=100)

    print("\nSimulating Trending Regime:")
    imbalance = 0.0
    for i in range(100):
        # Trending behavior: imbalance has momentum
        imbalance = 0.95 * imbalance + 0.05 * np.random.normal(0, 0.1)
        bid_liq = 1000 * (1 + imbalance)
        ask_liq = 1000 * (1 - imbalance)
        analyzer.add_observation(bid_liq, ask_liq)

    result = analyzer.classify_regime()
    print(f"  Regime: {result.regime}")
    print(f"  Half-life: {result.half_life:.1f}" if result.half_life and result.half_life != float('inf') else "  Half-life: ∞")
    print(f"  Autocorrelation: {result.autocorrelation:.3f}")
    print(f"  Persistence: {result.persistence:.3f}")
    print(f"  Recommendation: {result.recommendation}")
