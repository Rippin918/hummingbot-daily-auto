#!/usr/bin/env python3
"""
Avellaneda-Stoikov Market Making Analytics
Inventory management, spread calculation, and price impact estimation

Components:
1. Inventory Skew Calculator - Adjusts quotes based on inventory risk
2. Kyle's Lambda Estimator - Measures price impact for spread sizing
3. Avellaneda-Stoikov Spread Calculator - Optimal bid/ask spread

References:
- Avellaneda & Stoikov (2008): "High-frequency trading in a limit order book"
- Kyle (1985): "Continuous Auctions and Insider Trading"
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import math


@dataclass
class InventorySignal:
    """Inventory-based trading signal"""
    current_inventory: float  # Current position (positive = long, negative = short)
    target_inventory: float  # Target position (usually 0)
    inventory_ratio: float  # Current / Max (risk metric)
    reservation_price: float  # Adjusted mid price
    bid_skew: float  # Adjustment to bid (negative = lower bid)
    ask_skew: float  # Adjustment to ask (positive = higher ask)
    urgency: str  # "none", "low", "medium", "high", "critical"
    recommendation: str  # Action to take


@dataclass
class KyleLambdaResult:
    """Kyle's Lambda price impact estimate"""
    lambda_value: float  # Price impact per unit volume
    r_squared: float  # Regression R²
    confidence: float  # Confidence in estimate
    liquidity_score: float  # Derived liquidity metric (1/lambda)
    spread_multiplier: float  # Suggested spread adjustment


@dataclass
class AvellanedaStoikovSpread:
    """Optimal spread calculation"""
    optimal_spread: float  # Full spread (bid-ask)
    bid_offset: float  # Distance from mid to bid
    ask_offset: float  # Distance from mid to ask
    reservation_price: float  # Inventory-adjusted mid
    bid_price: float  # Absolute bid price
    ask_price: float  # Absolute ask price
    gamma: float  # Risk aversion used
    sigma: float  # Volatility used
    inventory_adj: float  # Inventory adjustment applied


class InventoryManager:
    """
    Manage inventory risk for market making
    Implements Avellaneda-Stoikov inventory skewing
    """

    def __init__(
        self,
        max_inventory: float = 100.0,  # Maximum position size
        target_inventory: float = 0.0,  # Target position (usually 0)
        gamma: float = 0.1,  # Risk aversion parameter
        T: float = 1.0  # Time horizon (in same units as volatility)
    ):
        """
        Initialize inventory manager

        Args:
            max_inventory: Maximum absolute inventory
            target_inventory: Target inventory level
            gamma: Risk aversion (higher = more conservative)
            T: Time horizon for inventory management
        """
        self.max_inventory = max_inventory
        self.target_inventory = target_inventory
        self.gamma = gamma
        self.T = T

        # Current state
        self.current_inventory = 0.0

    def update_inventory(self, inventory: float):
        """Update current inventory position"""
        self.current_inventory = inventory

    def add_trade(self, size: float, side: str):
        """
        Add a trade to inventory

        Args:
            size: Trade size (positive)
            side: "buy" or "sell"
        """
        if side == "buy":
            self.current_inventory += size
        elif side == "sell":
            self.current_inventory -= size

    def calculate_reservation_price(
        self,
        mid_price: float,
        volatility: float,
        time_remaining: Optional[float] = None
    ) -> float:
        """
        Calculate reservation price (inventory-adjusted mid price)

        r = s - q * γ * σ² * (T - t)

        where:
        s = mid price
        q = current inventory
        γ = risk aversion
        σ = volatility
        T - t = time remaining

        Args:
            mid_price: Current mid price
            volatility: Price volatility (same time unit as T)
            time_remaining: Time remaining (defaults to T)

        Returns:
            Reservation price
        """
        if time_remaining is None:
            time_remaining = self.T

        # Calculate inventory adjustment
        inventory_adj = self.current_inventory * self.gamma * (volatility ** 2) * time_remaining

        # Reservation price
        reservation_price = mid_price - inventory_adj

        return reservation_price

    def calculate_skew(
        self,
        mid_price: float,
        volatility: float,
        base_spread: float = 0.001  # Base spread as fraction
    ) -> Tuple[float, float]:
        """
        Calculate bid/ask skew based on inventory

        High inventory (long) → lower ask, raise bid (incentivize selling)
        Low inventory (short) → raise ask, lower bid (incentivize buying)

        Returns:
            (bid_offset, ask_offset) relative to reservation price
        """
        # Get reservation price
        reservation_price = self.calculate_reservation_price(mid_price, volatility)

        # Base half-spread
        half_spread = base_spread / 2

        # Inventory ratio (-1 to +1)
        inventory_ratio = np.clip(
            self.current_inventory / self.max_inventory,
            -1.0,
            1.0
        )

        # Skew spreads based on inventory
        # Positive inventory → widen ask, tighten bid
        # Negative inventory → widen bid, tighten ask
        bid_offset = half_spread * (1 - inventory_ratio * 0.5)
        ask_offset = half_spread * (1 + inventory_ratio * 0.5)

        return (bid_offset, ask_offset)

    def get_inventory_signal(
        self,
        mid_price: float,
        volatility: float
    ) -> InventorySignal:
        """
        Generate comprehensive inventory signal

        Returns:
            InventorySignal with recommendations
        """
        # Calculate reservation price
        reservation_price = self.calculate_reservation_price(mid_price, volatility)

        # Inventory ratio
        inventory_ratio = self.current_inventory / self.max_inventory

        # Determine urgency
        abs_ratio = abs(inventory_ratio)
        if abs_ratio > 0.9:
            urgency = "critical"
        elif abs_ratio > 0.7:
            urgency = "high"
        elif abs_ratio > 0.5:
            urgency = "medium"
        elif abs_ratio > 0.3:
            urgency = "low"
        else:
            urgency = "none"

        # Generate recommendation
        if inventory_ratio > 0.7:
            recommendation = "aggressively_sell"
        elif inventory_ratio > 0.3:
            recommendation = "prefer_sell"
        elif inventory_ratio < -0.7:
            recommendation = "aggressively_buy"
        elif inventory_ratio < -0.3:
            recommendation = "prefer_buy"
        else:
            recommendation = "balanced"

        # Calculate skews
        bid_skew = (reservation_price - mid_price) - (mid_price * 0.001)
        ask_skew = (reservation_price - mid_price) + (mid_price * 0.001)

        return InventorySignal(
            current_inventory=self.current_inventory,
            target_inventory=self.target_inventory,
            inventory_ratio=inventory_ratio,
            reservation_price=reservation_price,
            bid_skew=bid_skew,
            ask_skew=ask_skew,
            urgency=urgency,
            recommendation=recommendation
        )


