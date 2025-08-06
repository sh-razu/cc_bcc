from odoo import fields, models

class SaleOrderCancel(models.TransientModel):
    _inherit = 'sale.order.cancel'

    cc_email_partner_ids = fields.Many2many('res.partner', 'sale_cancel_cc_partner_rel', string='CC Recipients')
    bcc_email_partner_ids = fields.Many2many('res.partner', 'sale_cancel_bcc_partner_rel', string='BCC Recipients')

    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        order_id = self._context.get('default_order_id')
        if not order_id:
            return defaults

        order = self.env['sale.order'].browse(order_id)
        partner_ids = []

        if order.user_id and order.user_id.partner_id:
            partner_ids.append(order.user_id.partner_id.id)

        if partner_ids:
            defaults['cc_email_partner_ids'] = [(6, 0, list(set(partner_ids)))]

        return defaults

    def action_send_mail_and_cancel(self):
        self.ensure_one()

        cc_emails = [p.email for p in self.cc_email_partner_ids if p.email]
        bcc_emails = [p.email for p in self.bcc_email_partner_ids if p.email]

        post_kwargs = {
            'author_id': self.author_id.id,
            'body': self.body,
            'message_type': 'comment',
            'email_layout_xmlid': 'mail.mail_notification_light',
            'partner_ids': self.recipient_ids.ids,
            'subject': self.subject,
        }

        if cc_emails:
            post_kwargs['email_cc'] = cc_emails
        if bcc_emails:
            post_kwargs['email_bcc'] = bcc_emails

        self.order_id.message_post(**post_kwargs)
        return self.action_cancel()