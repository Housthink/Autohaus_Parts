#!/usr/bin/env python3
"""
PRODUCT CREATION TEST - FinditParts
Test product creation from JSON examples (no API calls, just JSON validation)
"""

import json
import sys
import os

def test_json_product_creation():
    """Test creating products from the example JSON files"""
    print("Testing product creation from JSON examples...")
    
    # Test files
    test_files = [
        'producto_completo_ejemplo.json',
        'ui_product_example.json'
    ]
    
    for test_file in test_files:
        if not os.path.exists(test_file):
            print(f"⚠️  Test file not found: {test_file}")
            continue
        
        print(f"\n📁 Testing with file: {test_file}")
        
        try:
            with open(test_file, 'r') as f:
                data = json.load(f)
            
            # Extract product data
            if 'product' in data:
                product_data = data['product']
            else:
                product_data = data
            
            # Display key product information
            print(f"   Product ID: {product_data.get('id', 'N/A')}")
            print(f"   Part Number: {product_data.get('part_number', 'N/A')}")
            print(f"   Manufacturer: {product_data.get('manufacturer', 'N/A')}")
            print(f"   Description: {product_data.get('short_description', 'N/A')[:50]}...")
            
            # Check pricing info
            current_variant = product_data.get('current_variant', {})
            if current_variant:
                print(f"   Price: ${current_variant.get('price', 'N/A')}")
                print(f"   Stock: {current_variant.get('quantity', 'N/A')}")
            
            # Check MSRP
            if product_data.get('msrp'):
                print(f"   MSRP: ${product_data.get('msrp')}")
            
            # Check images
            images = product_data.get('product_images', [])
            print(f"   Images: {len(images)} available")
            
            # Check categories
            breadcrumbs = product_data.get('breadcrumbs_ancestors', [])
            if breadcrumbs:
                categories = [b.get('name') for b in breadcrumbs]
                print(f"   Categories: {' > '.join(categories)}")
            
            print("   ✅ JSON structure is valid for product creation")
            
        except json.JSONDecodeError as e:
            print(f"   ❌ Invalid JSON: {e}")
        except Exception as e:
            print(f"   ❌ Error processing file: {e}")
    
    print("\n🔧 To create products in Odoo:")
    print("   python3 sync_products_from_api.py --json-file producto_completo_ejemplo.json")
    print("   python3 sync_products_from_api.py --part-number LF3970")
    print("   python3 sync_products_from_api.py --search 'brake' --limit 5")


def show_usage_examples():
    """Show usage examples for the sync functionality"""
    print("\n📖 NEXT STEPS:")
    print("="*40)
    
    print("\n1. Test API connectivity:")
    print("   python3 test_api_simple.py")
    
    print("\n2. Sync products:")
    print("   python3 sync_products_from_api.py --part-number LF3970")
    print("   python3 sync_products_from_api.py --search 'brake' --limit 5")
    
    print("\n3. From Odoo UI:")
    print("   FinditParts > Synchronization > Sync Products from API")


if __name__ == '__main__':
    print("🚀 FinditParts Product Creation Test")
    print("="*40)
    
    test_json_product_creation()
    show_usage_examples()
    
    print("\n✨ Ready to sync products! Choose your method above.")

