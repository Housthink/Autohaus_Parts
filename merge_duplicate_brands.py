"""
Fusiona tags de marca duplicados (product.tag) generados por variantes
textuales del mismo fabricante (p. ej. "CATERPILLAR" vs "CATERPILLAR-REPLACEMENT")
y renombra los tags sueltos que conservan el sufijo "-REPLACEMENT".

Usa la misma normalizacion que `_ensure_brand_tag` para agrupar los tags y
reasigna los productos al tag canonico antes de eliminar los duplicados.

Ejecutar dentro del contenedor Odoo (en modo dry-run por defecto):

    docker exec -i iom-odoo19 odoo shell -d autohouse --no-http < merge_duplicate_brands.py

Para aplicar los cambios de verdad:

    docker exec -i -e MERGE_DRY_RUN=0 iom-odoo19 odoo shell -d autohouse --no-http < merge_duplicate_brands.py
"""

import os

from odoo.addons.finditparts_integration.models.website import normalize_brand_name

DRY_RUN = os.environ.get('MERGE_DRY_RUN', '1') not in ('0', 'false', 'False')

LANGUAGES = ('en_US', 'es_419')


def _canonical_tag(group, norm):
    """Elige el tag canonico de un grupo: el que ya tiene el nombre
    normalizado; si no existe, el que mas productos tiene (y menor id)."""
    for tag in group:
        if (tag.name or '').strip().upper() == norm:
            return tag
    return sorted(
        group,
        key=lambda t: (-len(t.product_template_ids), t.id),
    )[0]


def _rename(tag, norm):
    """Renombra un tag actualizando su nombre en todos los idiomas activos."""
    for lang in LANGUAGES:
        tag.with_context(lang=lang).sudo().write({'name': norm})


def merge_duplicate_brands():
    Tag = env['product.tag']
    tags = Tag.sudo().search([])

    groups = {}
    for tag in tags:
        norm = normalize_brand_name(tag.name)
        if not norm:
            continue
        groups.setdefault(norm, []).append(tag)

    renamed = []
    merges = []
    for norm, group in groups.items():
        canonical = _canonical_tag(group, norm)
        if (canonical.name or '').strip().upper() != norm:
            renamed.append((canonical, norm))
        others = [t for t in group if t.id != canonical.id]
        if others:
            merges.append((canonical, others))

    print('Tags a renombrar:', len(renamed))
    for tag, norm in renamed:
        print('  * renombrar %r (id=%d) -> %r' % (tag.name, tag.id, norm))
        if not DRY_RUN:
            _rename(tag, norm)

    print('Grupos a fusionar:', len(merges))
    total_reassigned = 0
    total_removed = 0
    for canonical, others in merges:
        print('  -> canonico: %r (id=%d, %d productos)'
              % (canonical.name, canonical.id, len(canonical.product_template_ids)))
        for other in others:
            products = other.product_template_ids
            print('     fusionar: %r (id=%d, %d productos)'
                  % (other.name, other.id, len(products)))
            if not DRY_RUN and products:
                products.sudo().write({'product_tag_ids': [(4, canonical.id)]})
                total_reassigned += len(products)
            if not DRY_RUN:
                other.sudo().unlink()
                total_removed += 1

    if DRY_RUN:
        print('\nDRY RUN: no se aplico ningun cambio.')
    else:
        env.cr.commit()
        print('\nAplicado: %d renames, %d productos reasignados, %d tags eliminados.'
              % (len(renamed), total_reassigned, total_removed))


merge_duplicate_brands()
