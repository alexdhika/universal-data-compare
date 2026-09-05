from odoo import models, fields

class UniversalDataCompareLine(models.Model):
    _name = 'data_compare_line'
    _description = 'Universal Data Compare Line'

    compare_id = fields.Many2one(
        'data_compare',
        ondelete='cascade'
    )

    primary_excel_value = fields.Char(string="Primary Excel Value", index=True)
    informational_excel_value = fields.Char(string="Informational Excel Value")
    unpivot_value = fields.Char(string="Unpivot Value")
    field_name = fields.Char(string="Field Compared")
    excel_value = fields.Char(string="Excel Value")
    odoo_value = fields.Char(string="Odoo Value")
    
    status = fields.Selection([
        ('match', 'Match'),
        ('mismatch', 'Mismatch'),
        ('not_found', 'Not Found'),
    ], string="Status")
