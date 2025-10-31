"""Test admin endpoints."""

import asyncio
import sys

import httpx


async def test_admin():
    """Test admin endpoints."""
    base_url = "http://localhost:8000/api/v1"
    
    async with httpx.AsyncClient() as client:
        # 1. Register test admin user
        print("1. Registering admin user...")
        register_data = {
            "email": "admin@test.com",
            "username": "admin",
            "password": "admin12345",
            "role": "user"
        }
        try:
            response = await client.post(f"{base_url}/auth/register", json=register_data)
            if response.status_code == 201:
                user_data = response.json()
                print(f"   OK: User created (ID: {user_data['id']})")
            else:
                print(f"   User might already exist: {response.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # 2. Login
        print("\n2. Logging in...")
        login_data = {
            "email": "admin@test.com",
            "password": "admin12345"
        }
        response = await client.post(f"{base_url}/auth/login", json=login_data)
        if response.status_code == 200:
            token_data = response.json()
            token = token_data["access_token"]
            print(f"   OK: Got token")
        else:
            print(f"   ERROR: Login failed: {response.status_code}")
            print(f"   {response.text}")
            return
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Test admin stats (should fail - not admin yet)
        print("\n3. Testing admin/stats (should fail - not admin)...")
        response = await client.get(f"{base_url}/admin/stats", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 403:
            print("   OK: Access denied (need admin role)")
        else:
            print(f"   Response: {response.text}")
        
        # 4. Test get current user
        print("\n4. Getting current user info...")
        response = await client.get(f"{base_url}/auth/me", headers=headers)
        if response.status_code == 200:
            user = response.json()
            print(f"   OK: User {user['username']} (ID: {user['id']}, Role: {user['role']})")
            user_id = user['id']
        else:
            print(f"   ERROR: {response.status_code}")
            return
        
        # 5. Check brands
        print("\n5. Checking brands...")
        response = await client.get(f"{base_url}/brands/")
        if response.status_code == 200:
            brands = response.json()
            print(f"   OK: Found {brands['total']} brands")
            if brands['total'] > 0:
                print(f"   First brand: {brands['items'][0]['name']} (verified: {brands['items'][0]['verified']})")
        
        # 6. Test pending presets (should fail - not admin)
        print("\n6. Testing admin/presets/pending (should fail)...")
        response = await client.get(f"{base_url}/admin/presets/pending", headers=headers)
        print(f"   Status: {response.status_code}")
        if response.status_code == 403:
            print("   OK: Access denied (need admin role)")
        
        print("\n" + "="*50)
        print("Tests completed!")
        print("\nTo promote user to admin, call:")
        print(f"  POST {base_url}/admin/users/{user_id}/promote-admin")
        print("  (needs existing admin account)")


if __name__ == "__main__":
    asyncio.run(test_admin())

