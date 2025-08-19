from odoo import models, fields, api

class ValidatePickingEmailWizard(models.TransientModel):
    _name = 'validate.picking.email.wizard'
    _description = 'Wizard: capture CC for next validation email'

    picking_id = fields.Many2one('stock.picking', required=True, readonly=True)
    cc_partner_ids = fields.Many2many('res.partner', string='CC (Partners)')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        pid = self.env.context.get('default_picking_id')
        if not pid:
            return vals

        picking = self.env['stock.picking'].browse(int(pid))
        vals['picking_id'] = picking.id

        # RULE 1: settings override
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('cc_bcc.enable_custom_partner') in ('1', 'True', 'true', 'yes', 'y'):
            csv_ids = (ICP.get_param('cc_bcc.custom_partner_ids') or '').strip()
            cfg_ids = [int(x) for x in csv_ids.split(',') if x.strip().isdigit()] if csv_ids else []
            if cfg_ids:
                vals['cc_partner_ids'] = [(6, 0, list(set(cfg_ids)))]
                return vals

        # RULE 2: fallback — existing stored + responsible
        cc_ids = set(picking.next_cc_partner_ids.ids)

        if picking.user_id and picking.user_id.partner_id:
            cc_ids.add(picking.user_id.partner_id.id)

        vals['cc_partner_ids'] = [(6, 0, list(cc_ids))]

        return vals

    def action_save_cc(self):
        self.ensure_one()
        self.picking_id.write({
            'next_cc_partner_ids': [(6, 0, self.cc_partner_ids.ids)],
        })
        return {'type': 'ir.actions.act_window_close'}