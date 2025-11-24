#!/usr/bin/env python3
"""
Cross-DEX Analytics for Multi-Venue Market Making
Arbitrage detection, spread matrix, unified liquidity, best execution routing

Supports: Lynex, Nile, SyncSwap, KyberSwap, Etherex on Linea
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import time


@dataclass
class ArbitrageOpportunity:
    """Cross-DEX arbitrage opportunity"""
    pair: str
    buy_dex: str
    sell_dex: str
    buy_price: float
    sell_price: float
    spread_bps: float  # Basis points
    gross_profit_pct: float
    est_net_profit_pct: float  # After estimated gas
    size_available: float  # Max size for this arb
    confidence: float
    timestamp: int


@dataclass
class DEXSnapshot:
    """Snapshot from a single DEX"""
    dex: str
    pair: str
    mid_price: float
    bid_price: float
    ask_price: float
    bid_liquidity: float
    ask_liquidity: float
    timestamp: int


class CrossDEXAnalyzer:
    """
    Analyze opportunities across multiple DEXes on Linea
    """

    # Estimated gas costs (in USD) for different operations
    GAS_COSTS = {
        "swap": 3.0,  # Single swap
        "arb": 8.0,   # Two swaps + routing
    }

    # Minimum profitable arb (bps after gas)
    MIN_ARB_BPS = 20  # 0.2%

    def __init__(self, dexes: List[str]):
        """
        Initialize cross-DEX analyzer

        Args:
            dexes: List of DEX names to monitor
        """
        self.dexes = dexes
        self.latest_snapshots: Dict[Tuple[str, str], DEXSnapshot] = {}  # (dex, pair) -> snapshot

    def update_snapshot(self, snapshot: DEXSnapshot):
        """Update snapshot for a DEX/pair"""
        key = (snapshot.dex, snapshot.pair)
        self.latest_snapshots[key] = snapshot

    def get_spread_matrix(self, pair: str) -> Dict:
        """
        Get price spread matrix across all DEXes for a pair

        Returns:
            Dictionary with spread data
        """
        pair_snapshots = {
            dex: snapshot
            for (d, p), snapshot in self.latest_snapshots.items()
            if p == pair and d == dex
        }

        if not pair_snapshots:
            return {"error": "no_data"}

        # Build matrix
        prices = {dex: snap.mid_price for dex, snap in pair_snapshots.items()}
        bids = {dex: snap.bid_price for dex, snap in pair_snapshots.items()}
        asks = {dex: snap.ask_price for dex, snap in pair_snapshots.items()}

        # Find best bid/ask across all venues
        best_bid = max(bids.values()) if bids else 0
        best_ask = min(asks.values()) if asks else float('inf')
        best_bid_dex = max(bids, key=bids.get) if bids else None
        best_ask_dex = min(asks, key=asks.get) if asks else None

        # Calculate spreads from best
        spread_from_best = {
            dex: {
                "bid_diff_bps": ((price - best_bid) / best_bid * 10000) if best_bid > 0 else 0,
                "ask_diff_bps": ((price - best_ask) / best_ask * 10000) if best_ask > 0 else 0
            }
            for dex, price in prices.items()
        }

        return {
            "pair": pair,
            "prices": prices,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "best_bid_dex": best_bid_dex,
            "best_ask_dex": best_ask_dex,
            "nbbo_spread_bps": ((best_ask - best_bid) / best_bid * 10000) if best_bid > 0 else 0,
            "spread_from_best": spread_from_best,
            "timestamp": int(time.time())
        }

    def detect_arbitrage(self, pair: str, min_profit_bps: Optional[float] = None) -> List[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunities for a pair across all DEXes

        Args:
            pair: Trading pair
            min_profit_bps: Minimum profit in basis points (default: MIN_ARB_BPS)

        Returns:
            List of arbitrage opportunities
        """
        if min_profit_bps is None:
            min_profit_bps = self.MIN_ARB_BPS

        pair_snapshots = {
            dex: snapshot
            for (d, p), snapshot in self.latest_snapshots.items()
            if p == pair and d == dex
        }

        if len(pair_snapshots) < 2:
            return []

        opportunities = []

        # Compare all DEX pairs
        dex_list = list(pair_snapshots.keys())
        for i, buy_dex in enumerate(dex_list):
            for sell_dex in dex_list[i+1:]:
                buy_snap = pair_snapshots[buy_dex]
                sell_snap = pair_snapshots[sell_dex]

                # Check both directions

                # Direction 1: Buy on buy_dex, sell on sell_dex
                buy_price = buy_snap.ask_price
                sell_price = sell_snap.bid_price

                if sell_price > buy_price:
                    gross_profit_pct = ((sell_price - buy_price) / buy_price) * 100
                    spread_bps = gross_profit_pct * 100

                    # Estimate net profit after gas
                    gas_cost_pct = (self.GAS_COSTS["arb"] / (buy_price * 1.0)) * 100  # Assume 1 unit trade
                    net_profit_pct = gross_profit_pct - gas_cost_pct

                    if spread_bps >= min_profit_bps:
                        # Determine max size
                        max_size = min(buy_snap.ask_liquidity, sell_snap.bid_liquidity)

                        opportunities.append(ArbitrageOpportunity(
                            pair=pair,
                            buy_dex=buy_dex,
                            sell_dex=sell_dex,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            spread_bps=spread_bps,
                            gross_profit_pct=gross_profit_pct,
                            est_net_profit_pct=net_profit_pct,
                            size_available=max_size,
                            confidence=0.8,  # High confidence for on-chain arb
                            timestamp=int(time.time())
                        ))

                # Direction 2: Buy on sell_dex, sell on buy_dex
                buy_price = sell_snap.ask_price
                sell_price = buy_snap.bid_price

                if sell_price > buy_price:
                    gross_profit_pct = ((sell_price - buy_price) / buy_price) * 100
                    spread_bps = gross_profit_pct * 100
                    gas_cost_pct = (self.GAS_COSTS["arb"] / (buy_price * 1.0)) * 100
                    net_profit_pct = gross_profit_pct - gas_cost_pct

                    if spread_bps >= min_profit_bps:
                        max_size = min(sell_snap.ask_liquidity, buy_snap.bid_liquidity)

                        opportunities.append(ArbitrageOpportunity(
                            pair=pair,
                            buy_dex=sell_dex,
                            sell_dex=buy_dex,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            spread_bps=spread_bps,
                            gross_profit_pct=gross_profit_pct,
                            est_net_profit_pct=net_profit_pct,
                            size_available=max_size,
                            confidence=0.8,
                            timestamp=int(time.time())
                        ))

        # Sort by net profit
        opportunities.sort(key=lambda x: x.est_net_profit_pct, reverse=True)

        return opportunities

    def get_unified_liquidity(self, pair: str) -> Dict:
        """
        Get unified liquidity view across all DEXes

        Aggregates liquidity holes, total depth, etc.

        Returns:
            Dictionary with unified liquidity metrics
        """
        pair_snapshots = {
            dex: snapshot
            for (d, p), snapshot in self.latest_snapshots.items()
            if p == pair and d == dex
        }

        if not pair_snapshots:
            return {"error": "no_data"}

        # Aggregate liquidity
        total_bid_liq = sum(s.bid_liquidity for s in pair_snapshots.values())
        total_ask_liq = sum(s.ask_liquidity for s in pair_snapshots.values())
        total_liq = total_bid_liq + total_ask_liq

        # Average mid price (volume-weighted)
        weighted_prices = [s.mid_price * (s.bid_liquidity + s.ask_liquidity) for s in pair_snapshots.values()]
        total_weight = sum(s.bid_liquidity + s.ask_liquidity for s in pair_snapshots.values())
        avg_mid_price = sum(weighted_prices) / total_weight if total_weight > 0 else 0

        # Calculate liquidity concentration
        dex_liquidity = {
            dex: (s.bid_liquidity + s.ask_liquidity)
            for dex, s in pair_snapshots.items()
        }

        # Find most liquid DEX
        most_liquid_dex = max(dex_liquidity, key=dex_liquidity.get)

        return {
            "pair": pair,
            "total_bid_liquidity": total_bid_liq,
            "total_ask_liquidity": total_ask_liq,
            "total_liquidity": total_liq,
            "avg_mid_price": avg_mid_price,
            "num_dexes": len(pair_snapshots),
            "liquidity_by_dex": dex_liquidity,
            "most_liquid_dex": most_liquid_dex,
            "timestamp": int(time.time())
        }

    def get_best_execution_route(
        self,
        pair: str,
        side: str,  # "buy" or "sell"
        size: float
    ) -> Dict:
        """
        Determine best execution route for a trade

        Args:
            pair: Trading pair
            side: "buy" or "sell"
            size: Trade size

        Returns:
            Execution route recommendation
        """
        pair_snapshots = {
            dex: snapshot
            for (d, p), snapshot in self.latest_snapshots.items()
            if p == pair and d == dex
        }

        if not pair_snapshots:
            return {"error": "no_data"}

        # Find best price for given side
        if side == "buy":
            # We want lowest ask
            prices = {dex: s.ask_price for dex, s in pair_snapshots.items()}
            liquidity = {dex: s.ask_liquidity for dex, s in pair_snapshots.items()}
        else:
            # We want highest bid
            prices = {dex: s.bid_price for dex, s in pair_snapshots.items()}
            liquidity = {dex: s.bid_liquidity for dex, s in pair_snapshots.items()}

        # Sort by price (best first)
        if side == "buy":
            sorted_dexes = sorted(prices.keys(), key=lambda d: prices[d])
        else:
            sorted_dexes = sorted(prices.keys(), key=lambda d: prices[d], reverse=True)

        # Build execution route (fill from best prices first)
        route = []
        remaining_size = size

        for dex in sorted_dexes:
            if remaining_size <= 0:
                break

            available = liquidity[dex]
            fill_size = min(remaining_size, available)

            if fill_size > 0:
                route.append({
                    "dex": dex,
                    "price": prices[dex],
                    "size": fill_size,
                    "fraction": fill_size / size
                })

                remaining_size -= fill_size

        # Calculate weighted average price
        total_cost = sum(r["price"] * r["size"] for r in route)
        total_filled = sum(r["size"] for r in route)
        avg_price = total_cost / total_filled if total_filled > 0 else 0

        return {
            "pair": pair,
            "side": side,
            "requested_size": size,
            "filled_size": total_filled,
            "fill_rate": total_filled / size if size > 0 else 0,
            "avg_price": avg_price,
            "route": route,
            "num_venues": len(route),
            "timestamp": int(time.time())
        }


