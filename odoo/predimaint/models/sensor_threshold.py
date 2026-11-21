# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Grandeurs mesurées par les capteurs. Les clés techniques (à gauche) sont
# celles envoyées par le simulateur Big Data : elles ne doivent pas changer.
MEASURE_TYPES = [
    ('temperature', 'Température'),
    ('vibration', 'Vibration'),
    ('pression', 'Pression'),
    ('puissance_kw', 'Puissance (kW)'),
    ('bruit_db', 'Bruit (dB)'),
]


class PredimaintSensorThreshold(models.Model):
    _name = 'predimaint.sensor.threshold'
    _description = 'Seuil capteur PrediMaint'
    _order = 'category_id, measure_type'
    _rec_name = 'measure_type'

    category_id = fields.Many2one(
        'maintenance.equipment.category', string="Catégorie d'équipement",
        required=True, ondelete='cascade', index=True)
    measure_type = fields.Selection(
        MEASURE_TYPES, string='Grandeur', required=True)
    alert_threshold = fields.Float(
        string="Seuil d'alerte", required=True,
        help="Au-delà de cette valeur, l'alerte est de gravité « Surveillance ».")
    critical_threshold = fields.Float(
        string='Seuil critique', required=True,
        help="Au-delà de cette valeur, l'alerte est « Critique » et une "
             "demande d'intervention prédictive est proposée.")
    unit = fields.Char(string='Unité', help='Exemples : °C, mm/s, bar, kW, dB')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('category_measure_uniq', 'unique(category_id, measure_type)',
         'Un seul seuil par catégorie et par grandeur.'),
    ]

    @api.constrains('alert_threshold', 'critical_threshold')
    def _check_thresholds(self):
        for threshold in self:
            if threshold.critical_threshold <= threshold.alert_threshold:
                raise ValidationError(_(
                    "Le seuil critique (%(critical)s) doit être strictement "
                    "supérieur au seuil d'alerte (%(alert)s).",
                    critical=threshold.critical_threshold,
                    alert=threshold.alert_threshold,
                ))

    def _get_severity(self, value):
        """Gravité correspondant à une valeur mesurée, ou False si la valeur
        reste sous le seuil d'alerte."""
        self.ensure_one()
        if value >= self.critical_threshold:
            return 'critique'
        if value >= self.alert_threshold:
            return 'surveillance'
        return False
