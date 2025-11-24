#!/usr/bin/env python3
"""
Volatility Estimators for Market Making
Provides σ (sigma) parameter for Avellaneda-Stoikov model

Estimators:
1. Realized Volatility - Classic close-to-close returns
2. Parkinson Estimator - Uses high-low range (more efficient)
3. Garman-Klass Estimator - Uses OHLC (most efficient, 7.4x better than close-to-close)

For Avellaneda-Stoikov optimal spread calculation:
  spread = γσ²T + (2/γ)ln(1 + γ/k)

Where:
  σ = volatility (annualized)
  γ = risk aversion parameter
  T = time horizon
  k = order arrival rate
"""

import numpy as np
from typing import List, Dict, Optional
from collections import deque
from dataclasses import dataclass
import math


@dataclass
class VolatilityResult:
    """Volatility estimation result"""
    realized_vol: float  # Close-to-close volatility
    parkinson_vol: float  # High-low volatility
    garman_klass_vol: float  # OHLC volatility
    recommended_vol: float  # Best estimate (usually Garman-Klass)
    confidence: float  # Confidence in estimate (0-1)
    num_periods: int  # Number of periods used
    annualized: bool  # Whether volatility is annualized


class VolatilityEstimator:
    """
    Estimate volatility using multiple methods
    Critical for Avellaneda-Stoikov spread sizing
    """

    # Annualization factors
    BLOCKS_PER_YEAR = 365.25 * 24 * 60 * 60 / 2  # Assuming 2s block time on Linea

    def __init__(
        self,
        window_periods: int = 100,  # Number of periods for rolling window
        min_periods: int = 20,      # Minimum periods required
        annualize: bool = True      # Annualize volatility
    ):
        """
        Initialize volatility estimator

        Args:
            window_periods: Rolling window size
            min_periods: Minimum periods to calculate
            annualize: Whether to annualize volatility
        """
        self.window_periods = window_periods
        self.min_periods = min_periods
        self.annualize = annualize

        # State: store OHLC candles
        self.candles = deque(maxlen=window_periods)

    def add_candle(
        self,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        timestamp: Optional[int] = None
    ):
        """
        Add a candle (OHLC) to the estimator

        Args:
            open_price: Opening price
            high_price: High price
            low_price: Low price
            close_price: Closing price
            timestamp: Optional timestamp
        """
        candle = {
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "timestamp": timestamp
        }
        self.candles.append(candle)

    def realized_volatility(self) -> Optional[float]:
        """
        Calculate realized volatility using close-to-close returns

        σ_realized = sqrt(Σ(r_t²) / (n-1))
        where r_t = ln(P_t / P_{t-1})

        Returns:
            Annualized volatility or None if insufficient data
        """
        if len(self.candles) < self.min_periods:
            return None

        # Calculate log returns
        returns = []
        for i in range(1, len(self.candles)):
            prev_close = self.candles[i-1]["close"]
            curr_close = self.candles[i]["close"]

            if prev_close > 0 and curr_close > 0:
                log_return = math.log(curr_close / prev_close)
                returns.append(log_return)

        if len(returns) < 2:
            return None

        # Calculate volatility
        vol = np.std(returns, ddof=1)  # Sample standard deviation

        # Annualize if requested
        if self.annualize:
            vol *= math.sqrt(self.BLOCKS_PER_YEAR / len(returns))

        return vol

    def parkinson_volatility(self) -> Optional[float]:
        """
        Calculate Parkinson high-low volatility estimator

        σ_P = sqrt((1/(4n*ln(2))) * Σ(ln(H_t/L_t))²)

        More efficient than close-to-close (uses range information)
        ~1.67x more efficient than realized volatility

        Returns:
            Annualized volatility or None if insufficient data
        """
        if len(self.candles) < self.min_periods:
            return None

        # Calculate high-low ratios
        hl_ratios = []
        for candle in self.candles:
            high = candle["high"]
            low = candle["low"]

            if high > 0 and low > 0 and high >= low:
                hl_ratio = math.log(high / low)
                hl_ratios.append(hl_ratio ** 2)

        if len(hl_ratios) < 2:
            return None

        # Parkinson estimator
        n = len(hl_ratios)
        vol = math.sqrt(sum(hl_ratios) / (4 * n * math.log(2)))

        # Annualize if requested
        if self.annualize:
            vol *= math.sqrt(self.BLOCKS_PER_YEAR / n)

        return vol

    def garman_klass_volatility(self) -> Optional[float]:
        """
        Calculate Garman-Klass OHLC volatility estimator

        σ_GK² = (1/n) * Σ[(1/2)(ln(H_t/L_t))² - (2ln(2)-1)(ln(C_t/O_t))²]

        Most efficient estimator using OHLC data
        ~7.4x more efficient than close-to-close realized volatility

        Returns:
            Annualized volatility or None if insufficient data
        """
        if len(self.candles) < self.min_periods:
            return None

        variances = []

        for candle in self.candles:
            open_price = candle["open"]
            high_price = candle["high"]
            low_price = candle["low"]
            close_price = candle["close"]

            # Validate prices
            if any(p <= 0 for p in [open_price, high_price, low_price, close_price]):
                continue
            if high_price < low_price:
                continue

            # Garman-Klass formula
            hl_term = 0.5 * (math.log(high_price / low_price) ** 2)
            co_term = (2 * math.log(2) - 1) * (math.log(close_price / open_price) ** 2)

            variance = hl_term - co_term
            variances.append(variance)

        if len(variances) < 2:
            return None

        # Calculate volatility
        mean_variance = np.mean(variances)
        vol = math.sqrt(mean_variance)

        # Annualize if requested
        if self.annualize:
            vol *= math.sqrt(self.BLOCKS_PER_YEAR / len(variances))

        return vol

    def yang_zhang_volatility(self) -> Optional[float]:
        """
        Calculate Yang-Zhang volatility estimator (drift-independent)

        Even more sophisticated, accounts for overnight jumps and drift
        Most accurate for assets with opening jumps

        σ_YZ² = σ_o² + k*σ_c² + (1-k)*σ_rs²

        where:
        σ_o² = overnight volatility (open-to-previous-close)
        σ_c² = close-to-open volatility
        σ_rs² = Rogers-Satchell volatility

        Returns:
            Annualized volatility or None if insufficient data
        """
        if len(self.candles) < self.min_periods + 1:
            return None

        # Calculate components
        overnight_returns = []
        rs_components = []

        for i in range(1, len(self.candles)):
            prev_candle = self.candles[i-1]
            curr_candle = self.candles[i]

            prev_close = prev_candle["close"]
            curr_open = curr_candle["open"]
            curr_high = curr_candle["high"]
            curr_low = curr_candle["low"]
            curr_close = curr_candle["close"]

            # Validate
            if any(p <= 0 for p in [prev_close, curr_open, curr_high, curr_low, curr_close]):
                continue

            # Overnight return
            overnight_ret = math.log(curr_open / prev_close)
            overnight_returns.append(overnight_ret)

            # Rogers-Satchell component
            rs = (math.log(curr_high / curr_close) * math.log(curr_high / curr_open) +
                  math.log(curr_low / curr_close) * math.log(curr_low / curr_open))
            rs_components.append(rs)

        if len(overnight_returns) < 2 or len(rs_components) < 2:
            return None

        # Calculate variances
        sigma_o_sq = np.var(overnight_returns, ddof=1)
        sigma_rs_sq = np.mean(rs_components)

        # Yang-Zhang with k=0.34 (optimal for daily data)
        k = 0.34
        sigma_yz_sq = sigma_o_sq + k * sigma_rs_sq

        vol = math.sqrt(abs(sigma_yz_sq))

        # Annualize if requested
        if self.annualize:
            vol *= math.sqrt(self.BLOCKS_PER_YEAR / len(overnight_returns))

        return vol

    def estimate(self) -> Optional[VolatilityResult]:
        """
        Estimate volatility using all methods and return best estimate

        Returns:
            VolatilityResult with all estimators
        """
        if len(self.candles) < self.min_periods:
            return None

        realized = self.realized_volatility()
        parkinson = self.parkinson_volatility()
        garman_klass = self.garman_klass_volatility()

        # Choose recommended (prefer Garman-Klass if available)
        if garman_klass is not None:
            recommended = garman_klass
            confidence = 0.9
        elif parkinson is not None:
            recommended = parkinson
            confidence = 0.7
        elif realized is not None:
            recommended = realized
            confidence = 0.5
        else:
            return None

        # Adjust confidence based on number of periods
        confidence *= min(len(self.candles) / self.window_periods, 1.0)

        return VolatilityResult(
            realized_vol=realized or 0.0,
            parkinson_vol=parkinson or 0.0,
            garman_klass_vol=garman_klass or 0.0,
            recommended_vol=recommended,
            confidence=confidence,
            num_periods=len(self.candles),
            annualized=self.annualize
        )

    def estimate_from_ticks(self, tick_snapshots: List[Dict], period_blocks: int = 10) -> Optional[VolatilityResult]:
        """
        Estimate volatility from tick snapshots by constructing OHLC candles

        Args:
            tick_snapshots: List of tick snapshot dictionaries
            period_blocks: Blocks per candle

        Returns:
            VolatilityResult
        """
        if not tick_snapshots:
            return None

        # Group snapshots into candles
        candles = []
        current_candle = None
        start_block = tick_snapshots[0]["block"]

        for snapshot in tick_snapshots:
            block = snapshot["block"]
            price = snapshot["current_price"]

            # Determine which candle this belongs to
            candle_index = (block - start_block) // period_blocks

            # Start new candle if needed
            if current_candle is None or current_candle["index"] != candle_index:
                if current_candle is not None:
                    # Close previous candle
                    candles.append(current_candle)

                # Start new candle
                current_candle = {
                    "index": candle_index,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "timestamp": snapshot["timestamp"]
                }
            else:
                # Update current candle
                current_candle["high"] = max(current_candle["high"], price)
                current_candle["low"] = min(current_candle["low"], price)
                current_candle["close"] = price

        # Add final candle
        if current_candle is not None:
            candles.append(current_candle)

        # Add candles to estimator
        for candle in candles:
            self.add_candle(
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle.get("timestamp")
            )

        return self.estimate()


# Example usage
if __name__ == "__main__":
    # Initialize estimator
    vol_est = VolatilityEstimator(window_periods=50, annualize=True)

    # Simulate price data (OHLC)
    np.random.seed(42)
    base_price = 100.0
    for i in range(100):
        # Random walk
        change = np.random.normal(0, 0.02)  # 2% daily vol
        open_price = base_price
        close_price = base_price * (1 + change)
        high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.01)))
        low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.01)))

        vol_est.add_candle(open_price, high_price, low_price, close_price)
        base_price = close_price

    # Estimate volatility
    result = vol_est.estimate()
    if result:
        print(f"Volatility Estimates (annualized):")
        print(f"  Realized:      {result.realized_vol:.2%}")
        print(f"  Parkinson:     {result.parkinson_vol:.2%}")
        print(f"  Garman-Klass:  {result.garman_klass_vol:.2%}")
        print(f"  Recommended:   {result.recommended_vol:.2%} (confidence: {result.confidence:.1%})")
        print(f"  Periods:       {result.num_periods}")
