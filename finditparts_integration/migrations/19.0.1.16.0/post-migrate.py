"""Migracion 19.0.1.16.0

Reescribe el HTML guardado de Quick Facts / Product Attributes del formato de
dos tarjetas (o_autohaus_facts_inner / o_autohaus_facts_card) al formato de
pestanas (o_autohaus_facts_panel / o_autohaus_facts_tabs).

El HTML de la descripcion se genera una sola vez durante la sincronizacion y
queda guardado en la base de datos, por lo que un deploy de codigo no lo
actualiza. Esta migracion convierte los registros antiguos:

  <div class='o_autohaus_facts container'>
    <div class='o_autohaus_facts_inner'>
      <div class='o_autohaus_facts_card'>...</div>
      <div class='o_autohaus_facts_card'>...</div>
    </div>
  </div>

al formato actual de pestanas:

  <div class='o_autohaus_facts container'>
    <div class='o_autohaus_facts_panel'>
      <ul class='nav nav-tabs o_autohaus_facts_tabs'>...</ul>
      <div class='tab-content o_autohaus_facts_content'>...</div>
    </div>
  </div>

Es idempotente: los registros que ya estan en el formato nuevo se omiten.
"""

import html as html_lib
import logging

import odoo
from lxml import html as LH

_logger = logging.getLogger(__name__)

OLD_MARKER = 'o_autohaus_facts_inner'
NEW_MARKER = 'o_autohaus_facts_panel'

PANE_IDS = {
    'Quick Facts': 'o_autohaus_facts_pane',
    'Product Attributes': 'o_autohaus_attrs_pane',
}


def _clean(text):
    return ' '.join((text or '').split())


def _esc(text):
    return html_lib.escape(_clean(text), quote=False)


def _convert_cards_to_tabs(old_html):
    """Convierte el formato de dos tarjetas al formato de pestanas."""
    try:
        root = LH.fragment_fromstring(old_html, create_parent='div')
    except Exception:
        return None

    inner = root.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' %s ')]" % OLD_MARKER
    )
    if not inner:
        return None
    inner = inner[0]

    cards = inner.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_autohaus_facts_card ')]"
    )
    if not cards:
        return None

    sections = []
    for card in cards:
        title_el = card.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_autohaus_facts_title ')]"
        )
        table_el = card.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' o_autohaus_facts_table ')]"
        )
        if not title_el or not table_el:
            continue
        title = _clean(title_el[0].text_content())
        if not title:
            continue
        table_html = LH.tostring(table_el[0], encoding='unicode')
        sections.append((title, table_html))

    if not sections:
        return None

    if len(sections) == 1:
        title, table_html = sections[0]
        body = (
            "<h3 class='o_autohaus_facts_title'>" + _esc(title) + "</h3>"
            + table_html
        )
    else:
        tabs = ''
        panes = ''
        for index, (title, table_html) in enumerate(sections):
            pane_id = PANE_IDS.get(title, "o_autohaus_pane_%d" % index)
            active = " active" if index == 0 else ""
            show = " show active" if index == 0 else ""
            tabs += (
                "<li class='nav-item'>"
                "<a class='nav-link%s' data-bs-toggle='tab' href='#%s'>%s</a>"
                "</li>" % (active, pane_id, _esc(title))
            )
            panes += (
                "<div class='tab-pane fade%s' id='%s'>%s</div>"
                % (show, pane_id, table_html)
            )
        body = (
            "<ul class='nav nav-tabs o_autohaus_facts_tabs'>" + tabs + "</ul>"
            "<div class='tab-content o_autohaus_facts_content'>" + panes + "</div>"
        )

    return (
        "<div class='o_autohaus_facts container'>"
        "<div class='o_autohaus_facts_panel'>" + body + "</div>"
        "</div>"
    )


def _migrate_model(env, model, field):
    records = env[model].sudo().search([(field, 'like', OLD_MARKER)])
    changed = 0
    for record in records:
        new_html = _convert_cards_to_tabs(record[field])
        if new_html and new_html != record[field]:
            record.write({field: new_html})
            changed += 1
    return changed


def migrate(cr, version):
    if not version:
        return

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    total = 0
    total += _migrate_model(env, 'finditparts.product', 'long_description')
    total += _migrate_model(env, 'product.template', 'website_description')
    _logger.info(
        'finditparts_integration 19.0.1.16.0: %s descripciones migradas '
        'al formato de pestanas.', total
    )
