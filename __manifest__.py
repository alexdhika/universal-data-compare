{
    'name': 'Universal Data Compare',
    'summary': "Surya Semesta Modul Universal Data Compare",

    'description': """
Tools untuk membandingkan data antara Excel dan Odoo.
    """,

    'author': "Surya Semesta Dev Team",
    'website': "https://www.suryasemesta.com",
    'license': 'OEEL-1',
    'version': '1.0',
    'depends': ['base','mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/compare_views.xml',
        'views/compare_config_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