class KyleLambdaEstimator:
    """
    Estimate Kyle's Lambda (price impact coefficient)

    λ measures how much price moves per unit of order flow
    High λ = illiquid market → need wider spreads
    Low λ = liquid market → can tighten spreads

    Regression: ΔP_t = λ * Q_t + ε_t
    where:
    ΔP_t = price change
    Q_t = signed order flow (positive = buy, negative = sell)
    """

    def __init__(self, window_size: int = 100):
        """
        Initialize Kyle's Lambda estimator

        Args:
            window_size: Number of trades to use for estimation
        """
        self.window_size = window_size
        self.price_changes = []
        self.signed_volumes = []

    def add_trade(
        self,
        price_before: float,
        price_after: float,
        volume: float,
        side: str  # "buy" or "sell"
    ):
        """
        Add a trade observation

        Args:
            price_before: Price before trade
            price_after: Price after trade
            volume: Trade volume
            side: Trade side
        """
        # Calculate price change
        price_change = (price_after - price_before) / price_before

        # Signed volume (positive for buy, negative for sell)
        signed_volume = volume if side == "buy" else -volume

        self.price_changes.append(price_change)
        self.signed_volumes.append(signed_volume)

        # Maintain window size
        if len(self.price_changes) > self.window_size:
            self.price_changes.pop(0)
            self.signed_volumes.pop(0)

    def estimate_lambda(self) -> Optional[KyleLambdaResult]:
        """
        Estimate Kyle's Lambda using OLS regression

        Returns:
            KyleLambdaResult or None if insufficient data
        """
        if len(self.price_changes) < 10:
            return None

        # Convert to numpy arrays
        y = np.array(self.price_changes)
        X = np.array(self.signed_volumes)

        # OLS regression: y = λX + ε
        # λ = Cov(y,X) / Var(X)
        if np.var(X) == 0:
            return None

        lambda_value = np.cov(y, X)[0, 1] / np.var(X)

        # Calculate R²
        y_pred = lambda_value * X
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Confidence based on R² and sample size
        confidence = min(r_squared * (len(self.price_changes) / self.window_size), 1.0)

        # Liquidity score (inverse of lambda)
        liquidity_score = 1.0 / abs(lambda_value) if lambda_value != 0 else float('inf')

        # Spread multiplier based on lambda
        # High lambda = illiquid = wider spreads
        spread_multiplier = max(1.0, min(abs(lambda_value) * 100, 3.0))

        return KyleLambdaResult(
            lambda_value=lambda_value,
            r_squared=r_squared,
            confidence=confidence,
            liquidity_score=liquidity_score,
            spread_multiplier=spread_multiplier
        )


