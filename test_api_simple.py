#!/usr/bin/env python3
"""
SIMPLE API TEST - FinditParts
Quick test to verify API connectivity and basic functionality
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

def test_api():
    """Test basic API functionality"""
    print("FINDINPART API - SIMPLE TEST")
    print("=" * 50)
    
    # Setup headers
    token = generate_jwt_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'AutoHaus-FindinPart-Test/1.0'
    }
    
    base_url = 'https://www-build.finditparts.com'
    
    tests = [
        {
            'name': 'Basic Products List',
            'url': f'{base_url}/api/v1/products',
            'params': {'limit': 5, 'include_pies_data': 'true',},
        },
        {
            'name': 'Search by Text',
            'url': f'{base_url}/api/v1/products',
            'params': {'q': 'brake', 'limit': 3}
        },
        {
            'name': 'Lookup by Part Number',
            'url': f'{base_url}/api/v1/products/lookup',
            'params': {'part_number': 'TKPRO-UPS2', 'include_pies_data': 'true'},
            'lookup_summary': True,
        },
        {
            'name': 'Product',
            'url': f'{base_url}/api/v1/products/9374297',
            'params': {'include_pies_data': 'true'},
        },
        {
            'name': 'Lookup JSON Raw (10R4029)',
            'url': f'{base_url}/api/v1/products/lookup',
            'params': {'part_number': '10R4029', 'include_pies_data': 'true'},
            'lookup_summary': True,
        },
    ]
    
    results = []
    
    def describe_price_source(record):
        """Return a human readable description of where price info was found."""
        sources = []
        cv = record.get('current_variant') or {}
        if 'price' in cv:
            sources.append(f"variant price={cv.get('price')}")
        if 'cost' in cv:
            sources.append(f"variant cost={cv.get('cost')}")
        if 'msrp' in record:
            sources.append(f"msrp={record.get('msrp')}")
        if 'price' in record and record.get('price') != cv.get('price'):
            sources.append(f"product price={record.get('price')}")
        if not sources:
            sources.append("no price fields present")
        return "; ".join(sources)
    
    def describe_product_id(record):
        """Determine the most relevant product id field to display."""
        return record.get('id') or record.get('product_id') or record.get('finditparts_id') or 'N/A'

    def extract_product_variant_qty(data):
        """Extract product_id, variant_id, quantity from lookup-like payloads."""
        candidates = []
        main_rec = data.get('main_part') or data.get('product') or {}
        if main_rec:
            candidates.append(main_rec)
        candidates.extend(data.get('part_number_matches') or [])

        def pick(rec):
            current_variant = rec.get('current_variant') or {}
            variants = rec.get('variants') or []
            variant_fallback = variants[0] if variants else {}
            product_id = rec.get('id') or rec.get('product_id') or current_variant.get('product_id') or variant_fallback.get('product_id')
            variant_id = (
                current_variant.get('id')
                or current_variant.get('variant_id')
                or variant_fallback.get('id')
                or variant_fallback.get('variant_id')
                or product_id
            )
            qty = current_variant.get('quantity') or variant_fallback.get('quantity') or rec.get('quantity')
            return product_id, variant_id, qty

        for rec in candidates:
            pid, vid, qty = pick(rec)
            if pid and vid:
                return pid, vid, qty
        return None, None, None
    
    def print_limited_entries(title, entries, formatter, limit=5):
        """Print up to limit entries using formatter."""
        if not entries:
            return
        print(title)
        for idx, entry in enumerate(entries[:limit], 1):
            formatter(idx, entry)
        remaining = len(entries) - limit
        if remaining > 0:
            print(f"     ... ({remaining} more entries not shown)")
    
    def print_product_details(record, label="Sample", prefix="   "):
        if not record:
            return
        manufacturer = record.get('manufacturer') or record.get('brand') or 'N/A'
        part_number = record.get('part_number', 'N/A')
        category = record.get('category') or record.get('breadcrumbs_ancestors', [{}])[-1].get('name') if record.get('breadcrumbs_ancestors') else None
        condition = record.get('condition')
        sellable = record.get('sellable')
        short_desc = record.get('short_description')
        long_desc = record.get('long_description')
        
        print(f"{prefix}📦 {label}: {manufacturer} {part_number}")
        print(f"{prefix}🆔 Product ID: {describe_product_id(record)}")
        print(f"{prefix}🔢 Part Number: {part_number}")
        print(f"{prefix}💲 Price info: {describe_price_source(record)}")
        if category or condition or sellable is not None:
            print(f"{prefix}📂 Category: {category or 'N/A'} | Condition: {condition or 'N/A'} | Sellable: {sellable}")
        if record.get('msrp'):
            print(f"{prefix}🏷️ MSRP: {record.get('msrp')}")
        if short_desc:
            print(f"{prefix}📝 Short Description: {short_desc}")
        if long_desc:
            trimmed = long_desc if len(long_desc) < 400 else long_desc[:397] + '...'
            print(f"{prefix}🧾 Long Description: {trimmed}")
        
        # Images
        images = record.get('product_images') or []
        if images:
            def _image_formatter(i, img_entry):
                print(f"{prefix}     Image {i}:")
                for size, info in img_entry.items():
                    if isinstance(info, dict):
                        jpeg = info.get('jpeg')
                        webp = info.get('webp')
                        if jpeg:
                            print(f"{prefix}       {size} jpeg: {jpeg}")
                        if webp:
                            print(f"{prefix}       {size} webp: {webp}")
                    else:
                        print(f"{prefix}       {size}: {info}")
            print_limited_entries(f"{prefix}🖼️ Images:", images, _image_formatter, limit=3)
        
        # Purchase notes
        notes = record.get('purchase_notes') or []
        if notes:
            def _note_formatter(i, note):
                note_type = note.get('type', f"Note {i}")
                message = note.get('html_message') or note.get('text') or ''
                print(f"{prefix}     {note_type}: {message}")
            print_limited_entries(f"{prefix}🧾 Purchase Notes:", notes, _note_formatter, limit=4)
        
        pies = record.get('pies_data') or {}
        descriptions = pies.get('descriptions') or []
        if descriptions:
            def _desc_formatter(i, desc):
                title = desc.get('title') or desc.get('description_code') or f"Item {i}"
                lang = desc.get('language_code', 'N/A')
                value = desc.get('value', '')
                print(f"{prefix}     [{lang}] {title}: {value}")
            print_limited_entries(f"{prefix}📄 PIES Descriptions:", descriptions, _desc_formatter, limit=6)
        
        attributes = pies.get('product_attributes') or []
        if attributes:
            def _attr_formatter(i, attr):
                print(f"{prefix}     {attr.get('name', f'Attr {i}')}: {attr.get('value', '')}")
            print_limited_entries(f"{prefix}🧪 Product Attributes:", attributes, _attr_formatter, limit=10)
        
        ext_info = pies.get('extended_product_informations') or []
        if ext_info:
            def _ext_formatter(i, info):
                label = info.get('description') or info.get('expi_code') or f"Info {i}"
                value = info.get('value', '')
                print(f"{prefix}     {label}: {value}")
            print_limited_entries(f"{prefix}📚 Additional Info:", ext_info, _ext_formatter, limit=8)
        
        interchanges = pies.get('part_interchanges') or []
        if interchanges:
            def _int_formatter(i, interchange):
                brand = interchange.get('brand_label') or interchange.get('brand_aaiaid') or 'Unknown'
                part = interchange.get('part_number', '')
                print(f"{prefix}     {brand}: {part}")
            print_limited_entries(f"{prefix}🔁 Part Interchanges:", interchanges, _int_formatter, limit=12)
    
    for test in tests:
        print(f"\n🔍 Testing: {test['name']}")
        print(f"   URL: {test['url']}")
        if test.get('params'):
            print(f"   Params: {test['params']}")
        
        try:
            response = requests.get(test['url'], headers=headers, params=test.get('params'), timeout=15)
            print(f"   Status: {response.status_code}")
            data = None

            # For the lookup summary test, print product_id/variant_id and quantity only.
            if test.get('lookup_summary'):
                try:
                    data = response.json()
                    product_id, variant_id, qty = extract_product_variant_qty(data)
                    print(f"   📌 Lookup summary -> product_id={product_id}, variant_id={variant_id}, quantity={qty}")
                    results.append(True if response.status_code == 200 and product_id and variant_id else False)
                except Exception as e:
                    print(f"   ❌ Failed to parse lookup summary: {e}")
                    results.append(False)
                continue

            if response.status_code == 200:
                data = response.json()
                
                if 'products' in data:
                    products = data['products']
                    #print(f" AAAAA {products}")
                    print(f"   ✅ Success: {len(products)} products found")
                    if products:
                        print_product_details(products[0], label="Sample")
                elif 'main_part' in data:
                    sample = data['main_part']
                    print(f"   ✅ Success: main part returned")
                    print_product_details(sample, label="Main Part")
                    related = data.get('related_parts', {})
                    if related:
                        rel_keys = ', '.join([k for k in related.keys() if related.get(k)])
                        if rel_keys:
                            print(f"   🔗 Related parts sections: {rel_keys}")
                    matches = data.get('part_number_matches') or []
                    if matches:
                        print(f"   🔁 Additional matches: {len(matches)} found")
                        print_product_details(matches[0], label="Match Sample")
                elif 'part_number_matches' in data:
                    matches = data['part_number_matches']
                    print(f"   ✅ Success: {len(matches)} matches found")
                    if matches:
                        print_product_details(matches[0], label="Match Sample")
                else:
                    print(f"   ✅ Success: Response received")
                    print(f"   📊 Data keys: {list(data.keys())}")
                    sample = data.get('product') if isinstance(data.get('product'), dict) else data
                    if isinstance(sample, dict):
                        print_product_details(sample, label="Sample")
                
                results.append(True)
            else:
                print(f"   ❌ Failed: {response.status_code}")
                print(f"   Response: {response.text[:100]}...")
                results.append(False)
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    successful = sum(results)
    total = len(results)
    print(f"Tests passed: {successful}/{total}")
    
    if successful == total:
        print("✅ ALL TESTS PASSED - API IS WORKING!")
        print("\n🎯 Ready to sync products!")
        print("   Use: python3 sync_products_from_api.py --search 'brake' --limit 5")
        print("   Or:  python3 sync_products_from_api.py --part-number MPBD1369CV")
    else:
        print("❌ Some tests failed - Check API configuration")
    
    return successful == total

if __name__ == '__main__':
    success = test_api()
    exit(0 if success else 1)
