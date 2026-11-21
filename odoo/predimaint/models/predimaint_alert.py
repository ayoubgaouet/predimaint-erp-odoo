# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .sensor_threshold import MEASURE_TYPES

SEVERITIES = [
    ('surveillance', 'Surveillance'),
    ('critique', 'Critique'),
]

ALERT_STATES = [
    ('new', 'Nouvelle'),
    ('done', 'Traitée'),
    ('false_alarm', 'Fausse alerte'),
]

# Champs que la chaîne Big Data a le droit d'envoyer par l'API.
# Tout autre champ (état, demande liée...) est refusé : c'est Odoo qui décide.
API_ALLOWED_KEYS = {
    'equipment_id', 'sensor_ref', 'measure_type', 'value',
    'threshold', 'severity', 'alert_date',
}


class PredimaintAlert(models.Model):
    _name = 'predimaint.alert'
    _description = 'Alerte prédictive PrediMaint'
    _inherit = ['mail.thread']
    _order = 'alert_date desc, id desc'

    name = fields.Char(
        string='Référence', required=True, readonly=True, copy=False,
        default=lambda self: _('Nouveau'))
    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Équipement', required=True,
        ondelete='cascade', index=True, tracking=True)
    sensor_ref = fields.Char(
        related='equipment_id.sensor_ref', string='Identifiant capteur')
    category_id = fields.Many2one(
        related='equipment_id.category_id', store=True, string='Catégorie')
    maintenance_team_id = fields.Many2one(
        related='equipment_id.maintenance_team_id', store=True, string='Équipe')
    measure_type = fields.Selection(
        MEASURE_TYPES, string='Grandeur', required=True)
    value = fields.Float(string='Valeur mesurée', required=True)
    threshold = fields.Float(string='Seuil dépassé')
    unit = fields.Char(string='Unité')
    severity = fields.Selection(
        SEVERITIES, string='Gravité', required=True, tracking=True)
    alert_date = fields.Datetime(
        string="Date de l'alerte", required=True, default=fields.Datetime.now)
    state = fields.Selection(
        ALERT_STATES, string='État', required=True, default='new',
        tracking=True)
    request_id = fields.Many2one(
        'maintenance.request', string="Demande d'intervention liée",
        ondelete='set null', index=True, tracking=True, copy=False)

    # ------------------------------------------------------------------
    # Création : référence par séquence ALR0001, ALR0002...
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nouveau'):
                vals['name'] = (self.env['ir.sequence']
                                .next_by_code('predimaint.alert') or _('Nouveau'))
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Point d'entrée de la chaîne Big Data (XML-RPC, execute_kw)
    # ------------------------------------------------------------------
    @api.model
    def create_from_api(self, vals):
        """Crée une alerte reçue de la chaîne Big Data.

        Exemple d'appel XML-RPC :
            models.execute_kw(db, uid, key, 'predimaint.alert',
                              'create_from_api',
                              [{'sensor_ref': 'COMP-03',
                                'measure_type': 'temperature',
                                'value': 112.4}])

        Règles métier (cahier des charges, section 6.4) :
        * une alerte « surveillance » reste une simple alerte ;
        * une alerte « critique » crée une demande prédictive à l'étape
          « Nouvelle », affectée à l'équipe de l'équipement ;
        * si l'équipement a déjà une demande ouverte, l'alerte y est
          rattachée au lieu d'en créer une nouvelle (pas de doublon) ;
        * aucune planification : pas de date prévue, c'est le responsable
          maintenance qui décide.

        Retourne un dictionnaire (types simples, lisibles en XML-RPC).
        """
        if not isinstance(vals, dict):
            raise ValidationError(_("create_from_api attend un dictionnaire."))
        unknown = set(vals) - API_ALLOWED_KEYS
        if unknown:
            raise ValidationError(_(
                "Champs non autorisés dans l'appel API : %s",
                ', '.join(sorted(unknown))))

        equipment = self._api_find_equipment(vals)
        measure_type = vals.get('measure_type')
        if measure_type not in dict(MEASURE_TYPES):
            raise ValidationError(_("Grandeur inconnue : %s", measure_type))
        if vals.get('value') is None:
            raise ValidationError(_("La valeur mesurée est obligatoire."))
        value = float(vals['value'])

        threshold_rec = self.env['predimaint.sensor.threshold'].search([
            ('category_id', '=', equipment.category_id.id),
            ('measure_type', '=', measure_type),
        ], limit=1)

        severity = vals.get('severity')
        if not severity:
            if not threshold_rec:
                raise ValidationError(_(
                    "Aucun seuil défini pour %(cat)s / %(measure)s : "
                    "la gravité doit être fournie.",
                    cat=equipment.category_id.display_name,
                    measure=measure_type))
            severity = threshold_rec._get_severity(value)
            if not severity:
                raise ValidationError(_(
                    "La valeur %(value)s reste sous le seuil d'alerte : "
                    "aucune alerte n'est créée.", value=value))
        if severity not in dict(SEVERITIES):
            raise ValidationError(_("Gravité inconnue : %s", severity))

        threshold = vals.get('threshold')
        if threshold is None and threshold_rec:
            threshold = (threshold_rec.critical_threshold
                         if severity == 'critique'
                         else threshold_rec.alert_threshold)

        alert_date = self._api_parse_date(vals.get('alert_date'))
        alert = self.create({
            'equipment_id': equipment.id,
            'measure_type': measure_type,
            'value': value,
            'threshold': threshold or 0.0,
            'unit': threshold_rec.unit or False,
            'severity': severity,
            'alert_date': alert_date,
        })
        equipment.last_measure_date = alert.alert_date

        request_created = False
        if severity == 'critique':
            request_created = alert._link_or_create_request()

        return {
            'alert_id': alert.id,
            'alert_name': alert.name,
            'severity': alert.severity,
            'request_id': alert.request_id.id or False,
            'request_created': request_created,
        }

    @api.model
    def _api_find_equipment(self, vals):
        Equipment = self.env['maintenance.equipment']
        if vals.get('equipment_id'):
            equipment = Equipment.browse(int(vals['equipment_id'])).exists()
        elif vals.get('sensor_ref'):
            equipment = Equipment.search(
                [('sensor_ref', '=', vals['sensor_ref'])], limit=1)
        else:
            raise ValidationError(_(
                "Indiquez l'équipement (equipment_id) ou son identifiant "
                "capteur (sensor_ref)."))
        if not equipment:
            raise ValidationError(_(
                "Équipement introuvable : %s",
                vals.get('equipment_id') or vals.get('sensor_ref')))
        return equipment

    @api.model
    def _api_parse_date(self, value):
        """Accepte « 2026-11-06 10:15:00 » ou le format ISO « 2026-11-06T10:15:00Z »
        envoyé par Kafka/Spark."""
        if not value:
            return fields.Datetime.now()
        if isinstance(value, str):
            value = value.replace('T', ' ').rstrip('Z')[:19]
        return fields.Datetime.to_datetime(value)

    # ------------------------------------------------------------------
    # Lien avec les demandes d'intervention
    # ------------------------------------------------------------------
    def _find_open_request(self):
        """Demande non terminée et non archivée de l'équipement, s'il y en a une."""
        self.ensure_one()
        return self.env['maintenance.request'].search([
            ('equipment_id', '=', self.equipment_id.id),
            ('stage_id.done', '=', False),
            ('archive', '=', False),
        ], order='id desc', limit=1)

    def _link_or_create_request(self):
        """Rattache l'alerte à la demande ouverte de l'équipement, ou crée une
        demande prédictive. Retourne True si une demande a été créée."""
        self.ensure_one()
        if self.request_id:
            return False
        request = self._find_open_request()
        if request:
            self.request_id = request
            request.message_post(body=Markup(_(
                "Nouvelle alerte rattachée : <b>%(alert)s</b> (%(measure)s = "
                "%(value)s %(unit)s, gravité %(severity)s).")) % {
                    'alert': escape(self.name),
                    'measure': escape(self._measure_label()),
                    'value': self.value,
                    'unit': escape(self.unit or ''),
                    'severity': escape(self._severity_label()),
            })
            return False
        self.request_id = self.env['maintenance.request'].create(
            self._prepare_request_vals())
        return True

    def _prepare_request_vals(self):
        self.ensure_one()
        stage = self.env.ref('maintenance.stage_0', raise_if_not_found=False)
        if not stage:
            stage = self.env['maintenance.stage'].search([], order='sequence', limit=1)
        vals = {
            'name': _("[Prédictive] %(equipment)s - %(measure)s %(value)s %(unit)s",
                      equipment=self.equipment_id.name,
                      measure=self._measure_label(),
                      value=self.value,
                      unit=self.unit or ''),
            'equipment_id': self.equipment_id.id,
            'maintenance_type': 'predictive',
            'stage_id': stage.id,
            'priority': '3' if self.severity == 'critique' else '2',
            'alert_id': self.id,
            'description': Markup(_(
                "<p>Demande créée par PrediMaint à partir de l'alerte "
                "<b>%(alert)s</b>.</p><p>%(measure)s mesurée : %(value)s %(unit)s "
                "(seuil : %(threshold)s).</p><p><i>À valider et planifier par le "
                "responsable maintenance.</i></p>")) % {
                    'alert': escape(self.name),
                    'measure': escape(self._measure_label()),
                    'value': self.value,
                    'unit': escape(self.unit or ''),
                    'threshold': self.threshold,
            },
        }
        # L'équipe est celle de l'équipement (la « bonne équipe »).
        if self.equipment_id.maintenance_team_id:
            vals['maintenance_team_id'] = self.equipment_id.maintenance_team_id.id
        return vals

    def _measure_label(self):
        return dict(MEASURE_TYPES).get(self.measure_type, self.measure_type)

    def _severity_label(self):
        return dict(SEVERITIES).get(self.severity, self.severity)

    # ------------------------------------------------------------------
    # Boutons : la décision appartient au responsable maintenance
    # ------------------------------------------------------------------
    def action_validate(self):
        """« Valider et créer la demande » : l'alerte est confirmée par un humain.
        Une demande prédictive est créée (ou l'alerte est rattachée à la
        demande ouverte). Aucune date n'est planifiée."""
        for alert in self:
            if alert.state != 'new':
                raise UserError(_("L'alerte %s a déjà été traitée.", alert.name))
            alert._link_or_create_request()
            alert.state = 'done'
        if len(self) == 1 and self.request_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'maintenance.request',
                'res_id': self.request_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return True

    def action_false_alarm(self):
        """« Fausse alerte » : sert à mesurer le taux de fausses alertes (KPI)."""
        for alert in self:
            if alert.state != 'new':
                raise UserError(_("L'alerte %s a déjà été traitée.", alert.name))
            alert.state = 'false_alarm'
        return True

    def action_reset_new(self):
        """Remettre à l'état « Nouvelle » (correction d'une erreur de saisie)."""
        self.write({'state': 'new'})
        return True
