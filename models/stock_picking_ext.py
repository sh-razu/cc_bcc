from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    next_cc_partner_ids = fields.Many2many(
        'res.partner', 'stock_picking_next_cc_partner_rel', 'picking_id', 'partner_id',
        string='CC Partners'
    )

    def action_open_validate_email_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add CC recipient(s) for Shipping Email',
            'res_model': 'validate.picking.email.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_id': self.id},
        }

    def _send_confirmation_email(self):
        subtype_id = self.env['ir.model.data']._xmlid_to_res_id('mail.mt_comment')
        for picking in self.filtered(
                lambda p: p.company_id.stock_move_email_validation and p.picking_type_id.code == 'outgoing'):
            template = picking.company_id.stock_mail_confirmation_template_id
            msg = picking.with_context(force_send=True).message_post_with_source(
                template,
                email_layout_xmlid='mail.mail_notification_light',
                subtype_id=subtype_id,
            )

            if msg and msg.mail_ids:
                cc_list = []
                if picking.next_cc_partner_ids:
                    cc_list += [p.email for p in picking.next_cc_partner_ids if p.email]
                if cc_list:
                    msg.mail_ids.write({'email_cc': ','.join(cc_list)})

        return True