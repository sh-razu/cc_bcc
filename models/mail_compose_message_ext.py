from odoo import fields, models, api
from odoo.exceptions import UserError

class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    cc_email_partner_ids = fields.Many2many('res.partner', 'mail_cc_partner_rel', string='CC Email Partners')
    bcc_email_partner_ids = fields.Many2many('res.partner', 'mail_bcc_partner_rel', string='BCC Email Partners')

    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        model = self._context.get('default_model')
        res_ids = self._context.get('default_res_ids') or self._context.get('default_res_id')
        if not model or not res_ids:
            return defaults

        res_ids = res_ids if isinstance(res_ids, list) else [res_ids]
        partner_ids = []

        if model in ['sale.order', 'purchase.order', 'account.move']:
            records = self.env[model].browse(res_ids)
            for record in records:
                if model == 'sale.order' and record.user_id and record.user_id.partner_id:
                    partner_ids.append(record.user_id.partner_id.id)
                elif model == 'purchase.order' and record.user_id and record.user_id.partner_id:
                    partner_ids.append(record.user_id.partner_id.id)

        if partner_ids:
            defaults['cc_email_partner_ids'] = [(6, 0, list(set(partner_ids)))]

        return defaults

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