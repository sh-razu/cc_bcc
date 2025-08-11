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
        partner_ids = []

        if order.user_id and order.user_id.partner_id:
            partner_ids.append(order.user_id.partner_id.id)

        if partner_ids:
            defaults['cc_email_partner_ids'] = [(6, 0, list(set(partner_ids)))]

        return defaults

    @api.depends('template_id', 'order_id')
    def _compute_recipient_ids(self):
        block_templates = {'Sales: Order Cancellation'}
        for wizard in self:
            if wizard.template_id and wizard.template_id.name in block_templates:
                wizard.recipient_ids = False
            else:
                super(SaleOrderCancel, wizard)._compute_recipient_ids()

    def action_send_mail_and_cancel(self):
        self.ensure_one()

        valid_to = self.recipient_ids.filtered(lambda p: p.email)
        if not valid_to:
            raise UserError("Please select at least one recipient with a valid email in the 'To' field before sending.")

        MailMessage = self.env['mail.message'].sudo()
        MailMail = self.env['mail.mail'].sudo()
        MailNotification = self.env['mail.notification'].sudo()

        # 1) chatter comment (white)
        msg_comment = MailMessage.create({
            'model': 'sale.order',
            'res_id': self.order_id.id,
            'subject': self.subject or f"Order {self.order_id.name} Cancelled",
            'body': self.body or '',
            'partner_ids': [(6, 0, valid_to.ids)],
            'author_id': self.author_id.id,
            'email_from': self.env.user.email_formatted,
            'message_type': 'comment',
            'subtype_id': self.env.ref('mail.mt_comment').id,
        })

        qweb = self.env['ir.qweb']
        wrapped = qweb._render('mail.mail_notification_light', {
            'body': msg_comment.body or '',
            'company': self.order_id.company_id,
            'record': self.order_id,
            'message': msg_comment,
            # ensure header text: “Your Sales Order”
            'model_description': getattr(self.order_id, '_description', 'Sales Order'),
        })
        body_html = wrapped.decode() if isinstance(wrapped, bytes) else wrapped

        mail = MailMail.create({
            'subject': msg_comment.subject,
            'email_from': msg_comment.email_from,
            'recipient_ids': [(4, pid) for pid in valid_to.ids],
            'auto_delete': True,
            'body_html': body_html,
        })
        mail.send()

        # 3) notifications → link to a separate “email” message, not the chatter comment
        msg_email = MailMessage.create({
            'subject': msg_comment.subject,
            'body': body_html,
            'email_from': msg_comment.email_from,
            'message_type': 'email',
        })
        MailNotification.create([{
            'res_partner_id': pid,
            'mail_message_id': msg_email.id,
            'mail_mail_id': mail.id,
            'notification_status': 'sent',
            'notification_type': 'email',
            'is_read': True,
            'author_id': self.author_id.id,
        } for pid in valid_to.ids])

        # 4) cancel order (state change)
        return self.action_cancel()