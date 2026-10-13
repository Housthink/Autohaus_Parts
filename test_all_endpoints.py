#!/usr/bin/env python3
"""
FINDINPART API - COMPLETE ENDPOINTS TEST
This script tests all major API endpoints to verify connectivity and functionality
"""

import json
import time
import base64
import hmac
import hashlib
import requests

def generate_jwt_token():
    """Generate JWT token for API authentication"""
    jwt_secret = '222b6c16-b54a-4ad6-a2c7-e43ba7c23060'
    jwt_issuer = 'autohaus-build'
    
    now = int(time.time())
    expiry = now + 1800
    
    header = {"typ": "JWT", "alg": "HS256"}
    payload = {
        "iss": jwt_issuer,
        "iat": now,
        "exp": expiry,
        "jti": "jwt_nonce"
    }
    
    header_encoded = base64.urlsafe_b64encode(
        json.dumps(header, separators=(',', ':')).encode()
    ).decode().rstrip('=')
    
    payload_encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(',', ':')).encode()
    ).decode().rstrip('=')
    
    message = f"{header_encoded}.{payload_encoded}"
    signature = hmac.new(
        jwt_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    
    signature_encoded = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    return f"{header_encoded}.{payload_encoded}.{signature_encoded}"

def test_endpoint(name, url, params=None):
    """Test a single endpoint"""
    print(f"\n🔍 Testing: {name}")
    print(f"   URL: {url}")
    if params:
        print(f"   Params: {params}")
    
    token = generate_jwt_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'AutoHaus-FindinPart-Test/1.0'
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if 'products' in data:
                    products = data['products']
                    print(f"   ✅ Success: {len(products)} products found")
                    if products:
                        first_product = products[0]
                        print(f"   📦 Sample: {first_product.get('manufacturer', 'N/A')} {first_product.get('part_number', 'N/A')}")
                else:
                    print(f"   ✅ Success: Response received")
                    print(f"   📊 Data keys: {list(data.keys())}")
            except json.JSONDecodeError:
                print(f"   ✅ Success: Non-JSON response")
        else:
            print(f"   ❌ Error: {response.status_code}")
            print(f"   📝 Response: {response.text[:100]}...")
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")

def main():
    """Test all endpoints from Postman collection"""
    print("=" * 80)
    print("FINDINPART API - ALL ENDPOINTS TEST")
    print("=" * 80)
    print(f"Base URL: https://www-build.finditparts.com")
    print(f"Test Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    base_url = "https://www-build.finditparts.com"
    
    # Test all endpoints from Postman collection
    endpoints = [
        {
            "name": "Basic Products List",
            "url": f"{base_url}/api/v1/products",
            "params": None
        },
        {
            "name": "Search with Query (brake)",
            "url": f"{base_url}/api/v1/products",
            "params": {"q": "brake", "strict": "true"}
        },
        {
            "name": "Search by Part Number (5280X)",
            "url": f"{base_url}/api/v1/products",
            "params": {"strict": "true", "pn": "5280X"}
        },
        {
            "name": "V3 Search Engine (DR10511414)",
            "url": f"{base_url}/api/v1/products",
            "params": {"use_v3_search": "true", "part_number": "DR10511414", "eoos": "true", "aggs": "true"}
        },
        {
            "name": "Search with Aggregations (haldex KN20001)",
            "url": f"{base_url}/api/v1/products",
            "params": {"q": "haldex KN20001", "aggs": "true", "order": "price_to_high"}
        },
        {
            "name": "Product Lookup (WL10179)",
            "url": f"{base_url}/api/v1/products/lookup",
            "params": {"part_number": "WL10179", "include_pies_data": "true"}
        },
        {
            "name": "Multiple Products (1062657)",
            "url": f"{base_url}/api/v1/products/1062657/multi",
            "params": None
        },
        {
            "name": "Product with PIES Data (1062657)",
            "url": f"{base_url}/api/v1/products/1062657",
            "params": {"include_pies_data": "true"}
        }
    ]
    
    results = []
    for endpoint in endpoints:
        test_endpoint(endpoint["name"], endpoint["url"], endpoint["params"])
        results.append(endpoint["name"])
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total endpoints tested: {len(endpoints)}")
    print("All endpoints from Postman collection have been tested.")
    print("Check the results above to see which endpoints are working.")
    print("=" * 80)

if __name__ == "__main__":
    main()
