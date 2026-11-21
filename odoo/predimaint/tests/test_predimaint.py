# -*- coding: utf-8 -*-
"""Tests unitaires PrediMaint (cahier des charges, section 6.6).

TransactionCase : chaque test s'exécute dans une transaction annulée à la fin,
la base de test reste donc propre d'un test à l'autre.
"""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'predimaint')
class TestPredimaint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Jeu de données propre au test, indépendant du fichier data/.
        cls.team = cls.env['maintenance.team'].create({'name': 'Équipe test'})
        cls.category = cls.env['maintenance.equipment.category'].create({
            'name': 'Catégorie test',
        })
        cls.threshold = cls.env['predimaint.sensor.threshold'].create({
            'category_id': cls.category.id,
            'measure_type': 'temperature',
            'alert_threshold': 60.0,
            'critical_threshold': 75.0,
            'unit': '°C',
        })
        cls.equipment = cls.env['maintenance.equipment'].create({
            'name': 'Machine test',
            'sensor_ref': 'TEST-01',
            'category_id': cls.category.id,
            'maintenance_team_id': cls.team.id,
            'health_score': 90.0,
        })
        cls.Alert = cls.env['predimaint.alert']

    # ------------------------------------------------------------------
    # 1. Calcul de l'état de santé
    # ------------------------------------------------------------------
    def test_health_state_limits(self):
        """Normal >= 70, Surveillance de 40 à 70, Critique < 40 (bornes comprises)."""
        cases = [
            (100.0, 'normal'),
            (70.0, 'normal'),
            (69.9, 'surveillance'),
            (40.0, 'surveillance'),
            (39.9, 'critique'),
            (0.0, 'critique'),
        ]
        for score, expected in cases:
            with self.subTest(score=score):
                self.equipment.health_score = score
                self.assertEqual(self.equipment.health_state, expected)

    def test_health_state_is_stored(self):
        """L'état est stocké : on peut filtrer les équipements critiques en base."""
        self.equipment.health_score = 20.0
        self.env.flush_all()
        found = self.env['maintenance.equipment'].search([
            ('id', '=', self.equipment.id), ('health_state', '=', 'critique')])
        self.assertEqual(found, self.equipment)

    def test_health_score_bounds(self):
        with self.assertRaises(ValidationError):
            self.equipment.health_score = 120.0
        with self.assertRaises(ValidationError):
            self.equipment.health_score = -5.0

    # ------------------------------------------------------------------
    # 2. Contrainte sur les seuils
    # ------------------------------------------------------------------
    def test_threshold_critical_must_exceed_alert(self):
        with self.assertRaises(ValidationError):
            self.env['predimaint.sensor.threshold'].create({
                'category_id': self.category.id,
                'measure_type': 'vibration',
                'alert_threshold': 7.1,
                'critical_threshold': 4.5,
            })
        # Égalité refusée aussi : « strictement supérieur ».
        with self.assertRaises(ValidationError):
            self.threshold.critical_threshold = 60.0

    def test_threshold_valid(self):
        threshold = self.env['predimaint.sensor.threshold'].create({
            'category_id': self.category.id,
            'measure_type': 'vibration',
            'alert_threshold': 4.5,
            'critical_threshold': 7.1,
            'unit': 'mm/s',
        })
        self.assertEqual(threshold._get_severity(3.0), False)
        self.assertEqual(threshold._get_severity(5.0), 'surveillance')
        self.assertEqual(threshold._get_severity(8.0), 'critique')

    # ------------------------------------------------------------------
    # 3. Alertes reçues par l'API et déduplication
    # ------------------------------------------------------------------
    def test_sequence_reference(self):
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 65.0})
        alert = self.Alert.browse(result['alert_id'])
        self.assertTrue(alert.name.startswith('ALR'))
        self.assertEqual(len(alert.name), 7)  # ALR + 4 chiffres

    def test_surveillance_alert_creates_no_request(self):
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 65.0})
        alert = self.Alert.browse(result['alert_id'])
        self.assertEqual(alert.severity, 'surveillance')  # calculée par les seuils
        self.assertFalse(alert.request_id)
        self.assertFalse(result['request_created'])
        self.assertEqual(alert.state, 'new')

    def test_critical_alert_creates_predictive_request(self):
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 82.0})
        alert = self.Alert.browse(result['alert_id'])
        request = alert.request_id
        self.assertTrue(result['request_created'])
        self.assertEqual(alert.severity, 'critique')
        self.assertEqual(alert.threshold, 75.0)
        self.assertEqual(request.maintenance_type, 'predictive')
        self.assertEqual(request.stage_id, self.env.ref('maintenance.stage_0'))
        self.assertEqual(request.maintenance_team_id, self.team)
        self.assertEqual(request.equipment_id, self.equipment)
        self.assertEqual(request.alert_id, alert)
        # La plateforme ne planifie pas : aucune date prévue.
        self.assertFalse(request.schedule_date)
        # L'alerte reste « Nouvelle » : le responsable doit décider.
        self.assertEqual(alert.state, 'new')
        self.assertTrue(self.equipment.last_measure_date)

    def test_duplicate_critical_alert_is_attached(self):
        """Deux alertes critiques sur la même machine : une seule demande."""
        first = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 80.0})
        second = self.Alert.create_from_api({
            'equipment_id': self.equipment.id, 'measure_type': 'temperature',
            'value': 85.0, 'severity': 'critique'})
        self.assertTrue(first['request_created'])
        self.assertFalse(second['request_created'])
        self.assertEqual(first['request_id'], second['request_id'])
        requests = self.env['maintenance.request'].search([
            ('equipment_id', '=', self.equipment.id)])
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(requests.alert_ids), 2)

    def test_existing_open_request_is_reused(self):
        """Une demande corrective déjà ouverte reçoit l'alerte critique."""
        existing = self.env['maintenance.request'].create({
            'name': 'Bruit anormal signalé par l\'opérateur',
            'equipment_id': self.equipment.id,
        })
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 90.0})
        self.assertEqual(result['request_id'], existing.id)
        self.assertFalse(result['request_created'])

    def test_closed_request_is_not_reused(self):
        """Une demande terminée n'est pas « ouverte » : on en crée une nouvelle."""
        done_stage = self.env['maintenance.stage'].search([('done', '=', True)], limit=1)
        old = self.env['maintenance.request'].create({
            'name': 'Ancienne intervention',
            'equipment_id': self.equipment.id,
            'stage_id': done_stage.id,
        })
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 90.0})
        self.assertTrue(result['request_created'])
        self.assertNotEqual(result['request_id'], old.id)

    def test_api_rejects_forbidden_fields(self):
        with self.assertRaises(ValidationError):
            self.Alert.create_from_api({
                'sensor_ref': 'TEST-01', 'measure_type': 'temperature',
                'value': 90.0, 'state': 'done'})

    def test_api_unknown_equipment(self):
        with self.assertRaises(ValidationError):
            self.Alert.create_from_api({
                'sensor_ref': 'INCONNU-99', 'measure_type': 'temperature', 'value': 90.0})

    def test_api_iso_date(self):
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 65.0,
            'alert_date': '2026-11-06T10:15:30.123Z'})
        alert = self.Alert.browse(result['alert_id'])
        self.assertEqual(str(alert.alert_date), '2026-11-06 10:15:30')

    # ------------------------------------------------------------------
    # 4. Boutons de décision du responsable
    # ------------------------------------------------------------------
    def test_validate_surveillance_alert_creates_request(self):
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 65.0})
        alert = self.Alert.browse(result['alert_id'])
        alert.action_validate()
        self.assertEqual(alert.state, 'done')
        self.assertEqual(alert.request_id.maintenance_type, 'predictive')
        self.assertEqual(alert.request_id.priority, '2')

    def test_false_alarm(self):
        result = self.Alert.create_from_api({
            'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': 65.0})
        alert = self.Alert.browse(result['alert_id'])
        alert.action_false_alarm()
        self.assertEqual(alert.state, 'false_alarm')
        self.assertFalse(alert.request_id)

    def test_alert_count(self):
        for value in (65.0, 66.0, 67.0):
            self.Alert.create_from_api({
                'sensor_ref': 'TEST-01', 'measure_type': 'temperature', 'value': value})
        self.equipment.invalidate_recordset(['alert_count'])
        self.assertEqual(self.equipment.alert_count, 3)
