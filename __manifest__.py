# -*- coding: utf-8 -*-
{
    'name': "Laterna Books",
    'summary': "Laterna Books eCommerce API",
    'description': """
        Custom API module for Laterna Books.
      
    """,
    'author': "DHINESH S, The Fifthlab",
    'website': "https://thefifthlab.com/",
    'version': '18.0.1.0.0',
    'depends': [
        'base',
        'product',
        'sale',
        'stock',
        'account'
    ],
    'data': [
        # 'security/ir.model.access.csv',
        'views/config_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}