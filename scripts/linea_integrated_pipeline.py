#!/usr/bin/env python3
"""
Linea Integrated Micropulse Pipeline
End-to-end tick collection, Redis streaming, and Coulter analysis
Designed for integration with Sapient HRM automated strategy system
"""

import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from linea_tick_collector import LynexTickCollector
from linea_redis_streamer import LineaRedisStreamer
from linea_micropulse_analyzer import CoulterMicropulseAnalyzer


class LineaIntegratedPipeline:
    """
    Unified pipeline for tick-level orderbook analytics
    Combines collection, streaming, and Coulter analysis in one system
    """

    def __init__(
        self,
        config_path: str = None,
        data_dir: str = "data/ticks",
        analysis_dir: str = "data/analysis"
    ):
        self.data_dir = Path(data_dir)
        self.analysis_dir = Path(analysis_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent / "config" / "lynex_pools.json"

        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Components (initialized per pool)
        self.collectors = {}
        self.streamers = {}
        self.analyzers = {}

        # Results storage
        self.all_analyses = {}

        # Graceful shutdown
        self.running = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle graceful shutdown"""
        print("\n\nReceived shutdown signal...")
        self.running = False

    async def initialize_pool(self, pool_config: Dict, pair_symbol: str):
        """Initialize collector, streamer, and analyzer for a pool"""
        pool_address = pool_config["address"]

        # Validate pool address
        if pool_address == "0x..." or not pool_address.startswith("0x"):
            print(f"⚠ Skipping {pair_symbol}: Pool address not configured")
            return False

        print(f"Initializing {pair_symbol} ({pool_address})...")

        # Create analyzer
        analyzer_config = self.config.get("analyzer", {})
        analyzer = CoulterMicropulseAnalyzer(
            lookback_periods=analyzer_config.get("lookback_periods", 20),
            hole_threshold=analyzer_config.get("hole_threshold", 0.05),
            fibonacci_range_percent=analyzer_config.get("fibonacci_range_percent", 5.0)
        )
        self.analyzers[pair_symbol] = analyzer

        # Create Redis streamer if Redis is configured
        redis_config = self.config.get("redis")
        if redis_config:
            streamer = LineaRedisStreamer(
                pool_address=pool_address,
                pair_symbol=pair_symbol,
                redis_host=redis_config.get("host", "localhost"),
                redis_port=redis_config.get("port", 6379),
                redis_db=redis_config.get("db", 0),
                redis_password=redis_config.get("password"),
                tick_range=pool_config.get("tick_range", 200),
                rpc_url=self.config.get("rpc_url")
            )
            self.streamers[pair_symbol] = streamer
        else:
            # No Redis, use direct collector
            collector = LynexTickCollector(
                pool_address=pool_address,
                rpc_url=self.config.get("rpc_url"),
                tick_range=pool_config.get("tick_range", 200),
                data_dir=str(self.data_dir)
            )
            self.collectors[pair_symbol] = collector

        return True

    async def analyze_snapshot_callback(self, pair_symbol: str, snapshot: Dict):
        """Callback for real-time analysis of incoming snapshots"""
        analyzer = self.analyzers.get(pair_symbol)
        if not analyzer:
            return

        # Perform Coulter analysis
        analysis = analyzer.analyze_snapshot(snapshot)

        # Store result
        if pair_symbol not in self.all_analyses:
            self.all_analyses[pair_symbol] = []
        self.all_analyses[pair_symbol].append(analysis)

        # Log significant signals
        signal = analysis["trading_signal"]
        if signal["action"] != "hold" and signal["confidence"] > 0.5:
            print(f"\n{'='*70}")
            print(f"🚨 SIGNAL: {pair_symbol} - {signal['action'].upper()}")
            print(f"   Confidence: {signal['confidence']:.2%}")
            print(f"   Price: {analysis['current_price']:.6f}")
            print(f"   Imbalance: {analysis['signals']['pressure']['imbalance']:+.3f}")
            if "velocity" in analysis["signals"]:
                print(f"   Velocity: {analysis['signals']['velocity']['current_velocity']:+.4f}")
            print(f"   Reasons: {', '.join(signal['reasons'])}")
            print(f"{'='*70}\n")

    async def run_pool_pipeline(self, pair_symbol: str, duration_seconds: Optional[int] = None):
        """Run complete pipeline for a single pool"""
        if pair_symbol in self.streamers:
            # Use Redis streaming mode
            streamer = self.streamers[pair_symbol]

            # Create callback that does analysis
            async def streaming_callback(snapshot):
                await self.analyze_snapshot_callback(pair_symbol, snapshot)

            await streamer.stream(duration_seconds=duration_seconds)

        elif pair_symbol in self.collectors:
            # Use direct collection mode
            collector = self.collectors[pair_symbol]

            async def collection_callback(snapshot):
                await self.analyze_snapshot_callback(pair_symbol, snapshot)

            await collector.stream_ticks(
                duration_seconds=duration_seconds,
                callback=collection_callback
            )

            # Save snapshots
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            collector.save_snapshots(filename=f"{pair_symbol}_{timestamp}.json")

    async def run(self, pairs: List[str] = None, duration_seconds: Optional[int] = None):
        """
        Run integrated pipeline for specified pairs
        If pairs is None, runs all configured high-priority pairs
        """
        pools = self.config.get("pools", {})

        # Determine which pairs to run
        if pairs is None:
            # Run all high-priority pairs
            pairs = [
                symbol for symbol, pool in pools.items()
                if pool.get("priority") == "high" and pool["address"] != "0x..."
            ]

        if not pairs:
            print("No valid pairs configured. Please update pool addresses in config.")
            return

        print(f"\n{'='*70}")
        print(f"Linea Integrated Micropulse Pipeline")
        print(f"{'='*70}")
        print(f"Pairs: {', '.join(pairs)}")
        print(f"Duration: {duration_seconds}s" if duration_seconds else "Duration: Continuous")
        print(f"{'='*70}\n")

        # Initialize all pools
        for pair_symbol in pairs:
            pool_config = pools.get(pair_symbol)
            if not pool_config:
                print(f"⚠ Unknown pair: {pair_symbol}")
                continue

            success = await self.initialize_pool(pool_config, pair_symbol)
            if not success:
                pairs.remove(pair_symbol)

        if not pairs:
            print("No pools successfully initialized")
            return

        self.running = True

        # Run pipelines in parallel
        tasks = [
            self.run_pool_pipeline(pair, duration_seconds)
            for pair in pairs
        ]

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Pipeline error: {e}")
        finally:
            # Save all analyses
            await self.save_analyses()

    async def save_analyses(self):
        """Save all collected analyses to files"""
        if not self.all_analyses:
            print("No analyses to save")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for pair_symbol, analyses in self.all_analyses.items():
            if not analyses:
                continue

            filename = self.analysis_dir / f"{pair_symbol}_analysis_{timestamp}.json"

            data = {
                "pair": pair_symbol,
                "analysis_start": analyses[0]["timestamp"],
                "analysis_end": analyses[-1]["timestamp"],
                "snapshot_count": len(analyses),
                "analyses": analyses,
                "summary": self._generate_summary(analyses)
            }

            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)

            print(f"✓ Saved {len(analyses)} analyses to {filename}")

    def _generate_summary(self, analyses: List[Dict]) -> Dict:
        """Generate summary statistics from analyses"""
        if not analyses:
            return {}

        signals = [a["trading_signal"] for a in analyses]

        buy_signals = sum(1 for s in signals if s["action"] == "buy")
        sell_signals = sum(1 for s in signals if s["action"] == "sell")
        hold_signals = sum(1 for s in signals if s["action"] == "hold")

        avg_confidence = sum(s["confidence"] for s in signals) / len(signals)

        imbalances = [a["signals"]["pressure"]["imbalance"] for a in analyses]
        avg_imbalance = sum(imbalances) / len(imbalances)

        return {
            "total_snapshots": len(analyses),
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "hold_signals": hold_signals,
            "avg_confidence": avg_confidence,
            "avg_imbalance": avg_imbalance,
            "first_price": analyses[0]["current_price"],
            "last_price": analyses[-1]["current_price"],
            "price_change_percent": (
                (analyses[-1]["current_price"] - analyses[0]["current_price"]) /
                analyses[0]["current_price"] * 100
            )
        }


async def main():
    """CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run integrated Linea micropulse analysis pipeline"
    )
    parser.add_argument(
        "--pairs",
        type=str,
        help="Comma-separated list of pairs (e.g. 'WETH-USDC,REX-WETH')"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (default: config/lynex_pools.json)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Run duration in seconds (default: continuous)"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/ticks",
        help="Data directory for snapshots"
    )
    parser.add_argument(
        "--analysis-dir",
        type=str,
        default="data/analysis",
        help="Directory for analysis output"
    )

    args = parser.parse_args()

    # Parse pairs
    pairs = None
    if args.pairs:
        pairs = [p.strip() for p in args.pairs.split(",")]

    # Initialize pipeline
    pipeline = LineaIntegratedPipeline(
        config_path=args.config,
        data_dir=args.data_dir,
        analysis_dir=args.analysis_dir
    )

    # Run
    await pipeline.run(pairs=pairs, duration_seconds=args.duration)


if __name__ == "__main__":
    asyncio.run(main())
