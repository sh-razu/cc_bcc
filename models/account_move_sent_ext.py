from odoo import models, api

class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _get_default_sending_settings(self, move, from_cron=False, **custom_settings):
        # Get default values from parent
        vals = super()._get_default_sending_settings(move, from_cron=from_cron, **custom_settings)

        # Custom setting getter
        def get_setting(key, from_cron=False, default_value=None):
            return custom_settings.get(key) if key in custom_settings else move.sending_data.get(key) if from_cron else default_value

        # Only inject if sending by email
        if 'email' in vals.get('sending_methods', {}):
            vals['cc_email_partner_ids'] = get_setting(
                'cc_email_partner_ids',
                default_value=[]
            )

        return vals
