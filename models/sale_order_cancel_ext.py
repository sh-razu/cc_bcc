from odoo import fields, models, api
from odoo.exceptions import UserError

class SaleOrderCancel(models.TransientModel):
    _inherit = 'sale.order.cancel'

    cc_email_partner_ids = fields.Many2many('res.partner', 'sale_cancel_cc_partner_rel', string='CC Recipients')
    bcc_email_partner_ids = fields.Many2many('res.partner', 'sale_cancel_bcc_partner_rel', string='BCC Recipients')
    recipient_ids = fields.Many2many(
        'res.partner',
        string="Recipients",
        compute='_compute_recipient_ids',
        store=True,
        readonly=False,
    )

    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        order_id = self._context.get('default_order_id')
        if not order_id:
            return defaults

        order = self.env['sale.order'].browse(order_id)

        # RULE 1: settings override
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('cc_bcc.enable_custom_partner') in ('1', 'True', 'true', 'yes', 'y'):
            csv_ids = (ICP.get_param('cc_bcc.custom_partner_ids') or '').strip()
            cfg_ids = [int(x) for x in csv_ids.split(',') if x.strip().isdigit()] if csv_ids else []
            if cfg_ids:
                defaults['cc_email_partner_ids'] = [(6, 0, list(set(cfg_ids)))]
                return defaults

        # RULE 2: fallback — responsible (salesperson)
        partner_ids = []

        if order.user_id and order.user_id.partner_id:
            partner_ids.append(order.user_id.partner_id.id)

        if partner_ids:
            defaults['cc_email_partner_ids'] = [(6, 0, list(set(partner_ids)))]

        return defaults