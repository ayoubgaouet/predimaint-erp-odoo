# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HEALTH_STATES = [
    ('normal', 'Normal'),
    ('surveillance', 'Surveillance'),
    ('critique', 'Critique'),
]

# Bornes de l'état de santé (cahier des charges, section 6.1)
HEALTH_NORMAL_MIN = 70.0     # score >= 70        -> Normal
HEALTH_WATCH_MIN = 40.0      # 40 <= score < 70   -> Surveillance
                             # score < 40         -> Critique


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    sensor_ref = fields.Char(
        string='Identifiant capteur', copy=False, index=True,
        help="Identifiant utilisé par la chaîne Big Data (ex. PRESSE-01).")
    health_score = fields.Float(
        string='Score de santé', default=100.0, tracking=True,
        help="De 0 (panne imminente) à 100 (parfait état). "
             "Recalculé chaque nuit par Spark batch.")
    health_state = fields.Selection(
        HEALTH_STATES, string='État de santé',
        compute='_compute_health_state', store=True)
    last_measure_date = fields.Datetime(string='Dernière mesure')
    # Le module standard possède déjà un champ « mtbf » (en jours, calculé
    # sur les demandes correctives). On ne l'écrase pas : ce champ-ci reçoit
    # le MTBF calculé par Spark batch à partir des données capteurs.
    pm_mtbf_hours = fields.Float(
        string='MTBF capteurs (h)',
        help="Temps moyen entre deux pannes, en heures, calculé par Spark batch.")
    availability_rate = fields.Float(
        string='Disponibilité (%)',
        help="Temps de marche / temps d'ouverture, calculé par Spark batch.")
    alert_ids = fields.One2many(
        'predimaint.alert', 'equipment_id', string='Alertes')
    alert_count = fields.Integer(
        string="Nombre d'alertes", compute='_compute_alert_count')
    threshold_ids = fields.Many2many(
        'predimaint.sensor.threshold', string='Seuils applicables',
        compute='_compute_threshold_ids')

    _sql_constraints = [
        ('sensor_ref_uniq', 'unique(sensor_ref)',
         "Cet identifiant capteur est déjà utilisé par un autre équipement."),
    ]

    @api.depends('health_score')
    def _compute_health_state(self):
        for equipment in self:
            score = equipment.health_score
            if score >= HEALTH_NORMAL_MIN:
                equipment.health_state = 'normal'
            elif score >= HEALTH_WATCH_MIN:
                equipment.health_state = 'surveillance'
            else:
                equipment.health_state = 'critique'

    @api.constrains('health_score')
    def _check_health_score(self):
        for equipment in self:
            if not 0.0 <= equipment.health_score <= 100.0:
                raise ValidationError(_(
                    "Le score de santé doit être compris entre 0 et 100 "
                    "(valeur reçue : %s).", equipment.health_score))

    @api.constrains('availability_rate')
    def _check_availability_rate(self):
        for equipment in self:
            if not 0.0 <= equipment.availability_rate <= 100.0:
                raise ValidationError(_(
                    "La disponibilité doit être comprise entre 0 et 100 %."))

    @api.depends('alert_ids')
    def _compute_alert_count(self):
        counts = dict(self.env['predimaint.alert']._read_group(
            [('equipment_id', 'in', self.ids)], ['equipment_id'], ['__count']))
        for equipment in self:
            equipment.alert_count = counts.get(equipment, 0)

    @api.depends('category_id')
    def _compute_threshold_ids(self):
        Threshold = self.env['predimaint.sensor.threshold']
        for equipment in self:
            equipment.threshold_ids = Threshold.search(
                [('category_id', '=', equipment.category_id.id)]
            ) if equipment.category_id else Threshold

    def action_view_alerts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'predimaint.predimaint_alert_action')
        action['domain'] = [('equipment_id', '=', self.id)]
        action['context'] = {'default_equipment_id': self.id}
        return action
