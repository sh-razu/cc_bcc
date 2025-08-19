from odoo import models, fields, api


_PARAM_ENABLE = 'cc_bcc.enable_custom_partner'
_PARAM_RECIPIENTS = 'cc_bcc.custom_partner_ids'

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_custom_partner = fields.Boolean(
        string="Enable Custom Partner",
        config_parameter=_PARAM_ENABLE
    )

    custom_partner_ids = fields.Many2many(
        'res.partner',
        string="Custom CC Partners",
        domain=[('email', '!=', False)],
        compute='_compute_default_cc_partner_ids',
        inverse='_inverse_default_cc_partner_ids',
        store=False,
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        param = self.env['ir.config_parameter'].sudo().get_param('cc_bcc.custom_partner_ids', default='')
        partner_ids = [int(pid) for pid in param.split(',') if pid]
        res.update({
            'custom_partner_ids': [(6, 0, partner_ids)],
        })
        return res

    def set_values(self):
        super().set_values()
        config = self.env['ir.config_parameter'].sudo()

        if self.enable_custom_partner:
            partner_ids_str = ','.join(map(str, self.custom_partner_ids.ids))
        else:
            partner_ids_str = ''

        config.set_param('cc_bcc.custom_partner_ids', partner_ids_str)

    @api.model
    def _get_cc_ids_from_param(self):
        csv_ids = (self.env['ir.config_parameter'].sudo().get_param(_PARAM_RECIPIENTS) or '').strip()
        return [int(x) for x in csv_ids.split(',') if x.strip().isdigit()] if csv_ids else []

    def _compute_default_cc_partner_ids(self):
        ids_ = self._get_cc_ids_from_param()
        for rec in self:
            rec.custom_partner_ids = [(6, 0, ids_)]

    def _inverse_default_cc_partner_ids(self):
        ICP = self.env['ir.config_parameter'].sudo()
        for rec in self:
            ICP.set_param(_PARAM_RECIPIENTS, ','.join(str(i) for i in rec.custom_partner_ids.ids))