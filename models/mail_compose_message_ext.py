from odoo import fields, models, api
from odoo.tools.mail import email_normalize

class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    cc_email_partner_ids = fields.Many2many('res.partner', 'mail_cc_partner_rel', string='CC Email Partners')
    bcc_email_partner_ids = fields.Many2many('res.partner', 'mail_bcc_partner_rel', string='BCC Email Partners')

    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        # Cc logic from here
        model = self._context.get('default_model')
        res_ids = self._context.get('default_res_ids') or self._context.get('default_res_id')
        if not model or not res_ids:
            return defaults

        res_ids = res_ids if isinstance(res_ids, list) else [res_ids]

        # RULE 1: settings override first
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('cc_bcc.enable_custom_partner') in ('1', 'True', 'true', 'yes', 'y'):
            csv_ids = (ICP.get_param('cc_bcc.custom_partner_ids') or '').strip()
            cfg_ids = [int(x) for x in csv_ids.split(',') if x.strip().isdigit()] if csv_ids else []
            if cfg_ids:
                defaults['cc_email_partner_ids'] = [(6, 0, list(set(cfg_ids)))]
                return defaults

        # RULE 2: fallback — responsible (salesperson/buyer)
        partner_ids = []

        if model in ['sale.order', 'purchase.order']:
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