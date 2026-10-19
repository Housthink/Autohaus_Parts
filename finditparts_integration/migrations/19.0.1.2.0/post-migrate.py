"""Migracion 19.0.1.2.0

Reescribe el HTML guardado de Quick Facts / Product Attributes al diseno
de tarjetas (o_autohaus_facts) en todas las bases de datos, incluidas las
de produccion (Odoo.sh).

El HTML de la descripcion se genera una sola vez durante la sincronizacion
y queda guardado en la base de datos, por lo que un deploy de codigo no lo
actualiza. Esta migracion convierte los registros antiguos:

  - <div class="finditparts-long-description"> ... <h4> + <table>
  - formato intermedio de tarjetas sin el wrapper flex

al formato actual:

  <div class='o_autohaus_facts container'>
    <div class='o_autohaus_facts_inner'>
      <div class='o_autohaus_facts_card'>...</div>
      <div class='o_autohaus_facts_card'>...</div>
    </div>
  </div>

Es idempotente: los registros que ya estan en el formato nuevo se omiten.
"""

import html as html_lib
import logging

import odoo
from lxml import html as LH

_logger = logging.getLogger(__name__)

LEGACY_MARKER = 'finditparts-long-description'
NEW_MARKER = 'o_autohaus_facts_inner'
KEEP_SECTIONS = ('Quick Facts', 'Product Attributes')


def _clean(text):
    return ' '.join((text or '').split())


def _esc(text):
    return html_lib.escape(_clean(text), quote=False)


def _rows(table):
    """Devuelve [(etiqueta, valor), ...] de una tabla etiqueta/valor."""
    rows = []
    for tr in table.xpath('.//tr'):
        ths = tr.xpath('./th')
        tds = tr.xpath('./td')
        if not ths or not tds:
            continue
        label = _clean(ths[0].text_content())
        value = tds[0].text_content().strip()
        if label and value:
            rows.append((label, value))
    return rows


def _card(title, rows):
    if not rows:
        return ''
    body = ''.join(
        "<div class='o_autohaus_facts_row'>"
        f"<span class='o_autohaus_facts_label'>{_esc(label)}</span>"
        f"<span class='o_autohaus_facts_value'>{_esc(value)}</span>"
        "</div>"
        for label, value in rows
    )
    return (
        "<div class='o_autohaus_facts_card'>"
        f"<h3 class='o_autohaus_facts_title'>{_esc(title)}</h3>"
        f"<div class='o_autohaus_facts_table'>{body}</div>"
        "</div>"
    )


def _convert_legacy(old_html):
    """Convierte el formato viejo (h4 + tables) al de tarjetas."""
    try:
        root = LH.fragment_fromstring(old_html, create_parent='div')
    except Exception:
        return None

    wraps = root.xpath(".//*[contains(@class,'%s')]" % LEGACY_MARKER)
    if not wraps:
        return None
    wrap = wraps[0]

    cards = []
    for h4 in wrap.xpath('.//h4'):
        title = _clean(h4.text_content())
        if title not in KEEP_SECTIONS:
            continue
        table = h4.getnext()
        while table is not None and getattr(table, 'tag', '').lower() != 'table':
            table = table.getnext()
        if table is None:
            continue
        card = _card(title, _rows(table))
        if card:
            cards.append(card)

    if not cards:
        return None
    return (
        "<div class='o_autohaus_facts container'>"
        "<div class='o_autohaus_facts_inner'>"
        + ''.join(cards)
        + "</div></div>"
    )


def _wrap_existing(old_html):
    """Envuelve tarjetas del formato intermedio en el wrapper flex."""
    try:
        root = LH.fragment_fromstring(old_html, create_parent='div')
    except Exception:
        return None

    target = None
    for el in root.iter():
        classes = (el.get('class') or '').split()
        if 'o_autohaus_facts' in classes:
            target = el
            break
    if target is None:
        return None

    inner = LH.Element('div', attrib={'class': 'o_autohaus_facts_inner'})
    for child in list(target):
        target.remove(child)
        inner.append(child)
    if len(inner) == 0:
        return None
    target.append(inner)
    return LH.tostring(target, encoding='unicode')


def to_new_html(value):
    """Devuelve el HTML nuevo, o None si no hay nada que migrar."""
    if not value:
        return None
    text = str(value)
    if NEW_MARKER in text:
        return None
    if LEGACY_MARKER in text:
        return _convert_legacy(text)
    if 'o_autohaus_facts' in text:
        return _wrap_existing(text)
    return None


def _migrate_model(env, model, field):
    records = env[model].sudo().search(
        ['|', (field, 'like', LEGACY_MARKER), (field, 'like', 'o_autohaus_facts')]
    )
    changed = 0
    for record in records:
        new_html = to_new_html(record[field])
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
        'finditparts_integration 19.0.1.2.0: %s descripciones migradas '
        'al diseno de tarjetas.', total
    )
