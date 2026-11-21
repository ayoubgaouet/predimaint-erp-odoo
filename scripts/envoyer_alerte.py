# -*- coding: utf-8 -*-
"""Envoie une alerte capteur à Odoo par XML-RPC, comme le fera le connecteur Big Data.

Usage (PowerShell) :
    & "C:\\Program Files\\Odoo 17.0.20260930\\python\\python.exe" "scripts\\envoyer_alerte.py" COMP-03 temperature 112.4

Paramètres de connexion (variables d'environnement, avec valeurs par défaut) :
    ODOO_URL   http://localhost:8070
    ODOO_DB    predimaint
    ODOO_USER  admin
    ODOO_KEY   clé d'API ou mot de passe ; demandé au clavier s'il est absent.

Aucun mot de passe n'est écrit dans ce fichier : il ne doit jamais être versionné dans Git.
"""
import getpass
import os
import sys
import xmlrpc.client


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    sensor_ref, measure_type, value = sys.argv[1], sys.argv[2], float(sys.argv[3])
    severity = sys.argv[4] if len(sys.argv) > 4 else None

    url = os.environ.get('ODOO_URL', 'http://localhost:8070')
    db = os.environ.get('ODOO_DB', 'predimaint')
    user = os.environ.get('ODOO_USER', 'admin')
    key = os.environ.get('ODOO_KEY') or getpass.getpass(f"Mot de passe ou clé d'API de {user} : ")

    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, user, key, {})
    if not uid:
        sys.exit("Authentification refusée.")

    vals = {'sensor_ref': sensor_ref, 'measure_type': measure_type, 'value': value}
    if severity:
        vals['severity'] = severity

    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    result = models.execute_kw(db, uid, key, 'predimaint.alert', 'create_from_api', [vals])
    print("Réponse d'Odoo :")
    for k, v in result.items():
        print(f"  {k:16} {v}")


if __name__ == '__main__':
    main()
