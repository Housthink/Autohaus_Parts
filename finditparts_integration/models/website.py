from odoo import models

# Mapa de marcas -> archivo de logo (static/img/brands/).
# Logos reales (Wikimedia Commons) + logos de texto generados como respaldo.
BRAND_LOGOS = {
    # Logos reales
    'CATERPILLAR': 'caterpillar.svg',
    'CATERPILLAR-REPLACEMENT': 'caterpillar.svg',
    'CUMMINS': 'cummins.svg',
    'DETROIT': 'detroit.svg',
    'DETROIT DIESEL': 'detroit.svg',
    'DINEX': 'dinex.jpg',
    'EATON CORPORATION': 'eaton.svg',
    'HALDEX': 'haldex.svg',
    'INTERNATIONAL': 'international.svg',
    'MACK': 'mack.png',
    'MILWAUKEE': 'milwaukee.svg',
    'SKF': 'skf.svg',
    'VOLVO': 'volvo.svg',
    # Logos de texto (respaldo)
    'A-1 CARDONE IND.': 'cardone.png',
    'AIMCO': 'aimco.svg',
    'BALDWIN': 'baldwin.svg',
    'BORG WARNER': 'borg_warner.svg',
    'BUFFERS USA': 'buffers_usa.svg',
    'BUYERS PRODUCTS': 'buyers_products.webp',
    'CARLSON': 'carlson.svg',
    'CHELSEA': 'chelsea.svg',
    'CLARK': 'clark.svg',
    'CONDOR-REPLACEMENT': 'condor.svg',
    'CONTINENTAL AG': 'continental.svg',
    'DANA': 'dana.webp',
    'DENSO POWEREDGE': 'denso.svg',
    'DI-PRO INC (DIPRO)': 'dipro.svg',
    'FEDERAL SIGNAL': 'federal_signal.svg',
    'FOUR SEASONS DIVISION': 'four_seasons.svg',
    'FREIGHTLINER': 'freightliner.svg',
    'FULLER': 'fuller.svg',
    'GARRISON': 'garrison.jpg',
    'GATES CORPORATION': 'gates.svg',
    'GEARWRENCH': 'gearwrench.svg',
    'GLOBAL INDUSTRIAL': 'global_industrial.svg',
    'GROTE': 'grote.png',
    'HD VALUE': 'hd_value.svg',
    'HORTON': 'horton.svg',
    'ITM AUTOMOTIVE PARTS': 'itm.svg',
    'JOST': 'jost.svg',
    'LUCAS OIL': 'lucas_oil.png',
    'MAXON INDUSTRIES': 'maxon.svg',
    'MIDWEST TRUCK & AUTO PARTS': 'midwest_truck.svg',
    'MINIMIZER': 'minimizer.png',
    'MONROE': 'monroe.png',
    'NEWSTAR': 'newstar.svg',
    'PAI': 'pai.svg',
    'PETERSON LIGHTING': 'peterson.webp',
    'PETERSON P-M LIGHTING': 'peterson.webp',
    'PIONEER': 'pioneer.svg',
    'POLLACK': 'pollack.svg',
    'ROADWARRIOR': 'roadwarrior.svg',
    'SAF HOLLAND': 'saf_holland.png',
    'SAVE-A-LOAD': 'save_a_load.svg',
    'SEALCO': 'sealco.svg',
    'SEM PRODUCTS': 'sem_products.svg',
    'SK HAND TOOL': 'sk_hand_tool.svg',
    'SPECTRE INDUSTRIES': 'spectre.svg',
    'STANDARD MOTOR PRODUCTS INC.': 'smp.png',
    'TECTRAN': 'tectran.svg',
    'THERMO KING': 'thermo_king.svg',
    'TOMPKINS': 'tompkins.webp',
    'TORQUE PARTS': 'torque_parts.svg',
    'TRAILMOBILE': 'trailmobile.svg',
    'TRAMEC SLOAN': 'tramec_sloan.svg',
    'TRIANGLE SUSPENSION SYSTEMS CO.': 'triangle.svg',
    'TRUCKEX': 'truckex.svg',
    'UNITED PACIFIC': 'united_pacific.webp',
    'VEHICLE SAFETY MANUFACTURING': 'vehicle_safety.svg',
    'VSM (VSMXX)': 'vsm.svg',
    'WABCO': 'wabco.svg',
    'WALKER EXHAUST': 'walker_exhaust.png',
    'WIX FILTERS': 'wix.jpg',
    'WORLD AMERICAN': 'world_american.svg',
}


class Website(models.Model):
    _inherit = 'website'

    def get_brand_logo(self, brand_name):
        """Devuelve la URL del logo de una marca, o False si no existe."""
        name = (brand_name or '').strip().upper()
        if not name:
            return False
        filename = BRAND_LOGOS.get(name)
        if filename:
            return '/finditparts_integration/static/img/brands/' + filename
        # Coincidencia parcial (p. ej. "GATES CORPORATION" -> "GATES")
        for key, filename in BRAND_LOGOS.items():
            if key in name or name in key:
                return '/finditparts_integration/static/img/brands/' + filename
        return False

    def get_whatsapp_url(self):
        self.ensure_one()
        url = self.env['ir.config_parameter'].sudo().get_param(
            'finditparts_integration.whatsapp_url',
            'https://wa.link/1ru5s3',
        )
        url = (url or '').strip()
        if not url:
            return False
        if not url.lower().startswith(('http://', 'https://')):
            url = 'https://' + url
        return url

    def get_home_brands(self, limit=None):
        """Devuelve todas las marcas (product.tag) con productos publicados,
        ordenadas por cantidad de productos, para la seccion de marcas lideres
        del home. Las marcas que tienen logo se muestran primero."""
        Tag = self.env['product.tag'].sudo()
        tags = Tag.search([
            ('visible_to_customers', '=', True),
            ('product_template_ids', '!=', False),
        ])
        counted = []
        for tag in tags:
            published = tag.product_template_ids.filtered(
                lambda p: p.is_published and p.sale_ok
            )
            if published:
                counted.append((len(published), tag))
        counted.sort(key=lambda item: (-item[0], (item[1].name or '').lower()))
        # Prioriza marcas que tienen logo para que la seccion muestre imagenes
        with_logo = [x for x in counted if self.get_brand_logo(x[1].name)]
        without_logo = [x for x in counted if not self.get_brand_logo(x[1].name)]
        ordered = with_logo + without_logo
        if limit:
            ordered = ordered[:limit]
        return [
            {'tag': tag, 'logo': self.get_brand_logo(tag.name)}
            for _count, tag in ordered
        ]
