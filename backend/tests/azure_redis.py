#!/usr/bin/env python3
"""
Azure Cache for Redis Connection Test Script
Tests your Redis connection and helps diagnose issues
"""
import os
import sys
import time
import redis
import ssl
from urllib.parse import urlparse
from dotenv import load_dotenv


load_dotenv()

def test_redis_connection():
    """Test connection to Azure Cache for Redis"""
    print("🔧 Azure Cache for Redis Connection Test")
    print("=" * 50)
    
    # Get Redis URL or components
    redis_url = os.getenv('REDIS_URL')
    redis_host = os.getenv('REDIS_HOST')
    redis_port = int(os.getenv('REDIS_PORT', 6380))
    redis_password = os.getenv('REDIS_PASSWORD')
    redis_ssl = os.getenv('REDIS_SSL', 'true').lower() == 'true'
    
    if not redis_url and not (redis_host and redis_password):
        print("❌ Error: Redis configuration not found in .env file")
        print("   Please set either REDIS_URL or REDIS_HOST + REDIS_PASSWORD")
        return False
    
    # Display configuration (hide password)
    if redis_url:
        parsed = urlparse(redis_url)
        print(f"📍 URL: {parsed.scheme}://{parsed.hostname}:{parsed.port}")
        print(f"🔐 SSL: {parsed.scheme == 'rediss'}")
    else:
        print(f"📍 Host: {redis_host}")
        print(f"📍 Port: {redis_port}")
        print(f"🔐 SSL: {redis_ssl}")
    
    print("\n🧪 Running connection tests...\n")
    
    # Test 1: Basic Connection
    print("1️⃣ Testing basic connection...")
    try:
        if redis_url:
            client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                ssl_cert_reqs='required' if 'rediss' in redis_url else None
            )
        else:
            client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
                ssl=redis_ssl or redis_port == 6380,
                ssl_cert_reqs='required' if redis_ssl else None,
                socket_connect_timeout=5,
                socket_timeout=5
            )
        
        # Ping test
        start_time = time.time()
        result = client.ping()
        latency = (time.time() - start_time) * 1000
        
        if result:
            print(f"✅ Connected successfully! (Latency: {latency:.2f}ms)")
        else:
            print("❌ Connected but ping failed")
            return False
            
    except redis.ConnectionError as e:
        print(f"❌ Connection failed: {e}")
        print("\n🔍 Troubleshooting tips:")
        print("   - Check if your IP is whitelisted in Azure Portal → Firewall")
        print("   - Verify the host name and port are correct")
        print("   - Ensure Redis instance is running")
        return False
    except redis.AuthenticationError as e:
        print(f"❌ Authentication failed: {e}")
        print("\n🔍 Troubleshooting tips:")
        print("   - Check if the password/access key is correct")
        print("   - Try regenerating the access key in Azure Portal")
        return False
    except ssl.SSLError as e:
        print(f"❌ SSL/TLS error: {e}")
        print("\n🔍 Troubleshooting tips:")
        print("   - Update your certificates: sudo apt update ca-certificates")
        print("   - For testing only, try REDIS_SSL_CERT_REQS=none")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
        return False
    
    # Test 2: Read/Write Operations
    print("\n2️⃣ Testing read/write operations...")
    try:
        test_key = "test:connection:key"
        test_value = f"Hello from Python at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Set
        client.set(test_key, test_value, ex=60)  # Expire in 60 seconds
        print(f"✅ SET operation successful")
        
        # Get
        retrieved = client.get(test_key)
        if retrieved == test_value:
            print(f"✅ GET operation successful: '{retrieved}'")
        else:
            print(f"⚠️  GET returned unexpected value: '{retrieved}'")
        
        # Delete
        client.delete(test_key)
        print(f"✅ DELETE operation successful")
        
    except Exception as e:
        print(f"❌ Read/Write test failed: {e}")
        return False
    
    # Test 3: Server Information
    print("\n3️⃣ Getting server information...")
    try:
        info = client.info()
        server_info = client.info("server")
        
        print(f"✅ Redis Version: {info.get('redis_version', 'Unknown')}")
        print(f"✅ Redis Mode: {server_info.get('redis_mode', 'standalone')}")
        print(f"✅ Connected Clients: {info.get('connected_clients', 0)}")
        print(f"✅ Used Memory: {info.get('used_memory_human', 'Unknown')}")
        print(f"✅ Max Memory: {info.get('maxmemory_human', 'Unlimited')}")
        
        # Check if it's Azure Cache
        if '.redis.cache.windows.net' in (redis_host or redis_url or ''):
            print(f"✅ Provider: Azure Cache for Redis")
        
    except Exception as e:
        print(f"⚠️  Could not get server info: {e}")
    
    # Test 4: Performance Test
    print("\n4️⃣ Running performance test...")
    try:
        iterations = 100
        start_time = time.time()
        
        for i in range(iterations):
            client.set(f"perf:test:{i}", f"value{i}", ex=10)
            client.get(f"perf:test:{i}")
        
        elapsed = time.time() - start_time
        ops_per_sec = (iterations * 2) / elapsed
        
        print(f"✅ Performed {iterations * 2} operations in {elapsed:.2f}s")
        print(f"✅ Performance: {ops_per_sec:.0f} ops/second")
        
        # Cleanup
        for i in range(iterations):
            client.delete(f"perf:test:{i}")
            
    except Exception as e:
        print(f"⚠️  Performance test failed: {e}")
    

    
    print("\n" + "=" * 50)
    print("✅ All tests completed successfully!")
    print("\n📝 Next steps:")
    print("   1. Your Redis connection is working properly")
    print("   2. You can now start your FastAPI application")
    print("   3. Monitor your Redis usage in Azure Portal")
    
    return True


def test_ssl_connection():
    """Test SSL/TLS connection specifically"""
    print("\n🔐 Testing SSL/TLS connection variants...")
    
    redis_url = os.getenv('REDIS_URL')
    if not redis_url or not redis_url.startswith('rediss://'):
        print("⚠️  Skipping SSL tests (not using rediss:// URL)")
        return
    
    ssl_options = [
        ("Required (default)", "required", None),
        ("Optional", "optional", None),
        ("None (dev only)", "none", None),
    ]
    
    for name, cert_reqs, ca_certs in ssl_options:
        print(f"\n   Testing with ssl_cert_reqs='{cert_reqs}'...")
        try:
            client = redis.from_url(
                redis_url,
                decode_responses=True,
                ssl_cert_reqs=cert_reqs,
                ssl_ca_certs=ca_certs,
                socket_connect_timeout=3
            )
            client.ping()
            print(f"   ✅ {name}: Connected successfully")
        except Exception as e:
            print(f"   ❌ {name}: {type(e).__name__}")


if __name__ == "__main__":
    print("\n🚀 Starting Azure Cache for Redis connection test...\n")
    
    # Check if .env exists
    if not os.path.exists('.env'):
        print("❌ Error: .env file not found")
        print("   Please create a .env file with your Redis configuration")
        sys.exit(1)
    
    # Run main test
    success = test_redis_connection()
    
    # Run SSL test if applicable
    if success:
        test_ssl_connection()
    
    sys.exit(0 if success else 1)