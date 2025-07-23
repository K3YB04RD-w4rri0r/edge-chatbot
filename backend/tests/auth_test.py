import httpx
import json
import sys

BASE_URL = "http://localhost:8000"

def test_auth_flow():
    """Test the complete authentication flow with proper error handling."""
    
    # Test user data
    test_user = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "strongpassword123",
        "full_name": "Test User"
    }
    
    print("Starting authentication flow test...\n")
    
    # 1. Test server health
    print("1. Testing server health...")
    try:
        response = httpx.get(f"{BASE_URL}/health")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
        else:
            print(f"   Response: {response.text}")
    except httpx.ConnectError:
        print("   ERROR: Cannot connect to server. Is it running?")
        print("   Run: python3 main.py")
        sys.exit(1)
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
    
    # 2. Register a new user
    print("\n2. Registering new user...")
    try:
        response = httpx.post(
            f"{BASE_URL}/auth/register",  # Note: using API prefix
            json=test_user
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"   User created: {user_data}")
        elif response.status_code == 400:
            print(f"   User might already exist: {response.json()}")
        else:
            print(f"   Error: {response.text}")
            # Try to parse JSON error if possible
            try:
                error_detail = response.json()
                print(f"   Error details: {error_detail}")
            except:
                pass
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
        return
    
    # 3. Login
    print("\n3. Testing login...")
    try:
        # For OAuth2PasswordRequestForm, we need to send form data, not JSON
        response = httpx.post(
            f"{BASE_URL}/auth/login",  # Note: using API prefix
            data={
                "username": test_user["username"],
                "password": test_user["password"]
            }
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            tokens = response.json()
            print(f"   Access token: {tokens['access_token'][:50]}...")
            print(f"   Refresh token: {tokens['refresh_token'][:50]}...")
            print(f"   Token type: {tokens['token_type']}")
        else:
            print(f"   Error: {response.text}")
            try:
                error_detail = response.json()
                print(f"   Error details: {error_detail}")
            except:
                pass
            return
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
        return
    
    # 4. Test protected endpoint
    print("\n4. Testing protected endpoint (get current user)...")
    try:
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        response = httpx.get(
            f"{BASE_URL}/auth/me",  # Note: using API prefix
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            user_info = response.json()
            print(f"   Current user: {user_info}")
        else:
            print(f"   Error: {response.text}")
            try:
                error_detail = response.json()
                print(f"   Error details: {error_detail}")
            except:
                pass
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
    
    # 5. Test refresh token
    print("\n5. Testing token refresh...")
    try:
        response = httpx.post(
            f"{BASE_URL}/auth/refresh",  # Note: using API prefix
            json={"refresh_token": tokens["refresh_token"]}
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            new_tokens = response.json()
            print(f"   New access token: {new_tokens['access_token'][:50]}...")
            print(f"   New refresh token: {new_tokens['refresh_token'][:50]}...")
        else:
            print(f"   Error: {response.text}")
            try:
                error_detail = response.json()
                print(f"   Error details: {error_detail}")
            except:
                pass
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
    
    # 6. Test logout
    print("\n6. Testing logout...")
    try:
        response = httpx.post(
            f"{BASE_URL}/auth/logout",  # Note: using API prefix
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
    
    print("\n✅ Authentication flow test completed!")


def test_invalid_credentials():
    """Test authentication with invalid credentials."""
    print("\n\nTesting invalid credentials...")
    
    # Test with wrong password
    print("\n1. Testing login with wrong password...")
    try:
        response = httpx.post(
            f"{BASE_URL}/auth/login",
            data={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json() if response.status_code != 200 else 'Unexpected success!'}")
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
    
    # Test with non-existent user
    print("\n2. Testing login with non-existent user...")
    try:
        response = httpx.post(
            f"{BASE_URL}/auth/login",
            data={
                "username": "nonexistentuser",
                "password": "somepassword"
            }
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json() if response.status_code != 200 else 'Unexpected success!'}")
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
    
    # Test with invalid token
    print("\n3. Testing protected endpoint with invalid token...")
    try:
        headers = {"Authorization": "Bearer invalid-token-here"}
        response = httpx.get(
            f"{BASE_URL}/auth/me",
            headers=headers
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json() if response.status_code != 200 else 'Unexpected success!'}")
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    # Run the tests
    test_auth_flow()
    test_invalid_credentials()
    
    print("\n\n🎉 All tests completed!")
    print("\nNote: If you see connection errors, make sure your FastAPI server is running:")
    print("  python3 main.py")