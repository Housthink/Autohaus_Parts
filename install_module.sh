#!/bin/bash

# FindinPart Integration Module Installation Script
# This script helps install the module in an Odoo environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root"
   exit 1
fi

# Default Odoo addons path
DEFAULT_ADDONS_PATH="/opt/odoo/addons"
CURRENT_DIR=$(pwd)

print_status "FindinPart Integration Module Installation Script"
print_status "=================================================="

# Check if module directory exists
if [ ! -d "finditparts_integration" ]; then
    print_error "Module directory 'finditparts_integration' not found!"
    print_error "Please run this script from the directory containing the module."
    exit 1
fi

# Check if test script passes
print_status "Running module structure tests..."
if python3 test_module.py; then
    print_success "Module structure tests passed!"
else
    print_error "Module structure tests failed! Please fix issues before installation."
    exit 1
fi

# Get Odoo addons path
print_status "Please enter the path to your Odoo addons directory:"
read -p "Addons path [$DEFAULT_ADDONS_PATH]: " ADDONS_PATH
ADDONS_PATH=${ADDONS_PATH:-$DEFAULT_ADDONS_PATH}

# Check if addons path exists
if [ ! -d "$ADDONS_PATH" ]; then
    print_error "Addons directory '$ADDONS_PATH' does not exist!"
    print_error "Please create it or provide the correct path."
    exit 1
fi

# Check if we have write permissions
if [ ! -w "$ADDONS_PATH" ]; then
    print_error "No write permission to '$ADDONS_PATH'"
    print_error "You may need to run this script with sudo or fix permissions."
    exit 1
fi

# Copy module to addons directory
print_status "Copying module to Odoo addons directory..."
if cp -r finditparts_integration "$ADDONS_PATH/"; then
    print_success "Module copied successfully!"
else
    print_error "Failed to copy module to addons directory!"
    exit 1
fi

# Set proper permissions
print_status "Setting proper permissions..."
if chmod -R 755 "$ADDONS_PATH/finditparts_integration"; then
    print_success "Permissions set successfully!"
else
    print_warning "Failed to set permissions. You may need to do this manually."
fi

# Check if Odoo is running
print_status "Checking if Odoo is running..."
if pgrep -f "odoo" > /dev/null; then
    print_warning "Odoo appears to be running."
    print_status "You should restart Odoo to detect the new module."
    print_status "You can do this with: sudo systemctl restart odoo"
else
    print_status "Odoo is not currently running."
fi

# Installation summary
print_success "Installation completed successfully!"
echo ""
print_status "Next steps:"
echo "1. Restart your Odoo server:"
echo "   sudo systemctl restart odoo"
echo "   # or"
echo "   sudo service odoo restart"
echo ""
echo "2. In Odoo web interface:"
echo "   - Go to Apps → Update Apps List"
echo "   - Search for 'FindinPart'"
echo "   - Install the 'FindinPart API Integration' module"
echo ""
echo "3. Configure the module:"
echo "   - Go to FindinPart → Configuration → API Settings"
echo "   - Create a new configuration with your API credentials"
echo "   - Test the API connection"
echo ""
print_status "Module installed at: $ADDONS_PATH/finditparts_integration"

# Check if requirements.txt exists and suggest installing dependencies
if [ -f "requirements.txt" ]; then
    echo ""
    print_warning "Don't forget to install Python dependencies:"
    echo "pip install -r requirements.txt"
    echo ""
    print_status "Or install them individually:"
    echo "pip install requests stripe Pillow python-dateutil"
fi
