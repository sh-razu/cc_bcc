from odoo import models, fields, api


class AccountMoveSendWizardExt(models.TransientModel):
    _inherit = 'account.move.send.wizard'

    cc_email_partner_ids = fields.Many2many('res.partner', 'cc_partners', string='CC Email', )
    bcc_email_partner_ids = fields.Many2many('res.partner', 'bcc_partners', string='CC Email', )

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
