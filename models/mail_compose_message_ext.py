from odoo import fields, models

class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    cc_email_partner_ids = fields.Many2many('res.partner', 'mail_cc_partner_rel', string='CC Email Partners')
    bcc_email_partner_ids = fields.Many2many('res.partner', 'mail_bcc_partner_rel', string='BCC Email Partners')

    def _prepare_mail_values_rendered(self, res_ids):
        mail_values = super()._prepare_mail_values_rendered(res_ids)

        for res_id in res_ids:
            if self.cc_email_partner_ids:
                cc_emails = [p.email for p in self.cc_email_partner_ids if p.email]
                if cc_emails:
                    mail_values[res_id]['email_cc'] = ','.join(cc_emails)

            if self.bcc_email_partner_ids:
                bcc_email = [p.email for p in self.bcc_email_partner_ids if p.email]
                if bcc_email:
                    mail_values[res_id]['email_bcc'] = ','.join(bcc_email)

        return mail_values