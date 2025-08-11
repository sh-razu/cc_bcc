from odoo import fields, models, api

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
        self.ensure_one()

        MailMessage = self.env['mail.message'].sudo()
        MailMail = self.env['mail.mail'].sudo()
        MailNotification = self.env['mail.notification'].sudo()

        result_messages = self.env['mail.message']

        # helpers
        def _normalize_group(g):
            if isinstance(g, dict):
                data = dict(g)
                data.setdefault('recipients', [])
                data.setdefault('has_button_access', data.get('has_button_access', False))
                return data
            if isinstance(g, tuple) and len(g) == 2:
                a, b = g
                if isinstance(a, dict):
                    d = dict(a); d.setdefault('recipients', b if isinstance(b, (list, tuple)) else [])
                    d.setdefault('has_button_access', d.get('has_button_access', False)); return d
                if isinstance(b, dict):
                    d = dict(b); d.setdefault('recipients', a if isinstance(a, (list, tuple)) else [])
                    d.setdefault('has_button_access', d.get('has_button_access', False)); return d
            return {'recipients': [], 'has_button_access': False}

        def _partner_id_from_recipient(rec):
            if isinstance(rec, dict):
                return rec.get('id')
            if isinstance(rec, int):
                return rec
            return getattr(rec, 'id', None)

        def _strip_html(text):
            import re
            return re.sub(r'<[^>]*>', '', text or '').strip()

        for res_id in res_ids:
            # 1) Prefer UI edits; template only fills blanks
            rendered_subject = self.subject or ''
            rendered_body = self.body or ''

            if self.template_id:
                if not rendered_subject:
                    try:
                        sub_map = self.template_id._render_field('subject', [res_id], compute_lang=True)
                        rendered_subject = (sub_map or {}).get(res_id) or rendered_subject
                    except Exception:
                        pass
                if not rendered_body:
                    try:
                        body_map = self.template_id._render_field('body_html', [res_id], compute_lang=True)
                        rendered_body = (body_map or {}).get(res_id) or rendered_body
                    except Exception:
                        pass

            # avoid double signature
            author_partner = self.author_id or self.env.user.partner_id
            author_user = self.env.user if author_partner == self.env.user.partner_id else (
                author_partner.user_ids[:1] if author_partner.user_ids else self.env.user)
            author_signature = _strip_html(getattr(author_user, 'signature', '') or '')
            has_sig_in_body = bool(author_signature and author_signature in _strip_html(rendered_body))

            # 2) Create the message with exactly the edited body
            message = MailMessage.create({
                'model': self.model,
                'res_id': res_id,
                'subject': rendered_subject,
                'body': rendered_body,  # <- UI body verbatim
                'partner_ids': [(6, 0, self.partner_ids.ids)],
                'author_id': self.author_id.id,
                'email_from': self.email_from,
                'message_type': 'comment',
                'subtype_id': self.subtype_id.id if self.subtype_id else self.env.ref('mail.mt_comment').id,
                'email_add_signature': False if has_sig_in_body else True,
            })

            result_messages |= message

            # ----- Standard layout + CTA -----
            record = self.env[self.model].browse(res_id)

            # Ensure portal token so CTA/URL can be generated
            if hasattr(record, '_portal_ensure_token'):
                record.sudo()._portal_ensure_token()

            # model description
            if hasattr(record, '_get_model_description'):
                try:
                    model_description = record._get_model_description(self.model)
                except Exception:
                    model_description = getattr(self.env[self.model], '_description', False) or self.model
            else:
                model_description = getattr(self.env[self.model], '_description', False) or self.model

            # recipient groups (CTA source)
            base_msg_vals = {'partner_ids': self.partner_ids.ids, 'model': self.model, 'res_id': res_id}
            try:
                recipients_groups = record._notify_get_recipients_groups(message, model_description, msg_vals=base_msg_vals)
            except TypeError:
                try:
                    recipients_groups = record._notify_get_recipients_groups(message, msg_vals=base_msg_vals, model_description=model_description)
                except TypeError:
                    recipients_groups = record._notify_get_recipients_groups(message)

            norm_groups = [_normalize_group(g) for g in (recipients_groups or [])]
            partner_set = set(self.partner_ids.ids)
            group = None
            for g in norm_groups:
                rec_ids = set(filter(None, (_partner_id_from_recipient(r) for r in g.get('recipients', []))))
                if partner_set & rec_ids:
                    group = g
                    break
            if not group:
                group = norm_groups[0] if norm_groups else {'recipients': [], 'has_button_access': False}

            # Fallback CTA
            try:
                if not group.get('has_button_access', False):
                    if hasattr(record, '_portal_ensure_token'):
                        record.sudo()._portal_ensure_token()
                    portal_url = False
                    if hasattr(record, 'get_portal_url'):
                        portal_url = record.get_portal_url()
                    elif hasattr(record, 'access_token') and getattr(record, 'access_token'):
                        portal_url = f"/my/{record._name.replace('.', '/')}/{record.id}?access_token={record.access_token}"
                    if portal_url:
                        base_url = record.get_base_url() if hasattr(record, 'get_base_url') else self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                        label = "View Document"
                        name = record._name
                        if name == 'sale.order':
                            require_sig = bool(getattr(record, 'require_signature', False) or getattr(record, 'requires_signature', False))
                            require_pay = bool(getattr(record, 'require_payment', False) or getattr(record, 'requires_payment', False))
                            label = "Sign & Pay Quotation" if (require_sig or require_pay) else ("View Quotation" if getattr(record, 'state', '') in ('draft', 'sent') else "View Order")
                        elif name == 'account.move':
                            label = "View Invoice" if getattr(record, 'move_type', '') in ('out_invoice', 'out_refund') else "View Bill"
                        elif name == 'purchase.order':
                            label = "View Order"
                        group['has_button_access'] = True
                        group['button_access'] = {'title': label, 'url': f"{base_url}{portal_url}", 'style': 'primary'}
            except Exception:
                pass

            # render context
            render_values = record._notify_by_email_prepare_rendering_context(
                message,
                msg_vals={'model': self.model, 'record_name': record.display_name},
                model_description=model_description,
            )

            # subtitles
            template_name = (self.template_id.name or '') if self.template_id else ''
            subtitles = [record.display_name]

            amount_label = False
            date_label = False
            try:
                from odoo.tools.misc import format_amount, format_date
            except Exception:
                from odoo.tools.misc import format_amount
                format_date = None

            # amount if available
            try:
                if hasattr(record, 'amount_total') and getattr(record, 'currency_id', False):
                    amount_label = format_amount(self.env, record.amount_total, record.currency_id)
                elif hasattr(record, 'amount_untaxed') and getattr(record, 'currency_id', False):
                    amount_label = format_amount(self.env, record.amount_untaxed, record.currency_id)
            except Exception:
                if hasattr(record, 'currency_id') and getattr(record, 'amount_total', False) is not False:
                    symbol = getattr(record.currency_id, 'symbol', '') or ''
                    amount_label = f"{symbol} {record.amount_total}"

            # RFQ (Purchase: Request For Quotation) -> "Order due {date}"
            if template_name == 'Purchase: Request For Quotation':
                the_date = getattr(record, 'date_order', False) or getattr(record, 'date', False)
                if the_date:
                    try:
                        if format_date:
                            date_label = "Order due %s" % format_date(self.env, the_date)
                        else:
                            date_label = "Order due %s" % fields.Date.to_string(the_date)
                    except Exception:
                        date_label = "Order due %s" % fields.Date.to_string(the_date)

            if template_name in ('Sales: Send Quotation', 'Purchase: Purchase Order'):
                if amount_label:
                    subtitles.append(amount_label)
            elif template_name == 'Purchase: Request For Quotation':
                if date_label:
                    subtitles.append(date_label)
            else:
                if amount_label:
                    subtitles.append(amount_label)

            render_values['subtitles'] = subtitles

            # force header/footer; keep the exact edited body
            render_values.update({
                'body': message.body,
                'email_notification_force_header': True,
                'email_notification_allow_footer': True,
            })

            # render layout
            mail_body = record._notify_by_email_render_layout(
                message,
                group,
                msg_vals={'email_layout_xmlid': getattr(message, 'email_layout_xmlid', False)},
                render_values=render_values
            )

            email_body_html = mail_body or message.body

            # 3) mail.mail with CC/BCC
            recipient_links = [(4, pid) for pid in self.partner_ids.ids]
            att_ids = []
            if self.attachment_ids:
                self.attachment_ids.sudo().write({'res_model': 'mail.message', 'res_id': message.id})
                att_ids = self.attachment_ids.ids

            mail_values = {
                'mail_message_id': message.id,
                'subject': rendered_subject,
                'body_html': email_body_html,
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

            # 4) notifications
            MailNotification.create([{
                'res_partner_id': pid,
                'mail_message_id': message.id,
                'mail_mail_id': mail.id,
                'notification_status': 'sent',
                'notification_type': 'email',
                'is_read': True,
                'author_id': self.author_id.id,
            } for pid in self.partner_ids.ids])

            # 5) post-send state updates (non-blocking)
            try:
                if self.model == 'sale.order':
                    so = record.sudo()
                    if getattr(so, 'state', False) == 'draft':
                        so.write({'state': 'sent'})
                elif self.model == 'purchase.order':
                    po = record.sudo()
                    if getattr(po, 'state', False) == 'draft':
                        po.write({'state': 'sent'})
            except Exception:
                pass

        return result_messages