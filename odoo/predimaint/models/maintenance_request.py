# -*- coding: utf-8 -*-
from odoo import fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    # selection_add ajoute une valeur à la liste standard (corrective,
    # préventive) sans la redéfinir. ondelete indique quoi faire des demandes
    # « prédictives » si le module est désinstallé : elles repassent à la
    # valeur par défaut du champ (corrective) au lieu de bloquer.
    maintenance_type = fields.Selection(
        selection_add=[('predictive', 'Prédictive')],
        ondelete={'predictive': 'set default'})
    alert_id = fields.Many2one(
        'predimaint.alert', string="Alerte d'origine",
        ondelete='set null', readonly=True, copy=False)
    alert_ids = fields.One2many(
        'predimaint.alert', 'request_id', string='Alertes rattachées')
