#!/usr/bin/env python3
"""
Cart flow test against FinditParts API.
Creates a cart, adds a product, optionally updates qty, sets shipping/billing,
and fetches shipping methods. Credentials are hardcoded for quick checks.
"""

import json
import time
import base64
import hmac
import hashlib
import requests


# --- Auth helpers (hardcoded for testing) ---
JWT_SECRET = "222b6c16-b54a-4ad6-a2c7-e43ba7c23060"
JWT_ISSUER = "autohaus-build"
BASE_URL = "https://www-build.finditparts.com"


def generate_jwt_token():
    now = int(time.time())
    expiry = now + 1800
    header = {"typ": "JWT", "alg": "HS256"}
    payload = {"iss": JWT_ISSUER, "iat": now, "exp": expiry, "jti": "cart_flow_test"}
    header_enc = base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode()).decode().rstrip("=")
    payload_enc = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    msg = f"{header_enc}.{payload_enc}"
    sig = hmac.new(JWT_SECRET.encode(), msg.encode(), hashlib.sha256).digest()
    sig_enc = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{msg}.{sig_enc}"


def make_headers():
    return {
        "Authorization": f"Bearer {generate_jwt_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "AutoHaus-FindinPart-CartFlow/1.0",
    }


def pretty(obj):
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return str(obj)


def fetch_sample_variant(headers):
    """Return hardcoded product/variant known to be available."""
    return 15337111, 56953563, {"id": 15337111, "variant_id": 56953563}


def run_cart_flow():
    print("=== FinditParts Cart Flow Test ===")
    headers_auth = make_headers()
    headers_cart = dict(headers_auth)  # keep Authorization; also send cart_token param

    # 1. Create cart
    create_url = f"{BASE_URL}/api/v1/carts"
    r = requests.post(create_url, headers=headers_auth, json={}, timeout=15)
    print(f"[Create cart] status={r.status_code}")
    r.raise_for_status()
    cart_data = r.json()
    cart = cart_data.get("cart") or {}
    cart_id = cart.get("id")
    cart_token = cart.get("cart_token")
    if not cart_id:
        raise RuntimeError(f"Cart ID missing in response: {pretty(cart_data)}")
    print(f"  -> cart_id={cart_id} token={cart_token}")

    # 2. Resolve a sample product/variant
    product_id, variant_id, record = fetch_sample_variant(headers_auth)
    print(f"[Lookup product] product_id={product_id} variant_id={variant_id}")

    # 3. Add line item
    add_url = f"{BASE_URL}/api/v1/carts/{cart_id}/line_items"
    payload_add = {
        "finditparts_product_id": product_id,  # product_id from record (FinditParts product id)
        "variant_id": variant_id,
        "quantity": 1,
    }
    add_params = {"token": cart_token} if cart_token else None
    print(f"[Add line item] payload={payload_add} params={add_params}")
    r = requests.post(add_url, headers=headers_cart, params=add_params, json=payload_add, timeout=15)
    print(f"[Add line item] status={r.status_code}")
    if r.status_code != 200:
        try:
            with open("line_items_error.html", "w", encoding="utf-8") as f:
                f.write(r.text)
            print("   Saved error to line_items_error.html")
        except Exception:
            pass
        print(f"   Response (truncated): {r.text[:800]}")
        r.raise_for_status()
    cart = r.json().get("cart") or {}
    line_items = cart.get("line_items") or []
    line_item_id = line_items[0]["id"] if line_items else None
    print(f"  -> items={len(line_items)} line_item_id={line_item_id}")
    if not line_items:
        raise RuntimeError(f"Line item not added. Response: {pretty(r.json())}")

    # 4. (Optional) Update quantity if we have a line_item_id
    if line_item_id:
        update_url = f"{BASE_URL}/api/v1/carts/{cart_id}/line_items"
        payload_upd = {
            "line_items_attributes": [
                {"id": line_item_id, "quantity": 2},
            ]
        }
        r = requests.put(update_url, headers=headers_cart, params=add_params, json=payload_upd, timeout=15)
        print(f"[Update qty] status={r.status_code}")
        r.raise_for_status()
        cart = r.json().get("cart") or {}

    # 5. Set shipping address (dummy USA warehouse address)
    ship_url = f"{BASE_URL}/api/v1/carts/{cart_id}/shipping_address"
    shipping_body = {
        "first_name": "Warehouse",
        "last_name": "Pickup",
        "address1": "123 Warehouse St",
        "city": "Miami",
        "state": "FL",
        "zip": "33101",
        "country": "US",
        "phone": "5551234567",
    }
    r = requests.put(ship_url, headers=headers_cart, params=add_params, json=shipping_body, timeout=15)
    print(f"[Set shipping address] status={r.status_code}")
    r.raise_for_status()
    cart = r.json().get("cart") or {}

    # 6. Set billing address (reuse shipping)
    bill_url = f"{BASE_URL}/api/v1/carts/{cart_id}/billing_address"
    r = requests.put(bill_url, headers=headers_cart, params=add_params, json=shipping_body, timeout=15)
    print(f"[Set billing address] status={r.status_code}")
    r.raise_for_status()
    cart = r.json().get("cart") or {}

    # 7. Get shipping methods
    ship_methods_url = f"{BASE_URL}/api/v1/carts/{cart_id}/shipping_methods"
    r = requests.get(ship_methods_url, headers=headers_cart, params=add_params, timeout=15)
    print(f"[Get shipping methods] status={r.status_code}")
    r.raise_for_status()
    methods = r.json()
    print("[Shipping methods] sample:")
    print(pretty(methods)[:800])

    print("\n✅ Cart flow finished")
    print(f"Cart ID: {cart_id}")
    return True


if __name__ == "__main__":
    ok = run_cart_flow()
    exit(0 if ok else 1)
