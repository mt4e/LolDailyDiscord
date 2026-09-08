#!/usr/bin/env python3
"""Quick test script to verify the PUUID-based league endpoint works"""
import asyncio
import os
from dotenv import load_dotenv
from bot import RiotClient, Player

load_dotenv()

async def test():
    api_key = os.getenv("RIOT_API_KEY")
    platform = os.getenv("RIOT_PLATFORM")
    region = os.getenv("RIOT_REGION")
    
    # Test with first player
    test_player = Player("Cimo", "EUW25")
    
    async with RiotClient(api_key, platform, region) as riot:
        print(f"Testing with player: {test_player.name}#{test_player.tag}")
        
        # Get account info (PUUID)
        account = await riot.account(test_player)
        puuid = account["puuid"]
        print(f"✓ Got PUUID: {puuid[:20]}...")
        
        # Try the new endpoint
        snapshot = await riot.ranked_snapshot(puuid)
        if snapshot:
            print(f"✓ Ranked data retrieved!")
            print(f"  Rank: {snapshot.tier} {snapshot.rank}")
            print(f"  LP: {snapshot.lp}")
        else:
            print("✗ No ranked data (unranked or endpoint failed)")

if __name__ == "__main__":
    asyncio.run(test())