class AvellanedaStoikovCalculator:
    """
    Calculate optimal spreads using Avellaneda-Stoikov model

    Optimal bid/ask spreads around reservation price:
    δ_bid = δ_ask = γσ²(T-t) + (2/γ)ln(1 + γ/k)

    where:
    γ = risk aversion
    σ = volatility
    T-t = time remaining
    k = order arrival rate
    """

    def __init__(
        self,
        gamma: float = 0.1,  # Risk aversion
        k: float = 1.5,  # Order arrival rate (orders per time unit)
        T: float = 1.0  # Time horizon
    ):
        """
        Initialize Avellaneda-Stoikov calculator

        Args:
            gamma: Risk aversion (higher = wider spreads)
            k: Order arrival rate
            T: Time horizon
        """
        self.gamma = gamma
        self.k = k
        self.T = T

    def calculate_optimal_spread(
        self,
        mid_price: float,
        volatility: float,
        inventory: float = 0.0,
        time_remaining: Optional[float] = None,
        kyle_lambda: Optional[float] = None
    ) -> AvellanedaStoikovSpread:
        """
        Calculate optimal bid/ask spread

        Args:
            mid_price: Current mid price
            volatility: Price volatility
            inventory: Current inventory position
            time_remaining: Time remaining (defaults to T)
            kyle_lambda: Optional Kyle's lambda for liquidity adjustment

        Returns:
            AvellanedaStoikovSpread with bid/ask prices
        """
        if time_remaining is None:
            time_remaining = self.T

        # Calculate reservation price (inventory adjustment)
        inventory_adj = inventory * self.gamma * (volatility ** 2) * time_remaining
        reservation_price = mid_price - inventory_adj

        # Calculate optimal half-spread
        # δ = γσ²T + (2/γ)ln(1 + γ/k)
        spread_term1 = self.gamma * (volatility ** 2) * time_remaining
        spread_term2 = (2 / self.gamma) * math.log(1 + self.gamma / self.k)

        half_spread = spread_term1 + spread_term2

        # Adjust for illiquidity (Kyle's lambda)
        if kyle_lambda is not None and kyle_lambda > 0:
            liquidity_adj = 1 + (kyle_lambda * 10)  # Scale factor
            half_spread *= liquidity_adj

        # Calculate bid/ask offsets
        bid_offset = half_spread
        ask_offset = half_spread

        # Calculate absolute prices
        bid_price = reservation_price - bid_offset
        ask_price = reservation_price + ask_offset

        optimal_spread = bid_offset + ask_offset

        return AvellanedaStoikovSpread(
            optimal_spread=optimal_spread,
            bid_offset=bid_offset,
            ask_offset=ask_offset,
            reservation_price=reservation_price,
            bid_price=bid_price,
            ask_price=ask_price,
            gamma=self.gamma,
            sigma=volatility,
            inventory_adj=inventory_adj
        )


# Example usage
if __name__ == "__main__":
    # Inventory management example
    inventory_mgr = InventoryManager(max_inventory=100.0, gamma=0.1)
    inventory_mgr.update_inventory(70.0)  # Long 70 units

    signal = inventory_mgr.get_inventory_signal(mid_price=100.0, volatility=0.2)
    print(f"Inventory Signal:")
    print(f"  Current: {signal.current_inventory:.1f}")
    print(f"  Ratio: {signal.inventory_ratio:.2f}")
    print(f"  Urgency: {signal.urgency}")
    print(f"  Recommendation: {signal.recommendation}")
    print(f"  Reservation Price: ${signal.reservation_price:.2f}")

    # Kyle's Lambda example
    kyle = KyleLambdaEstimator(window_size=50)

    # Simulate trades
    price = 100.0
    for i in range(100):
        side = "buy" if np.random.random() > 0.5 else "sell"
        volume = np.random.uniform(1, 10)
        price_before = price
        price += np.random.normal(0, 0.1) + (0.05 if side == "buy" else -0.05)
        kyle.add_trade(price_before, price, volume, side)

    lambda_result = kyle.estimate_lambda()
    if lambda_result:
        print(f"\nKyle's Lambda:")
        print(f"  λ = {lambda_result.lambda_value:.6f}")
        print(f"  R² = {lambda_result.r_squared:.3f}")
        print(f"  Liquidity Score: {lambda_result.liquidity_score:.1f}")
        print(f"  Spread Multiplier: {lambda_result.spread_multiplier:.2f}x")

    # Avellaneda-Stoikov example
    as_calc = AvellanedaStoikovCalculator(gamma=0.1, k=1.5)
    spread = as_calc.calculate_optimal_spread(
        mid_price=100.0,
        volatility=0.2,
        inventory=50.0
    )

    print(f"\nAvellaneda-Stoikov Optimal Spread:")
    print(f"  Reservation Price: ${spread.reservation_price:.2f}")
    print(f"  Bid: ${spread.bid_price:.2f} (offset: {spread.bid_offset:.4f})")
    print(f"  Ask: ${spread.ask_price:.2f} (offset: {spread.ask_offset:.4f})")
    print(f"  Full Spread: {spread.optimal_spread:.4f} ({spread.optimal_spread/spread.reservation_price*100:.2f}%)")
