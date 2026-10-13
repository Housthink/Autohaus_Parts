#!/bin/bash
# Script para instalar y probar el módulo FindinPart en Odoo

echo "======================================================"
echo "FindinPart Module Installation Guide"
echo "======================================================"

echo ""
echo "STEP 1: Copy module to Odoo addons directory"
echo "------------------------------------------------------"
echo "Run this command (adjust path to your Odoo installation):"
echo ""
echo "  sudo cp -r finditparts_integration /opt/odoo/addons/"
echo "  # or"
echo "  sudo cp -r finditparts_integration /usr/lib/python3/dist-packages/odoo/addons/"
echo "  # or to custom addons directory:"
echo "  cp -r finditparts_integration /path/to/your/custom/addons/"
echo ""

echo "STEP 2: Install Python dependencies"
echo "------------------------------------------------------"
echo "  pip3 install requests"
echo ""

echo "STEP 3: Restart Odoo server"
echo "------------------------------------------------------"
echo "  sudo systemctl restart odoo"
echo "  # or"
echo "  sudo service odoo restart"
echo ""

echo "STEP 4: Install module in Odoo"
echo "------------------------------------------------------"
echo "1. Open Odoo in your browser"
echo "2. Go to Apps → Update Apps List"
echo "3. Search for 'FindinPart'"
echo "4. Click Install on 'FindinPart API Integration'"
echo ""

echo "STEP 5: Configure API credentials"
echo "------------------------------------------------------"
echo "1. Go to FindinPart → Configuration → API Settings"
echo "2. Click 'Create'"
echo "3. Fill in the configuration:"
echo "   - Configuration Name: Production"
echo "   - API Base URL: https://www-build.finditparts.com"
echo "   - JWT Issuer: autohaus-build"
echo "   - JWT Secret: 222b6c16-b54a-4ad6-a2c7-e43ba7c23060"
echo "   - JWT Audience: https://api.finditparts.com"
echo "   - JWT Token Expiry: 1 hour"
echo "4. Click 'Save'"
echo "5. Click 'Test Connection' button"
echo ""

echo "STEP 6: Test functionality"
echo "------------------------------------------------------"
echo "If 'Test Connection' shows 'Success':"
echo "✓ API integration is working!"
echo "✓ You can now sync products"
echo "✓ Module is ready for production use"
echo ""

echo "Current configuration file:"
echo "------------------------------------------------------"
cat api_config.json
echo ""

echo "Module structure validation:"
echo "------------------------------------------------------"
python3 test_module.py
echo ""

echo "Quick API test:"
echo "------------------------------------------------------"
python3 test_api.py
