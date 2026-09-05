from odoo import models, fields

class UniversalDataCompareConfig(models.Model):
    _name = 'data_compare_config'
    _description = 'Universal Data Compare Config'
    _inherit = ['mail.thread','mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Name', required=True, tracking=True)
    model = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade', tracking=True)
    model_name = fields.Char(string='Model Name', related='model.model')
    filter_domain = fields.Text(string='Filter Domain', default='[]', tracking=True)
    primary_excel_column = fields.Char(string='Primary Excel Column', required=True, tracking=True)
    primary_key = fields.Many2one('ir.model.fields', string='Primary Key', domain="[('model_id', '=', model)]", required=True, ondelete='cascade', tracking=True)
    unpivot = fields.Boolean(string='Unpivot', default=False, tracking=True)
    unpivot_field = fields.Many2one('ir.model.fields', string='Unpivot Field', domain="[('model_id', '=', model)]", ondelete='cascade', tracking=True)
    informational_excel_column = fields.Char(string='Informational Excel Column', required=True, tracking=True)
    field_mapping_ids = fields.One2many('data_compare_config_field_mapping', 'config_id', string='Field Mapping', required=True, copy=True, tracking=True)
    rounding_tolerance = fields.Float(string='Rounding Tolerance', default=0.0, tracking=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)

class UniversalDataCompareConfigFieldMapping(models.Model):
    _name = 'data_compare_config_field_mapping'
    _description = 'Universal Data Compare Config Field Mapping'

    config_id = fields.Many2one('data_compare_config', string='Config', required=True)
    model_id = fields.Many2one(
        'ir.model',
        related='config_id.model'
    )
    excel_column = fields.Char(string='Excel Column', required=True, tracking=True)
    field_id = fields.Many2one('ir.model.fields', string='Field', domain="[('model_id', '=', model_id)]", required=True, ondelete='cascade', tracking=True)
    unpivot_value = fields.Char(string='Unpivot Value', tracking=True)
    

    
    
    
    
