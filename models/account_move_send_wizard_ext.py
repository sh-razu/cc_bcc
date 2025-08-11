from odoo import models, fields, api, _
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

    @api.depends('mail_template_id', 'mail_lang')
    def _compute_mail_subject_body_partners(self):
        for wizard in self:
            if wizard.mail_template_id:
                wizard.mail_subject = self._get_default_mail_subject(
                    wizard.move_id, wizard.mail_template_id, wizard.mail_lang
                )
                # Raw template body in the editor; we’ll add header/footer at send time
                wizard.mail_body = self._get_default_mail_body(
                    wizard.move_id, wizard.mail_template_id, wizard.mail_lang
                )
                # Optional: block recipients for a specific template
                if wizard.mail_template_id.name in {'Invoice: Sending'}:
                    wizard.mail_partner_ids = False
            else:
                wizard.mail_subject = False
                wizard.mail_body = False
                wizard.mail_partner_ids = False

    def action_send_and_print(self, allow_fallback_pdf=False):
        self.ensure_one()

        if not self.mail_partner_ids:
            raise UserError(_("Please select at least one recipient in the 'To' field before sending."))

        move = self.move_id

        # Generate documents (same behavior as standard)
        custom_settings = self._get_sending_settings()
        self._check_sending_data(move, **custom_settings)
        moves_data = {move.sudo(): {**self._get_default_sending_settings(move, from_cron=False, **custom_settings)}}
        self._generate_invoice_documents(moves_data, allow_fallback_pdf=allow_fallback_pdf)
        errors = {m: md for m, md in moves_data.items() if md.get('error')}
        if allow_fallback_pdf and errors:
            self._generate_invoice_fallback_documents(errors)

        # Attachments from widget + manual
        manual = [x for x in (self.mail_attachments_widget or []) if x.get('manual')]
        widget = self._get_default_mail_attachments_widget(
            move,
            self.mail_template_id,
            extra_edis=self.extra_edis or {},
            pdf_report=self.pdf_report_id if (not self.pdf_report_id or self.pdf_report_id.exists()) else False,
        )
        widget += manual
        attachment_ids = []
        for item in widget:
            att_id = item.get('attachment_id') or item.get('id')
            if isinstance(att_id, int):
                attachment_ids.append(att_id)
            else:
                name = item.get('name') or str(att_id)
                existing = self.env['ir.attachment'].search([
                    ('name', '=', name),
                    ('res_model', '=', move._name),
                    ('res_id', '=', move.id),
                ], limit=1)
                if existing:
                    attachment_ids.append(existing.id)
        seen = set()
        attachment_ids = [x for x in attachment_ids if not (x in seen or seen.add(x))]

        # Recipients & CC/BCC
        recipient_links = [(4, pid) for pid in self.mail_partner_ids.ids]
        mail_cc = ','.join(filter(None, getattr(self, 'cc_email_partner_ids', self.env['res.partner']).mapped('email')))
        mail_bcc = ','.join(
            filter(None, getattr(self, 'bcc_email_partner_ids', self.env['res.partner']).mapped('email')))

        # Chatter message (RAW body; no banner in chatter)
        message = self.env['mail.message'].sudo().create({
            'model': move._name,
            'res_id': move.id,
            'message_type': 'email',
            'subject': self.mail_subject or '',
            'body': self.mail_body or '',
            'author_id': self.env.user.partner_id.id,
            'email_add_signature': False,  # avoid duplicate signature
        })

        # Ensure portal token so CTA can be generated
        if hasattr(move, '_portal_ensure_token'):
            move.sudo()._portal_ensure_token()

        # Model description
        model_description = getattr(self.env[move._name], '_description', move._name)
        if hasattr(move, '_get_model_description'):
            try:
                model_description = move._get_model_description(move._name)
            except Exception:
                pass

        # Recipient groups (CTA/button)
        base_msg_vals = {'partner_ids': self.mail_partner_ids.ids, 'model': move._name, 'res_id': move.id}
        try:
            rec_groups = move._notify_get_recipients_groups(message, model_description, msg_vals=base_msg_vals)
        except TypeError:
            try:
                rec_groups = move._notify_get_recipients_groups(message, msg_vals=base_msg_vals,
                                                                model_description=model_description)
            except TypeError:
                rec_groups = move._notify_get_recipients_groups(message)

        def _norm_group(g):
            if isinstance(g, dict):
                d = dict(g);
                d.setdefault('recipients', []);
                d.setdefault('has_button_access', d.get('has_button_access', False));
                return d
            if isinstance(g, tuple) and len(g) == 2:
                a, b = g
                if isinstance(a, dict):
                    d = dict(a);
                    d.setdefault('recipients', b if isinstance(b, (list, tuple)) else []);
                    d.setdefault('has_button_access', d.get('has_button_access', False));
                    return d
                if isinstance(b, dict):
                    d = dict(b);
                    d.setdefault('recipients', a if isinstance(a, (list, tuple)) else []);
                    d.setdefault('has_button_access', d.get('has_button_access', False));
                    return d
            return {'recipients': [], 'has_button_access': False}

        def _pid(r):
            if isinstance(r, int): return r
            if isinstance(r, dict): return r.get('id')
            return getattr(r, 'id', None)

        norm_groups = [_norm_group(g) for g in (rec_groups or [])]
        group = None
        dest_ids = set(self.mail_partner_ids.ids)
        for g in norm_groups:
            rec_ids = set(filter(None, (_pid(r) for r in g.get('recipients', []))))
            if dest_ids & rec_ids:
                group = g;
                break
        if not group:
            group = norm_groups[0] if norm_groups else {'recipients': [], 'has_button_access': False}

        # Fallback CTA to portal if needed
        try:
            if not group.get('has_button_access', False):
                portal_url = False
                if hasattr(move, 'get_portal_url'):
                    portal_url = move.get_portal_url()
                elif getattr(move, 'access_token', False):
                    portal_url = f"/my/{move._name.replace('.', '/')}/{move.id}?access_token={move.access_token}"
                if portal_url:
                    base_url = move.get_base_url() if hasattr(move, 'get_base_url') else self.env[
                        'ir.config_parameter'].sudo().get_param('web.base.url')
                    label = _("View Invoice") if getattr(move, 'move_type', '') in ('out_invoice', 'out_refund') else _(
                        "View Bill")
                    group['has_button_access'] = True
                    group['button_access'] = {'title': label, 'url': f"{base_url}{portal_url}", 'style': 'primary'}
        except Exception:
            pass

        # ---------- Build header lines ----------
        partner_name = move.partner_id.name or ''
        record_title = f"{move.name} - {partner_name}" if partner_name else (move.name or move.display_name)

        amount_due_line = ''
        try:
            from odoo.tools.misc import format_amount, format_date
            amount_label = format_amount(self.env, getattr(move, 'amount_total', 0.0), move.currency_id) if getattr(
                move, 'currency_id', False) else ''
            due_label = format_date(self.env, move.invoice_date_due) if getattr(move, 'invoice_date_due', False) else ''
            if amount_label and due_label:
                amount_due_line = f"{amount_label} " + _("due %s") % due_label
            elif amount_label:
                amount_due_line = amount_label
        except Exception:
            symbol = getattr(getattr(move, 'currency_id', False), 'symbol', '') or ''
            amt = getattr(move, 'amount_total', 0.0) or 0.0
            amount_due_line = f"{symbol} {amt:,.2f}"
            if getattr(move, 'invoice_date_due', False):
                amount_due_line += " " + _("due %s") % move.invoice_date_due.strftime('%Y-%m-%d')

        # ---------- Prepare rendering context using our title ----------
        render_values = move._notify_by_email_prepare_rendering_context(
            message,
            msg_vals={'model': move._name, 'record_name': record_title},  # <-- critical
            model_description=model_description,
        )
        # Force both lines to appear even if the layout ignores record_name:
        render_values['record_name'] = record_title
        render_values['subtitles'] = [record_title, amount_due_line] if amount_due_line else [record_title]
        render_values.update({
            'body': self.mail_body or '',
            'email_notification_force_header': True,
            'email_notification_allow_footer': True,
        })

        # Render final HTML (banner+button+footer) for the OUTGOING EMAIL ONLY
        final_body = move._notify_by_email_render_layout(
            message,
            group,
            msg_vals={'email_layout_xmlid': getattr(message, 'email_layout_xmlid', False)},
            render_values=render_values,
        ) or (self.mail_body or '')

        # Do NOT write final_body back to chatter (keep chatter clean)
        # message.write({'body': final_body})

        # Create & send email (with banner)
        mail_vals = {
            'mail_message_id': message.id,
            'subject': self.mail_subject or '',
            'body_html': final_body,
            'email_from': self.env.user.email_formatted,
            'recipient_ids': recipient_links,
            'attachment_ids': [(4, a) for a in attachment_ids],
            'model': move._name,
            'res_id': move.id,
        }
        if mail_cc:
            mail_vals['email_cc'] = mail_cc
        if mail_bcc:
            mail_vals['email_bcc'] = mail_bcc

        mail = self.env['mail.mail'].sudo().create(mail_vals)
        mail.send()

        # Notifications
        self.env['mail.notification'].sudo().create([{
            'res_partner_id': pid,
            'mail_message_id': message.id,
            'mail_mail_id': mail.id,
            'notification_status': 'sent',
            'notification_type': 'email',
            'is_read': True,
            'author_id': self.env.user.partner_id.id,
        } for pid in self.mail_partner_ids.ids])

        return {'type': 'ir.actions.act_window_close'}

