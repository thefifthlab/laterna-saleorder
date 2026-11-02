from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    my_api_base_url = fields.Char(
        string="API Base URL",
        config_parameter='my_integration.api_base_url'
    )
    my_api_token = fields.Char(
        string="API Token",
        config_parameter='my_integration.api_token'
    )