# Example usage
if __name__ == "__main__":
    # Initialize analyzer
    analyzer = CrossDEXAnalyzer(dexes=["lynex", "etherex", "nile", "syncswap", "kyberswap"])

    # Simulate snapshots from different DEXes
    snapshots = [
        DEXSnapshot("lynex", "WETH-USDC", 1850.0, 1849.5, 1850.5, 100000, 95000, int(time.time())),
        DEXSnapshot("etherex", "WETH-USDC", 1851.0, 1850.3, 1851.7, 80000, 85000, int(time.time())),
        DEXSnapshot("nile", "WETH-USDC", 1849.5, 1849.0, 1850.0, 60000, 65000, int(time.time())),
    ]

    for snap in snapshots:
        analyzer.update_snapshot(snap)

    # Get spread matrix
    spread_matrix = analyzer.get_spread_matrix("WETH-USDC")
    print("Spread Matrix:")
    print(f"  Best Bid: ${spread_matrix['best_bid']} on {spread_matrix['best_bid_dex']}")
    print(f"  Best Ask: ${spread_matrix['best_ask']} on {spread_matrix['best_ask_dex']}")
    print(f"  NBBO Spread: {spread_matrix['nbbo_spread_bps']:.1f} bps")

    # Detect arbitrage
    arbs = analyzer.detect_arbitrage("WETH-USDC", min_profit_bps=10)
    print(f"\nArbitrage Opportunities: {len(arbs)}")
    for arb in arbs:
        print(f"  Buy {arb.pair} on {arb.buy_dex} @ ${arb.buy_price:.2f}")
        print(f"  Sell on {arb.sell_dex} @ ${arb.sell_price:.2f}")
        print(f"  Gross: {arb.gross_profit_pct:.2f}% | Net: {arb.est_net_profit_pct:.2f}%")

    # Unified liquidity
    unified = analyzer.get_unified_liquidity("WETH-USDC")
    print(f"\nUnified Liquidity:")
    print(f"  Total: ${unified['total_liquidity']:,.0f}")
    print(f"  Most Liquid DEX: {unified['most_liquid_dex']}")

    # Best execution
    route = analyzer.get_best_execution_route("WETH-USDC", "buy", 10.0)
    print(f"\nBest Execution for 10 WETH:")
    print(f"  Avg Price: ${route['avg_price']:.2f}")
    print(f"  Venues: {route['num_venues']}")
    for r in route["route"]:
        print(f"    {r['dex']}: {r['size']:.2f} WETH @ ${r['price']:.2f}")
