{
    'name': 'CC and BCC in Emails',
    'version': '18.0',
    'category': 'Accounting',
    'summary': 'Add CC and BCC fields to email sending wizard',
    'description': 'This module extends the email sending wizard to include CC and BCC fields for email addresses.',
    'author': 'Your Name',
    'website': 'https://www.example.com',
    'depends': ['account', 'sale', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/inherited_account_move_send_wizard_form.xml',
        'views/inherited_mail_compose_message_form.xml',
        'views/inherited_sale_order_cancel_form.xml',
        'views/validate_picking_email_wizard.xml',
        'views/inherited_stock_picking_view.xml',
        'views/inherited_res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',

}
