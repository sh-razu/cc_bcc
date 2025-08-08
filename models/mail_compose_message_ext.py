from odoo import fields, models, api
from odoo.exceptions import UserError

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

    @api.depends('composition_mode', 'model', 'parent_id', 'res_domain', 'res_ids', 'template_id')
    def _compute_partner_ids(self):
        block_templates = {
            'Sales: Send Quotation',
            'Purchase: Request For Quotation',
            'Purchase: Purchase Order',
        }
        for wizard in self:
            if wizard.template_id and wizard.template_id.name in block_templates:
                wizard.partner_ids = False
            else:
                super(MailComposer, wizard)._compute_partner_ids()

    def _action_send_mail_comment(self, res_ids):
        """Bypass Odoo’s recipient logic completely, return mail.message recordset."""
        self.ensure_one()

        if not self.partner_ids:
            raise UserError("Please select at least one recipient in the 'To' field before sending.")

        MailMessage = self.env['mail.message'].sudo()
        MailMail = self.env['mail.mail'].sudo()
        MailNotification = self.env['mail.notification'].sudo()

        result_messages = self.env['mail.message']

        for res_id in res_ids:
            # 1. Create mail.message (no CC/BCC here)
            message = MailMessage.create({
                'model': self.model,
                'res_id': res_id,
                'subject': self.subject,
                'body': self.body,
                'partner_ids': [(6, 0, self.partner_ids.ids)],
                'author_id': self.author_id.id,
                'email_from': self.email_from,
                'message_type': 'comment',
                'subtype_id': self.subtype_id.id if self.subtype_id else self.env.ref('mail.mt_comment').id,
            })

            result_messages |= message

            # 2. Create mail.mail with CC/BCC
            recipient_links = [(4, pid) for pid in self.partner_ids.ids]

            att_ids = []
            if self.attachment_ids:
                self.attachment_ids.sudo().write({'res_model': 'mail.message', 'res_id': message.id})
                att_ids = self.attachment_ids.ids

            mail_values = {
                'mail_message_id': message.id,
                'subject': self.subject,
                'body_html': self.body,
                'email_from': self.email_from,
                'recipient_ids': recipient_links,
                'attachment_ids': [(4, a) for a in att_ids],
            }

            if self.cc_email_partner_ids:
                cc_emails = [p.email for p in self.cc_email_partner_ids if p.email]
                if cc_emails:
                    mail_values['email_cc'] = ','.join(cc_emails)

            if self.bcc_email_partner_ids:
                bcc_emails = [p.email for p in self.bcc_email_partner_ids if p.email]
                if bcc_emails:
                    mail_values['email_bcc'] = ','.join(bcc_emails)

            mail = MailMail.create(mail_values)
            mail.send()

            # 3. Create mail.notification manually
            MailNotification.create([{
                'res_partner_id': pid,
                'mail_message_id': message.id,
                'mail_mail_id': mail.id,
                'notification_status': 'sent',
                'notification_type': 'email',
                'is_read': True,
                'author_id': self.author_id.id,
            } for pid in self.partner_ids.ids])

        return result_messages