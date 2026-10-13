from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class FinditPartsSyncCron(models.Model):
    _name = 'finditparts.sync.cron'
    _description = 'FinditParts Scheduled Sync'

    name = fields.Char(string='Name', required=True, default='FinditParts Sync')
    sync_type = fields.Selection([
        ('search', 'Search Products'),
        ('part_number', 'Specific Part Number'),
        ('all', 'All Products (Limited)'),
    ], string='Sync Type', default='search', required=True)
    search_query = fields.Char(string='Search Query')
    part_number = fields.Char(string='Part Number')
    limit = fields.Integer(string='Limit', default=100)
    interval_number = fields.Integer(
        string='Interval',
        default=30,
        required=True,
        help='Cada cuántas unidades de tiempo se ejecuta el sync (ej. 5).'
    )
    interval_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], string='Interval Unit', default='minutes', required=True,
        help='Unidad del intervalo (ej. Hours). 5 + Hours = cada 5 horas.')
    config_id = fields.Many2one(
        'finditparts.config',
        string='Configuration',
        help='Configuracion de FinditParts a usar. Si se deja vacio se usa la configuracion activa.'
    )
    ir_cron_id = fields.Many2one('ir.cron', string='Linked Cron', readonly=True, ondelete='set null')
    active = fields.Boolean(default=True)
    next_execution = fields.Datetime(string='Next Execution', related='ir_cron_id.nextcall', readonly=True)
    last_run = fields.Datetime(string='Last Run', readonly=True)
    last_result = fields.Text(string='Last Result', readonly=True)
    last_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial'),
        ('never', 'Never Ran'),
    ], string='Last Status', default='never', readonly=True)
    last_created = fields.Integer(string='Last Created', readonly=True)
    last_updated = fields.Integer(string='Last Updated', readonly=True)
    last_errors_count = fields.Integer(string='Last Errors', readonly=True)

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._sync_ir_cron()
        return record

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_cron_sync'):
            self._sync_ir_cron()
        return res

    def unlink(self):
        # Remove linked ir.cron when deleting
        for record in self:
            if record.ir_cron_id:
                record.ir_cron_id.sudo().unlink()
        return super().unlink()

    @api.constrains('interval_number')
    def _check_interval_number(self):
        for record in self:
            if record.interval_number <= 0:
                raise ValidationError(_('Interval must be greater than zero'))

    def _cron_display_name(self):
        self.ensure_one()
        base = 'FinditParts Sync'
        suffix = ''
        if self.sync_type == 'search':
            suffix = f"Search: {self.search_query or ''}"
        elif self.sync_type == 'part_number':
            suffix = f"PN: {self.part_number or ''}"
        else:
            suffix = f"All (limit {self.limit or 0})"
        return f"{base} - {suffix}"

    def _sync_ir_cron(self):
        """Create or update the linked ir.cron to run this record."""
        for record in self:
            cron_model = self.env['ir.cron']
            cron_fields = cron_model._fields

            cron_vals = {
                'name': record._cron_display_name(),
                'model_id': self.env['ir.model']._get('finditparts.sync.cron').id,
                'state': 'code',
                'code': f"model.browse({record.id}).sudo()._run_cron_job()",
                'interval_number': record.interval_number,
                'interval_type': record.interval_type,
                'active': record.active,
                'user_id': self.env.user.id,
                'nextcall': fields.Datetime.now(),
            }

            # Solo setear campos que existan en esta instancia
            if 'numbercall' in cron_fields:
                cron_vals['numbercall'] = -1
            elif 'max_number_of_calls' in cron_fields:
                cron_vals['max_number_of_calls'] = -1
            elif 'max_calls' in cron_fields:
                cron_vals['max_calls'] = -1

            if 'doall' in cron_fields:
                cron_vals['doall'] = False
            elif 'catchup' in cron_fields:
                cron_vals['catchup'] = False

            if 'cron_name' in cron_fields:
                cron_vals['cron_name'] = cron_vals['name']

            if record.ir_cron_id:
                record.ir_cron_id.sudo().write(cron_vals)
            else:
                cron = cron_model.sudo().create(cron_vals)
                record.ir_cron_id = cron.id

    def _get_sync_params(self):
        """Return params dict for sync_products_from_api based on type."""
        self.ensure_one()
        if self.sync_type == 'search':
            if not self.search_query:
                raise ValidationError(_('Search Query is required for search sync type'))
            return {'search_query': self.search_query, 'limit': self.limit}
        if self.sync_type == 'part_number':
            if not self.part_number:
                raise ValidationError(_('Part Number is required for part number sync type'))
            return {'part_number': self.part_number, 'limit': 1}
        # all products limited
        return {'limit': self.limit}

    def _run_cron_job(self):
        """Executed by ir.cron. Triggers the sync using stored parameters."""
        for record in self:
            if not record.active:
                continue
            try:
                params = record._get_sync_params()
                product_model = self.env['finditparts.product'].sudo()
                if record.config_id:
                    params['config'] = record.config_id
                result = product_model.sync_products_from_api(**params)
                errors_list = result.get('errors', []) or []
                created_count = result.get('created', 0)
                updated_count = result.get('updated', 0)
                status = 'success' if not errors_list else 'partial'
                record.with_context(skip_cron_sync=True).write({
                    'last_run': fields.Datetime.now(),
                    'last_status': status,
                    'last_created': created_count,
                    'last_updated': updated_count,
                    'last_errors_count': len(errors_list),
                    'last_result': _(
                        'Created: %(created)s | Updated: %(updated)s | Errors: %(errors)s'
                    ) % {
                        'created': created_count,
                        'updated': updated_count,
                        'errors': len(errors_list)
                    }
                })
                if result.get('errors'):
                    _logger.warning("FinditParts cron %s completed with errors: %s", record.id, result.get('errors', []))
            except Exception as e:
                record.with_context(skip_cron_sync=True).write({
                    'last_run': fields.Datetime.now(),
                    'last_status': 'failed',
                    'last_errors_count': 1,
                    'last_result': _('Failed: %s') % str(e),
                })
                _logger.error("FinditParts cron %s failed: %s", record.id, e)
                # Continue to next record without raising to avoid stopping the scheduler
                continue
