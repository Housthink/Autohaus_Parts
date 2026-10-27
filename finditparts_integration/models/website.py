from odoo import models

# Mapa de marcas -> archivo de logo (static/img/brands/).
# Solo logos graficos reales (archivos > ~900 bytes). Los placeholders de
# texto (SVGs de ~250 bytes) se excluyeron para que el home muestre
# unicamente marcas con logo real.
BRAND_LOGOS = {
    'A-1 CARDONE IND.': 'cardone.png',
    'BORG WARNER': 'borg_warner.svg',
    'BUYERS PRODUCTS': 'buyers_products.webp',
    'CATERPILLAR': 'caterpillar.svg',
    'CONTINENTAL AG': 'continental.svg',
    'CUMMINS': 'cummins.svg',
    'DANA': 'dana.webp',
    'DENSO POWEREDGE': 'denso.svg',
    'DETROIT': 'detroit.svg',
    'DINEX': 'dinex.jpg',
    'EATON CORPORATION': 'eaton.svg',
    'FEDERAL SIGNAL': 'federal_signal.svg',
    'FREIGHTLINER': 'freightliner.svg',
    'GARRISON': 'garrison.jpg',
    'GROTE': 'grote.png',
    'HALDEX': 'haldex.svg',
    'INTERNATIONAL': 'international.svg',
    'JOST': 'jost.svg',
    'LUCAS OIL': 'lucas_oil.png',
    'MACK': 'mack.png',
    'MAXON INDUSTRIES': 'maxon.svg',
    'MILWAUKEE': 'milwaukee.svg',
    'MINIMIZER': 'minimizer.png',
    'MONROE': 'monroe.png',
    'PAI': 'pai.svg',
    'PETERSON LIGHTING': 'peterson.webp',
    'SAF HOLLAND': 'saf_holland.png',
    'SKF': 'skf.svg',
    'STANDARD MOTOR PRODUCTS INC.': 'smp.png',
    'THERMO KING': 'thermo_king.svg',
    'TOMPKINS': 'tompkins.webp',
    'UNITED PACIFIC': 'united_pacific.webp',
    'VOLVO': 'volvo.svg',
    'WALKER EXHAUST': 'walker_exhaust.png',
    'WIX': 'wix.jpg',
}

# Sufijo generico que la API de FinditParts agrega a algunas marcas
# (p. ej. "CATERPILLAR-REPLACEMENT") y que se debe eliminar para que
# todas las variantes caigan en la misma etiqueta.
BRAND_REPLACEMENT_SUFFIX = '-REPLACEMENT'

# Mapeo de variantes de nombre de marca -> nombre canonico.
# Sirve para colapsar variaciones textuales que representan la misma marca
# y asi evitar tags duplicados en el catalogo y en el home del website.
BRAND_NORMALIZATION = {
    # Sufijos "-REPLACEMENT" explicitos
    'CATERPILLAR-REPLACEMENT': 'CATERPILLAR',
    'DANA HOLDING CORPORATION-REPLACEMENT': 'DANA',
    # Variantes de nombre conocidas
    'DETROIT DIESEL': 'DETROIT',
    'PETERSON P-M LIGHTING': 'PETERSON LIGHTING',
    'FOUR SEASONS DIVISION': 'FOUR SEASONS',
    'FOUR SEASONS TEMP PARTS': 'FOUR SEASONS',
    '4-SEASONS': 'FOUR SEASONS',
    'GATES CORPORATION': 'GATES',
    'GATES RUBBER PRODUCTS': 'GATES',
    'DANA HOLDING CORPORATION': 'DANA',
    'DANA HOLDINGS CORPORATION': 'DANA',
    'TRIANGLE SUSPENSION SYSTEMS CO': 'TRIANGLE SUSPENSION SYSTEMS CO.',
    'MILWAUKEE ELEC. TOOL': 'MILWAUKEE',
    'WIX FILTERS': 'WIX',
    'WALKER EXHAUST PRODUCTS': 'WALKER EXHAUST',
    'MONROE RIDE CONTROL': 'MONROE',
    'POLLAK': 'POLLACK',
    'MSC UNDUSTRIAL': 'MSC INDUSTRIAL',
    'FEDERAL-MOGUL': 'FEDERAL MOGUL',
    'MAGNAFLOW EXHAUST PRODUCT': 'MAGNAFLOW EXHAUST PRODUCTS',
    'AC DELCO': 'ACDELCO',
    'DINEX A/S': 'DINEX',
    'TSI PRODUCTS INC': 'TSI PRODUCTS',
}


def normalize_brand_name(brand_name):
    """Normaliza el nombre de una marca a un canonico unico.

    Colapsa variantes que representan la misma marca para evitar tags
    duplicados: aplica primero el mapeo explicito y luego elimina el sufijo
    generico "-REPLACEMENT". Devuelve el nombre en mayusculas y sin espacios
    sobrantes.
    """
    name = (brand_name or '').strip()
    if not name:
        return ''
    upper = name.upper()
    if upper in BRAND_NORMALIZATION:
        return BRAND_NORMALIZATION[upper]
    if upper.endswith(BRAND_REPLACEMENT_SUFFIX):
        base = upper[:-len(BRAND_REPLACEMENT_SUFFIX)].strip()
        if base:
            return BRAND_NORMALIZATION.get(base, base)
    return upper


class Website(models.Model):
    _inherit = 'website'

    def get_brand_logo(self, brand_name):
        """Devuelve la URL del logo de una marca, o False si no existe.

        Solo coincide por nombre exacto (en mayusculas); las marcas sin logo
        registrado devuelven False para que no aparezcan en el home."""
        name = (brand_name or '').strip().upper()
        if not name:
            return False
        filename = BRAND_LOGOS.get(name)
        if filename:
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
        """Devuelve las marcas (product.tag) con productos publicados y con
        logo, ordenadas por cantidad de productos, para la seccion de marcas
        lideres del home. Solo se muestran marcas que tienen logo."""
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
        ordered = [x for x in counted if self.get_brand_logo(x[1].name)]
        if limit:
            ordered = ordered[:limit]
        return [
            {'tag': tag, 'logo': self.get_brand_logo(tag.name)}
            for _count, tag in ordered
        ]

    def get_all_brands_grouped(self):
        """Devuelve todas las marcas (product.tag) con productos publicados,
        agrupadas por letra inicial (A-Z) y ordenadas alfabeticamente, para el
        glosario de marcas."""
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
        counted.sort(key=lambda item: (item[1].name or '').strip().upper())
        grouped = {}
        for _count, tag in counted:
            first_letter = (tag.name or '').strip().upper()[:1]
            if not first_letter.isalpha():
                first_letter = '#'
            grouped.setdefault(first_letter, []).append(tag)
        return grouped
