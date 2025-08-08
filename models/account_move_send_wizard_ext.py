from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountMoveSendWizardExt(models.TransientModel):
    _inherit = 'account.move.send.wizard'

    cc_email_partner_ids = fields.Many2many('res.partner', 'cc_partners', string='CC Email', )
    bcc_email_partner_ids = fields.Many2many('res.partner', 'bcc_partners', string='CC Email', )

    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        res_ids = (self._context.get('default_res_ids') or self._context.get('default_move_ids') or self._context.get('active_ids'))

        if not res_ids:
            return defaults

        res_ids = res_ids if isinstance(res_ids, list) else [res_ids]
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

    def action_send_and_print(self, allow_fallback_pdf=False):
        self.ensure_one()

        if not self.mail_partner_ids:
            raise UserError("Please select at least one recipient in the 'To' field before sending.")

        recipient_links = [(4, pid) for pid in self.mail_partner_ids.ids]
        mail_cc = ','.join(filter(None, self.cc_email_partner_ids.mapped('email')))

        mail = self.env['mail.mail'].create({
            'subject': self.mail_subject,
            'body_html': self.mail_body,
            'email_from': self.env.user.email_formatted,
            'recipient_ids': recipient_links,
            'auto_delete': True,
            **({'email_cc': mail_cc} if mail_cc else {}),
        })

        mail.send()
        return {'type': 'ir.actions.act_window_close'}

    @api.depends('mail_template_id', 'mail_lang')
    def _compute_mail_subject_body_partners(self):
        for wizard in self:
            if wizard.mail_template_id:
                # Get values as usual
                wizard.mail_subject = self._get_default_mail_subject(wizard.move_id, wizard.mail_template_id, wizard.mail_lang)
                wizard.mail_body = self._get_default_mail_body(wizard.move_id, wizard.mail_template_id, wizard.mail_lang)

                block_templates = {'Invoice: Sending'}
                if wizard.mail_template_id.name in block_templates:
                    wizard.mail_partner_ids = False