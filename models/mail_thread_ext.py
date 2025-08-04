from odoo import models, api, Command
from odoo.tools import split_every, clean_context
import threading


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.model
    def _get_notify_valid_parameters(self):
        # Call super to get the base set
        params = super()._get_notify_valid_parameters()

        # Add email_cc (and email_bcc if you plan to use it)
        params.update({'email_cc'})  # or {'email_cc', 'email_bcc'}

        return params

    def _notify_thread_by_email(self, message, recipients_data, msg_vals=False,
                                mail_auto_delete=True,  # mail.mail
                                model_description=False, force_email_company=False, force_email_lang=False,  # rendering
                                subtitles=None,  # rendering
                                resend_existing=False, force_send=True, send_after_commit=True,  # email send
                                **kwargs):
        partners_data = [r for r in recipients_data if r['notif'] == 'email']
        if not partners_data:
            return True
        additional_values = {'auto_delete': mail_auto_delete}
        if 'email_cc' in kwargs:
            additional_values['email_cc'] = kwargs['email_cc']

        base_mail_values = self._notify_by_email_get_base_mail_values(
            message,
            additional_values
        )
        SafeMail = self.env['mail.mail'].sudo().with_context(clean_context(self._context))
        SafeNotification = self.env['mail.notification'].sudo().with_context(clean_context(self._context))
        emails = self.env['mail.mail'].sudo()

        # loop on groups (customer, portal, user,  ... + model specific like group_sale_salesman)
        gen_batch_size = int(
            self.env['ir.config_parameter'].sudo().get_param('mail.batch_size')
        ) or 50  # be sure to not have 0, as otherwise no iteration is done
        notif_create_values = []
        for _lang, render_values, recipients_group in self._notify_get_classified_recipients_iterator(
                message,
                partners_data,
                msg_vals=msg_vals,
                model_description=model_description,
                force_email_company=force_email_company,
                force_email_lang=force_email_lang,
                subtitles=subtitles,
        ):
            # generate notification email content
            mail_body = self._notify_by_email_render_layout(
                message,
                recipients_group,
                msg_vals=msg_vals,
                render_values=render_values,
            )
            recipients_ids = recipients_group.pop('recipients')

            # create email
            for recipients_ids_chunk in split_every(gen_batch_size, recipients_ids):
                mail_values = self._notify_by_email_get_final_mail_values(
                    recipients_ids_chunk,
                    base_mail_values,
                    additional_values={'body_html': mail_body}
                )
                new_email = SafeMail.create(mail_values)

                if new_email and recipients_ids_chunk:
                    tocreate_recipient_ids = list(recipients_ids_chunk)
                    if resend_existing:
                        existing_notifications = self.env['mail.notification'].sudo().search([
                            ('mail_message_id', '=', message.id),
                            ('notification_type', '=', 'email'),
                            ('res_partner_id', 'in', tocreate_recipient_ids)
                        ])
                        if existing_notifications:
                            tocreate_recipient_ids = [rid for rid in recipients_ids_chunk if
                                                      rid not in existing_notifications.mapped('res_partner_id.id')]
                            existing_notifications.write({
                                'notification_status': 'ready',
                                'mail_mail_id': new_email.id,
                            })
                    notif_create_values += [{
                        'author_id': message.author_id.id,
                        'is_read': True,  # discard Inbox notification
                        'mail_mail_id': new_email.id,
                        'mail_message_id': message.id,
                        'notification_status': 'ready',
                        'notification_type': 'email',
                        'res_partner_id': recipient_id,
                    } for recipient_id in tocreate_recipient_ids]
                emails += new_email

        if notif_create_values:
            SafeNotification.create(notif_create_values)

        # NOTE:
        #   1. for more than 50 followers, use the queue system
        #   2. do not send emails immediately if the registry is not loaded,
        #      to prevent sending email during a simple update of the database
        #      using the command-line.
        test_mode = getattr(threading.current_thread(), 'testing', False)
        if force_send := self.env.context.get('mail_notify_force_send', force_send):
            force_send_limit = int(self.env['ir.config_parameter'].sudo().get_param('mail.mail.force.send.limit', 100))
            force_send = len(emails) < force_send_limit
        if force_send and (not self.pool._init or test_mode):
            # unless asked specifically, send emails after the transaction to
            # avoid side effects due to emails being sent while the transaction fails
            if not test_mode and send_after_commit:
                emails.send_after_commit()
            else:
                emails.send()

        return True

    def _notify_by_email_get_final_mail_values(self, recipient_ids, mail_values,
                                               additional_values=None):
        """ Perform final formatting of values to create notification emails.
        Basic method just set the recipient partners as mail_mail recipients.
        Override to generate other mail values like email_to or email_cc.

        :param list recipient_ids: res.partner IDs to notify;
        :param dict mail_values: notification mail values;
        :param dict additional_values: optional additional values to add (ease
          custom calls and inheritance);

        :return: a new dictionary of values suitable for a <mail.mail> create;
        """
        final_mail_values = dict(mail_values)
        final_mail_values['recipient_ids'] = [Command.link(pid) for pid in recipient_ids]
        if additional_values and 'email_cc' in additional_values:
            final_mail_values['email_cc'] = additional_values['email_cc']
        if additional_values:
            final_mail_values.update(additional_values)
        return final_mail_values

