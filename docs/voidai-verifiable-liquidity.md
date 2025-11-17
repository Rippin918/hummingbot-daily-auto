# VoidAI Verifiable Liquidity - Reference

**Source:** https://voidai.com/blogs/economics-of-voidai
**Date Archived:** 2025-11-17
**Status:** Reference only - not currently integrated

## Overview

VoidAI uses Bittensor's Subnet 106 (SN106) to cryptographically verify liquidity provider positions, preventing common DeFi exploits like flash loan attacks and fake deposits.

## Key Innovation: Verifiable-LP Subnet (SN106)

### Traditional LP Problem
- Protocols trust user-reported deposits
- Vulnerable to: flash loans, wash trading, temporary positions for rewards
- No verification of genuine, persistent liquidity

### VoidAI's Solution
- **Validators** run nodes that verify on-chain LP positions
- Check position size, duration, and authenticity
- Bittensor consensus mechanism ensures validator honesty
- Only verified positions receive rewards

### Token Distribution (SN106)
- 41% → Liquidity Providers (verified)
- 41% → Validators (for verification work)
- 18% → Subnet owner

## Infrastructure

### Cross-Chain Bridges
1. **Solana Bridge (v2):** Lock TAO/Alpha on Bittensor → receive wrapped tokens on Solana
2. **CCIP Bridge (v3):** Chainlink oracle network for multi-chain atomic swaps
3. All bridge fees → VoidAI treasury

### Treasury Model
50% → Deepen liquidity pools across chains
50% → Build SN106 token reserves

## Revenue Streams
- Trading fees: 0.32% on swaps
- Bridge operation fees
- Staking yields
- Validator commissions
- Arbitrage profits
- Subnet incubation proceeds
- API access fees

## Potential Use Cases (Future)

### If Expanding Beyond Linea:
1. **Multi-chain Arbitrage**
   - TAO price differences between Bittensor/Solana/CEXs
   - Requires: Solana support, Bittensor RPC, CEX connectors

2. **Verified Liquidity Mining**
   - Participate in SN106 LP rewards (41% APY)
   - Benefit: No rug pull risk, validator-verified yields
   - Requires: Bittensor network support in Hummingbot

3. **Bridge Arbitrage**
   - Exploit price inefficiencies during cross-chain transfers
   - Requires: Fast execution, multi-chain wallet management

## Integration Requirements

### Technical Prerequisites:
- [ ] Bittensor RPC endpoint access
- [ ] Solana chain support (if using wrapped tokens)
- [ ] TAO/Alpha token pair on supported exchange
- [ ] Validator node setup (for full participation)
- [ ] Multi-chain wallet orchestration

### Current Blockers:
- Hummingbot doesn't natively support Bittensor network
- Current setup focused on Linea L2 only
- No TAO pairs in existing Renzo/R7 strategy

## Notes

**Pros:**
- Cryptographically verifiable LP positions
- Aligned incentives (validators stake reputation)
- Protection against common DeFi exploits
- Transparent, provable yields

**Cons:**
- Requires new chain integration
- More complex setup than traditional LPs
- Validator consensus may add latency

**Recommendation:** Shelve for now. Revisit if:
1. Expanding to Solana/Bittensor ecosystem
2. Seeking verified liquidity mining opportunities
3. Building cross-chain arbitrage system

---

**Last Updated:** 2025-11-17
**Next Review:** When considering chain expansion or verifiable liquidity products
