from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountMoveSendWizardExt(models.TransientModel):
    _inherit = 'account.move.send.wizard'

    cc_email_partner_ids = fields.Many2many('res.partner', 'cc_partners', string='CC Email', )
    bcc_email_partner_ids = fields.Many2many('res.partner', 'bcc_partners', string='BCC Email', )

    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        res_ids = (self._context.get('default_res_ids') or self._context.get('default_move_ids') or self._context.get('active_ids'))

        if not res_ids:
            return defaults

        res_ids = res_ids if isinstance(res_ids, list) else [res_ids]

        # RULE 1: settings override (if enabled and has partners)
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('cc_bcc.enable_custom_partner') in ('1', 'True', 'true', 'yes', 'y'):
            csv_ids = (ICP.get_param('cc_bcc.custom_partner_ids') or '').strip()
            cfg_ids = [int(x) for x in csv_ids.split(',') if x.strip().isdigit()] if csv_ids else []
            if cfg_ids:
                defaults['cc_email_partner_ids'] = [(6, 0, list(set(cfg_ids)))]
                return defaults

        # RULE 2: fallback — responsible (invoice user’s partner)
        partner_ids = []

        for move in self.env['account.move'].browse(res_ids):
            if move.invoice_user_id and move.invoice_user_id.partner_id:
                partner_ids.append(move.invoice_user_id.partner_id.id)

        if partner_ids:
            defaults['cc_email_partner_ids'] = [(6, 0, list(set(partner_ids)))]

        return defaults

    def _get_sending_settings(self):
        settings = super()._get_sending_settings()
        settings['cc_email_partner_ids'] = self.cc_email_partner_ids.ids if self.cc_email_partner_ids else []
        settings['bcc_email_partner_ids'] = self.bcc_email_partner_ids.ids if self.bcc_email_partner_ids else []

        return settings

    @api.model
    def _get_mail_params(self, move, move_data):
        # Call the base implementation
        params = super()._get_mail_params(move, move_data)

        # Inject CC emails if provided
        partner_ids = move_data.get('cc_email_partner_ids', [])
        if partner_ids:
            partners = self.env['res.partner'].browse(partner_ids)
            emails = [p.email for p in partners if p.email]
            if emails:
                params['email_cc'] = ','.join(emails)

        return params