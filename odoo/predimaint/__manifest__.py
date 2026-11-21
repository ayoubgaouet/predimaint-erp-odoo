# -*- coding: utf-8 -*-
{
    'name': 'PrediMaint - Maintenance prédictive',
    'version': '17.0.1.0.0',
    'summary': "Score de santé des équipements, seuils capteurs et alertes "
               "prédictives reçues de la chaîne Big Data",
    'description': """
PrediMaint
==========
Extension du module Maintenance d'Odoo 17 :

* score de santé et état (Normal / Surveillance / Critique) par équipement ;
* seuils d'alerte et seuils critiques par catégorie et par grandeur mesurée ;
* alertes reçues par XML-RPC (méthode ``create_from_api``) ;
* création d'une demande d'intervention prédictive pour une alerte critique,
  sans doublon si l'équipement a déjà une demande ouverte ;
* validation humaine : le responsable maintenance valide ou classe
  en fausse alerte. La plateforme ne planifie jamais d'intervention.
""",
    'author': 'Équipe PrediMaint',
    'category': 'Manufacturing/Maintenance',
    'license': 'LGPL-3',
    'depends': ['maintenance', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/alert_views.xml',
        'views/sensor_threshold_views.xml',
        'views/equipment_views.xml',
        'views/maintenance_request_views.xml',
        'views/menus.xml',
        'data/predimaint_data.xml',
    ],
    'installable': True,
    'application': False,
}
