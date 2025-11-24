#!/usr/bin/env python3
"""
Linea DEX Data Collector
Collects trading pair data from Linea DEXs for volatility and arbitrage analysis
"""

import os
import json
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
from pathlib import Path

# Linea DEX Subgraph URLs
SUBGRAPH_URLS = {
    "lynex": "https://api.goldsky.com/api/public/project_clv14x49kz9kz01saerx7bxpg/subgraphs/lynex/1.0.0/gn",
    "syncswap": "https://api.studio.thegraph.com/query/50473/syncswap-linea/version/latest",
    "nile": "https://graph.nile.build/subgraphs/name/nile/nile-v1",
    "velocore": "https://api.thegraph.com/subgraphs/name/velocore/velocore-linea"
}

# Common token addresses on Linea
TOKEN_ADDRESSES = {
    "WETH": "0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f",
    "USDC": "0x176211869cA2b568f2A7D4EE941E073a821EE1ff",
    "USDT": "0xA219439258ca9da29E9Cc4cE5596924745e12B93",
    "LINEA": "0x7d2bA228C5a28e1CA11a0e40f595c6FB0Dd9a9D4",  # Native LINEA token
    # Add more as we verify them
}

class LineaDataCollector:
    def __init__(self, output_dir: str = "data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def query_graphql(self, url: str, query: str, variables: Optional[Dict] = None) -> Optional[Dict]:
        """Execute GraphQL query against a subgraph"""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {"query": query}
            if variables:
                payload["variables"] = variables

            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error querying {url}: {e}")
            return None

    def get_pool_data_lynex(self, token0: str, token1: str, duration_hours: int = 12) -> List[Dict]:
        """Get pool data from Lynex for a specific pair"""
        timestamp_from = int((datetime.now() - timedelta(hours=duration_hours)).timestamp())

        query = """
        query GetPools($token0: String!, $token1: String!, $timestampFrom: Int!) {
          pools(
            where: {
              or: [
                {token0: $token0, token1: $token1}
                {token0: $token1, token1: $token0}
              ]
            }
            orderBy: volumeUSD
            orderDirection: desc
          ) {
            id
            token0 {
              id
              symbol
              decimals
            }
            token1 {
              id
              symbol
              decimals
            }
            reserve0
            reserve1
            reserveUSD
            volumeUSD
            token0Price
            token1Price
            poolHourData(
              where: {periodStartUnix_gte: $timestampFrom}
              orderBy: periodStartUnix
              orderDirection: asc
            ) {
              periodStartUnix
              reserve0
              reserve1
              reserveUSD
              volumeUSD
              token0Price
              token1Price
              high
              low
              open
              close
            }
          }
        }
        """

        variables = {
            "token0": token0.lower(),
            "token1": token1.lower(),
            "timestampFrom": timestamp_from
        }

        result = self.query_graphql(SUBGRAPH_URLS["lynex"], query, variables)
        if result and "data" in result and "pools" in result["data"]:
            return result["data"]["pools"]
        return []

    def get_top_pairs(self, dex: str = "lynex", limit: int = 20) -> List[Dict]:
        """Get top trading pairs by volume"""
        query = """
        query GetTopPairs($limit: Int!) {
          pairs: pools(
            first: $limit
            orderBy: volumeUSD
            orderDirection: desc
          ) {
            id
            token0 {
              id
              symbol
              name
            }
            token1 {
              id
              symbol
              name
            }
            reserve0
            reserve1
            reserveUSD
            volumeUSD
            token0Price
            token1Price
          }
        }
        """

        variables = {"limit": limit}
        result = self.query_graphql(SUBGRAPH_URLS[dex], query, variables)

        if result and "data" in result:
            return result["data"].get("pairs", [])
        return []

    def calculate_volatility(self, price_data: List[Dict]) -> float:
        """Calculate price volatility from hourly data"""
        if len(price_data) < 2:
            return 0.0

        prices = [float(d.get("close", 0) or d.get("token0Price", 0)) for d in price_data]
        prices = [p for p in prices if p > 0]  # Filter out zero prices

        if len(prices) < 2:
            return 0.0

        # Calculate percentage changes
        changes = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                change = abs((prices[i] - prices[i-1]) / prices[i-1])
                changes.append(change)

        if not changes:
            return 0.0

        # Return average volatility as percentage
        return sum(changes) / len(changes) * 100

    def find_arbitrage_opportunities(self, pair_data: Dict, threshold: float = 0.5) -> List[Dict]:
        """Find potential arbitrage opportunities based on price differences"""
        opportunities = []

        # This is a simplified example - in reality you'd compare prices across DEXs
        hour_data = pair_data.get("poolHourData", [])
        if len(hour_data) < 2:
            return opportunities

        for i in range(len(hour_data) - 1):
            current = hour_data[i]
            next_data = hour_data[i + 1]

            current_price = float(current.get("close", 0) or current.get("token0Price", 0))
            next_price = float(next_data.get("close", 0) or next_data.get("token0Price", 0))

            if current_price > 0 and next_price > 0:
                price_diff = abs(next_price - current_price) / current_price * 100

                if price_diff > threshold:
                    opportunities.append({
                        "timestamp": current.get("periodStartUnix"),
                        "current_price": current_price,
                        "next_price": next_price,
                        "price_diff_percent": price_diff,
                        "volume_usd": current.get("volumeUSD", 0)
                    })

        return opportunities

    def collect_pair_data(self, pairs: List[Dict], duration_hours: int = 12) -> Dict:
        """Collect detailed data for specified pairs"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "duration_hours": duration_hours,
            "pairs": []
        }

        for pair_config in pairs:
            symbol = pair_config.get("symbol", f"{pair_config['token0']}/{pair_config['token1']}")
            print(f"Collecting data for {symbol}...")

            token0 = pair_config["token0"]
            token1 = pair_config["token1"]

            # Get data from Lynex (primary source)
            pools = self.get_pool_data_lynex(token0, token1, duration_hours)

            for pool in pools:
                hour_data = pool.get("poolHourData", [])
                volatility = self.calculate_volatility(hour_data)
                arb_opportunities = self.find_arbitrage_opportunities(pool)

                pair_result = {
                    "symbol": symbol,
                    "pool_address": pool["id"],
                    "dex": "lynex",
                    "token0": {
                        "address": pool["token0"]["id"],
                        "symbol": pool["token0"]["symbol"],
                        "decimals": pool["token0"]["decimals"]
                    },
                    "token1": {
                        "address": pool["token1"]["id"],
                        "symbol": pool["token1"]["symbol"],
                        "decimals": pool["token1"]["decimals"]
                    },
                    "current_price": float(pool.get("token0Price", 0)),
                    "reserve0": float(pool.get("reserve0", 0)),
                    "reserve1": float(pool.get("reserve1", 0)),
                    "reserveUSD": float(pool.get("reserveUSD", 0)),
                    "volumeUSD": float(pool.get("volumeUSD", 0)),
                    "volatility_percent": volatility,
                    "num_snapshots": len(hour_data),
                    "arbitrage_opportunities": len(arb_opportunities),
                    "hourly_data": hour_data[:24],  # Last 24 hours
                    "arb_details": arb_opportunities[:10]  # Top 10 opportunities
                }

                results["pairs"].append(pair_result)
                print(f"  ✓ {symbol}: Volatility={volatility:.2f}%, Arb Ops={len(arb_opportunities)}, Vol=${float(pool.get('volumeUSD', 0)):,.0f}")

        return results

    def save_results(self, results: Dict, filename: str = None):
        """Save results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"linea_data_{timestamp}.json"

        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Data saved to {filepath}")
        return filepath

    def generate_summary(self, results: Dict):
        """Generate human-readable summary"""
        print("\n" + "="*60)
        print("LINEA DEX DATA COLLECTION SUMMARY")
        print("="*60)
        print(f"Timestamp: {results['timestamp']}")
        print(f"Duration: {results['duration_hours']} hours")
        print(f"Pairs analyzed: {len(results['pairs'])}")
        print("\nTop opportunities:")

        # Sort by volatility
        sorted_pairs = sorted(results['pairs'], key=lambda x: x['volatility_percent'], reverse=True)

        for i, pair in enumerate(sorted_pairs[:5], 1):
            print(f"\n{i}. {pair['symbol']} ({pair['dex']})")
            print(f"   Volatility: {pair['volatility_percent']:.2f}%")
            print(f"   Volume (24h): ${pair['volumeUSD']:,.0f}")
            print(f"   Liquidity: ${pair['reserveUSD']:,.0f}")
            print(f"   Arbitrage Opportunities: {pair['arbitrage_opportunities']}")
            print(f"   Pool: {pair['pool_address']}")


def main():
    parser = argparse.ArgumentParser(description="Collect Linea DEX data for trading analysis")
    parser.add_argument("--pairs", type=str, help="Pairs to analyze (e.g., 'WETH-USDC,LINEA-WETH')")
    parser.add_argument("--duration", type=int, default=12, help="Duration in hours (default: 12)")
    parser.add_argument("--output-dir", type=str, default="data", help="Output directory")
    parser.add_argument("--discover", action="store_true", help="Discover top pairs by volume")

    args = parser.parse_args()

    collector = LineaDataCollector(output_dir=args.output_dir)

    if args.discover:
        print("Discovering top pairs on Lynex...")
        top_pairs = collector.get_top_pairs("lynex", limit=20)

        print(f"\nTop 20 pairs by volume:")
        for i, pair in enumerate(top_pairs, 1):
            print(f"{i}. {pair['token0']['symbol']}/{pair['token1']['symbol']}")
            print(f"   Volume: ${float(pair['volumeUSD']):,.0f}")
            print(f"   Liquidity: ${float(pair['reserveUSD']):,.0f}")
            print(f"   Pool: {pair['id']}\n")
        return

    # Parse pairs
    pairs_to_analyze = []
    if args.pairs:
        for pair_str in args.pairs.split(","):
            tokens = pair_str.strip().split("-")
            if len(tokens) == 2:
                token0_addr = TOKEN_ADDRESSES.get(tokens[0].upper())
                token1_addr = TOKEN_ADDRESSES.get(tokens[1].upper())

                if token0_addr and token1_addr:
                    pairs_to_analyze.append({
                        "symbol": f"{tokens[0]}/{tokens[1]}",
                        "token0": token0_addr,
                        "token1": token1_addr
                    })
                else:
                    print(f"Warning: Unknown token in pair {pair_str}")
    else:
        # Default: WETH-USDC for testing
        pairs_to_analyze = [{
            "symbol": "WETH/USDC",
            "token0": TOKEN_ADDRESSES["WETH"],
            "token1": TOKEN_ADDRESSES["USDC"]
        }]

    print(f"Collecting data for {len(pairs_to_analyze)} pairs over {args.duration} hours...")
    results = collector.collect_pair_data(pairs_to_analyze, duration_hours=args.duration)

    # Save and display results
    collector.save_results(results)
    collector.generate_summary(results)


if __name__ == "__main__":
    main()
