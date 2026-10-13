#!/usr/bin/env python3
"""
VERIFICACIÓN POST-INSTALACIÓN - FinditParts
Script para verificar que todo está listo después de instalar el módulo
"""

import os
import sys
import json

def check_module_structure():
    """Verificar estructura del módulo"""
    print("🔍 Verificando estructura del módulo...")
    
    required_files = [
        'finditparts_integration/__manifest__.py',
        'finditparts_integration/models/__init__.py',
        'finditparts_integration/models/finditparts_product.py',
        'finditparts_integration/models/finditparts_sync_wizard.py',
        'finditparts_integration/utils/api_client.py',
        'finditparts_integration/views/finditparts_sync_wizard_views.xml',
        'finditparts_integration/security/ir.model.access.csv'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Archivos faltantes:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    else:
        print("✅ Estructura del módulo: OK")
        return True

def check_config_files():
    """Verificar archivos de configuración"""
    print("\n🔍 Verificando archivos de configuración...")
    
    if os.path.exists('api_config.json'):
        try:
            with open('api_config.json', 'r') as f:
                config = json.load(f)
            
            required_keys = ['api_base_url', 'jwt_issuer', 'jwt_secret', 'jwt_audience']
            missing_keys = [key for key in required_keys if key not in config]
            
            if missing_keys:
                print(f"❌ Configuración incompleta. Faltan: {missing_keys}")
                return False
            else:
                print("✅ Configuración API: OK")
                return True
        except Exception as e:
            print(f"❌ Error leyendo configuración: {e}")
            return False
    else:
        print("⚠️  api_config.json no encontrado (opcional)")
        return True

def check_test_scripts():
    """Verificar scripts de prueba"""
    print("\n🔍 Verificando scripts de prueba...")
    
    required_scripts = [
        'test_api_simple.py',
        'test_all_endpoints.py', 
        'test_product_creation.py',
        'sync_products_from_api.py'
    ]
    
    missing_scripts = []
    for script in required_scripts:
        if not os.path.exists(script):
            missing_scripts.append(script)
    
    if missing_scripts:
        print("❌ Scripts faltantes:")
        for script in missing_scripts:
            print(f"   - {script}")
        return False
    else:
        print("✅ Scripts de prueba: OK")
        return True

def check_example_files():
    """Verificar archivos de ejemplo"""
    print("\n🔍 Verificando archivos de ejemplo...")
    
    example_files = [
        'producto_completo_ejemplo.json',
        'ui_product_example.json'
    ]
    
    found_files = []
    for file_path in example_files:
        if os.path.exists(file_path):
            found_files.append(file_path)
    
    if found_files:
        print(f"✅ Archivos de ejemplo: {len(found_files)} encontrados")
        return True
    else:
        print("⚠️  No se encontraron archivos de ejemplo JSON")
        return False

def show_next_steps():
    """Mostrar próximos pasos"""
    print("\n" + "="*50)
    print("📋 PRÓXIMOS PASOS PARA EL CLIENTE")
    print("="*50)
    
    print("\n1. 🛠️  INSTALAR MÓDULO EN ODOO:")
    print("   ./install_module.sh")
    
    print("\n2. ⚙️  CONFIGURAR EN ODOO:")
    print("   - FinditParts > Configuration > API Settings")
    print("   - Crear configuración con credenciales JWT")
    print("   - Activar 'Auto Create Products'")
    print("   - Configurar Default Warehouse")
    
    print("\n3. 🧪 PROBAR API:")
    print("   python3 test_api_simple.py")
    
    print("\n4. 🚀 SINCRONIZAR PRODUCTOS:")
    print("   - Desde Odoo: FinditParts > Synchronization > Sync Products from API")
    print("   - O desde línea de comandos: python3 sync_products_from_api.py --part-number LF3970")
    
    print("\n5. ✅ VERIFICAR EN ODOO:")
    print("   - Inventory > Products > Products")
    print("   - Buscar productos sincronizados")
    print("   - Crear cotización con productos")

def main():
    print("🚀 VERIFICACIÓN POST-INSTALACIÓN - FinditParts")
    print("=" * 50)
    
    checks = [
        check_module_structure(),
        check_config_files(),
        check_test_scripts(),
        check_example_files()
    ]
    
    passed_checks = sum(checks)
    total_checks = len(checks)
    
    print("\n" + "="*50)
    print("📊 RESUMEN DE VERIFICACIÓN")
    print("="*50)
    print(f"Verificaciones pasadas: {passed_checks}/{total_checks}")
    
    if passed_checks == total_checks:
        print("✅ ¡TODO LISTO PARA INSTALAR!")
        print("🎯 El módulo está completo y listo para usar")
        show_next_steps()
        return True
    else:
        print("⚠️  Algunas verificaciones fallaron")
        print("Por favor, revisa los errores arriba antes de continuar")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
