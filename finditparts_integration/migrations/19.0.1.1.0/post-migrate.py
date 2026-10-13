import re
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _parse_expression(expr):
    """Map an old cron_expression value to (interval_number, interval_type)."""
    expr = (expr or '').strip()
    m = re.match(r'^\*/(\d+)\s+\*\s+\*\s+\*\s+\*$', expr)
    if m:
        return int(m.group(1)), 'minutes'
    m = re.match(r'^0\s+\*/(\d+)\s+\*\s+\*\s+\*\s*$', expr)
    if m:
        return int(m.group(1)), 'hours'
    return None


def migrate(cr, version):
    # The old ``cron_expression`` column still exists at this point:
    # read it with raw SQL and translate it to the new interval fields.
    cr.execute("SELECT id, cron_expression FROM finditparts_sync_cron")
    for rec_id, expr in cr.fetchall():
        interval = _parse_expression(expr)
        if not interval:
            continue
        cr.execute(
            "UPDATE finditparts_sync_cron SET interval_number=%s, interval_type=%s WHERE id=%s",
            (interval[0], interval[1], rec_id),
        )

    # Re-sync every linked ir.cron so it picks up the new interval.
    env = api.Environment(cr, SUPERUSER_ID, {})
    for record in env['finditparts.sync.cron'].search([]):
        record._sync_ir_cron()
