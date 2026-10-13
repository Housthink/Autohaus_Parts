#!/usr/bin/env python3
"""
Standalone script to sync products from FinditParts API to Odoo
This script can be run independently or called from within Odoo

Usage:
    python sync_products_from_api.py --search "brake pads"
    python sync_products_from_api.py --part-number "LF3970"
    python sync_products_from_api.py --all --limit 50
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync_products.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def setup_odoo_environment():
    """Setup Odoo environment for standalone execution"""
    try:
        import odoo
        from odoo import api, SUPERUSER_ID
        from odoo.tools import config
        
        # Initialize Odoo configuration
        config.parse_config([])
        
        # Initialize database
        db_name = os.environ.get('ODOO_DATABASE', 'finditparts_db')
        
        # Get registry and environment
        registry = odoo.registry(db_name)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            return env
            
    except ImportError:
        logger.error("Odoo not found. Make sure you're running this script in Odoo environment.")
        return None
    except Exception as e:
        logger.error(f"Failed to setup Odoo environment: {str(e)}")
        return None


def sync_products_standalone(search_query=None, part_number=None, limit=100, create_odoo=True):
    """Standalone product sync function"""
    logger.info("Starting standalone product sync...")
    
    env = setup_odoo_environment()
    if not env:
        return False
    
    try:
        # Get the product model
        product_model = env['finditparts.product']
        
        # Execute sync
        results = product_model.sync_products_from_api(
            search_query=search_query,
            part_number=part_number,
            limit=limit
        )
        
        # Log results
        logger.info(f"Sync completed successfully!")
        logger.info(f"Created: {results['created']} products")
        logger.info(f"Updated: {results['updated']} products")
        logger.info(f"Errors: {len(results['errors'])}")
        
        if results['errors']:
            logger.warning("Errors encountered:")
            for error in results['errors'][:10]:  # Show first 10 errors
                logger.warning(f"  - {error}")
            if len(results['errors']) > 10:
                logger.warning(f"  ... and {len(results['errors']) - 10} more errors")
        
        # Save results to file
        results_file = f"sync_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            # Convert product objects to dict for JSON serialization
            json_results = {
                'created': results['created'],
                'updated': results['updated'],
                'errors': results['errors'],
                'timestamp': datetime.now().isoformat(),
                'parameters': {
                    'search_query': search_query,
                    'part_number': part_number,
                    'limit': limit
                }
            }
            json.dump(json_results, f, indent=2)
        
        logger.info(f"Results saved to: {results_file}")
        return True
        
    except Exception as e:
        logger.error(f"Sync failed: {str(e)}")
        return False


def sync_from_json_file(json_file_path):
    """Sync products from a JSON file containing product data"""
    logger.info(f"Syncing products from JSON file: {json_file_path}")
    
    if not os.path.exists(json_file_path):
        logger.error(f"JSON file not found: {json_file_path}")
        return False
    
    env = setup_odoo_environment()
    if not env:
        return False
    
    try:
        # Read JSON file
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        
        product_model = env['finditparts.product']
        created_count = 0
        updated_count = 0
        errors = []
        
        # Handle different JSON structures
        products_data = []
        if isinstance(data, list):
            products_data = data
        elif isinstance(data, dict):
            if 'products' in data:
                products_data = data['products']
            elif 'product' in data:
                products_data = [data]
            else:
                products_data = [data]
        
        for product_data in products_data:
            try:
                # Create product from JSON
                finditparts_product = product_model.create_from_api_json(product_data)
                
                # Sync to Odoo
                sync_result = finditparts_product.sync_to_odoo()
                if sync_result:
                    if finditparts_product.odoo_product_id:
                        created_count += 1
                    else:
                        updated_count += 1
                else:
                    errors.append(f"Failed to sync {finditparts_product.sku} to Odoo")
                    
            except Exception as e:
                part_num = product_data.get('part_number', 'Unknown')
                error_msg = f"Failed to process product {part_num}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        logger.info(f"JSON sync completed!")
        logger.info(f"Created: {created_count} products")
        logger.info(f"Updated: {updated_count} products")
        logger.info(f"Errors: {len(errors)}")
        
        if errors:
            logger.warning("Errors encountered:")
            for error in errors[:10]:
                logger.warning(f"  - {error}")
            if len(errors) > 10:
                logger.warning(f"  ... and {len(errors) - 10} more errors")
        
        return True
        
    except Exception as e:
        logger.error(f"JSON sync failed: {str(e)}")
        return False


def main():
    """Main function for command line execution"""
    parser = argparse.ArgumentParser(description='Sync products from FinditParts API to Odoo')
    
    # Sync type arguments (mutually exclusive)
    sync_group = parser.add_mutually_exclusive_group(required=True)
    sync_group.add_argument('--search', type=str, help='Search products by keyword')
    sync_group.add_argument('--part-number', type=str, help='Sync specific product by part number')
    sync_group.add_argument('--all', action='store_true', help='Sync all products (limited by --limit)')
    sync_group.add_argument('--json-file', type=str, help='Sync products from JSON file')
    
    # Optional arguments
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of products to sync (default: 100)')
    parser.add_argument('--no-odoo', action='store_true', help='Don\'t create products in Odoo, only in finditparts.product')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Execute sync based on arguments
    success = False
    
    if args.json_file:
        success = sync_from_json_file(args.json_file)
    else:
        success = sync_products_standalone(
            search_query=args.search,
            part_number=args.part_number,
            limit=args.limit,
            create_odoo=not args.no_odoo
        )
    
    if success:
        logger.info("Script completed successfully!")
        sys.exit(0)
    else:
        logger.error("Script failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()

