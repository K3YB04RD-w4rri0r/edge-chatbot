#!/usr/bin/env python3
"""
Test script to verify rate limiting is working correctly
"""
import asyncio
import httpx
from datetime import datetime

async def test_rate_limiting():
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        print("Testing rate limiting on /health endpoint (30/minute limit)...")
        
        # Try to make 35 requests rapidly
        success_count = 0
        rate_limited_count = 0
        
        for i in range(35):
            try:
                response = await client.get(f"{base_url}/health")
                if response.status_code == 200:
                    success_count += 1
                    print(f"Request {i+1}: ✓ Success")
                    
                    # Check rate limit headers
                    if i == 0:
                        print(f"  Rate Limit Headers:")
                        print(f"  - Limit: {response.headers.get('X-RateLimit-Limit', 'N/A')}")
                        print(f"  - Remaining: {response.headers.get('X-RateLimit-Remaining', 'N/A')}")
                        print(f"  - Reset: {response.headers.get('X-RateLimit-Reset', 'N/A')}")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print(f"Request {i+1}: ⚠️  Rate limited (429)")
                    retry_after = response.headers.get('Retry-After', 'N/A')
                    print(f"  - Retry After: {retry_after} seconds")
                else:
                    print(f"Request {i+1}: ❌ Error {response.status_code}")
            except Exception as e:
                print(f"Request {i+1}: ❌ Exception: {e}")
            
            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.1)
        
        print(f"\nSummary:")
        print(f"- Successful requests: {success_count}")
        print(f"- Rate limited requests: {rate_limited_count}")
        print(f"- Expected: ~30 successful, ~5 rate limited")
        
        # Test auth endpoint with stricter limit
        print("\n\nTesting /auth/microsoft endpoint (10/minute limit)...")
        
        success_count = 0
        rate_limited_count = 0
        
        for i in range(15):
            try:
                response = await client.get(f"{base_url}/auth/microsoft", follow_redirects=False)
                if response.status_code in [302, 307]:  # Redirect is success for auth
                    success_count += 1
                    print(f"Request {i+1}: ✓ Success (redirect)")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print(f"Request {i+1}: ⚠️  Rate limited (429)")
                else:
                    print(f"Request {i+1}: Status {response.status_code}")
            except Exception as e:
                print(f"Request {i+1}: ❌ Exception: {e}")
            
            await asyncio.sleep(0.5)
        
        print(f"\nSummary:")
        print(f"- Successful requests: {success_count}")
        print(f"- Rate limited requests: {rate_limited_count}")
        print(f"- Expected: ~10 successful, ~5 rate limited")

if __name__ == "__main__":
    print(f"Starting rate limit test at {datetime.now()}")
    asyncio.run(test_rate_limiting())
    print("\nTest complete!")