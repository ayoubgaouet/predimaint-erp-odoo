# PrediMaint : maintenance prédictive dans Odoo 17

Mini-projet ERP Programming : *Étude et optimisation de la gestion de la maintenance
industrielle dans l'ERP Odoo par l'intégration de fonctionnalités prédictives.*
Cahier des charges : `Cahier des charges — Plateforme de maintenance prédictive (Odoo + Big Data).md`.

## Contenu du dépôt

| Chemin | Rôle |
| --- | --- |
| `odoo/predimaint/` | Module Odoo 17 (dépend de `maintenance` et `stock`) |
| `config/odoo.conf.example` | Modèle de configuration Odoo **sans mot de passe** |
| `config/odoo.conf` | Configuration réelle utilisée par PyCharm (**ignorée par Git**) |
| `scripts/envoyer_alerte.py` | Simule le connecteur Big Data : envoie une alerte par XML-RPC |
| `docs/journal_de_bord.md` | Journal de bord des séances |
| `docs/rapport/Rapport_avancement_ERP_S8.pdf` | Rapport d'avancement envoyé à l'enseignante (source HTML à côté) |
| `docs/images/` | Schémas : modèle de données, traitement d'une alerte |
| `../Mini Projet Big Data/` | L'autre mini-projet (Kafka, Logstash, Elasticsearch, Kibana, Spark) |

## Ce que fait le module

- **Équipements** (`maintenance.equipment`, par héritage) : identifiant capteur, score de santé
  0 à 100, état calculé et stocké (Normal ≥ 70, Surveillance 40 à 70, Critique < 40),
  date de dernière mesure, MTBF capteurs (h), disponibilité (%), alertes et leur nombre.
  Un onglet **Santé** est ajouté au formulaire standard par héritage de vue (`xpath`).
- **Seuils** (`predimaint.sensor.threshold`) : par catégorie et par grandeur
  (`temperature`, `vibration`, `pression`, `puissance_kw`, `bruit_db`), avec la contrainte
  « seuil critique > seuil d'alerte ».
- **Alertes** (`predimaint.alert`) : référence `ALR0001`… La méthode `create_from_api(vals)`,
  appelable en XML-RPC, crée l'alerte ; une alerte critique crée une demande d'intervention
  **prédictive** à l'étape « Nouvelle », ou se rattache à la demande déjà ouverte de
  l'équipement. Boutons « Valider et créer la demande » et « Fausse alerte ».
  La plateforme ne planifie jamais d'intervention : le responsable maintenance décide.
- **Demandes** (`maintenance.request`, par héritage) : type « Prédictive » ajouté
  (`selection_add`), alerte d'origine et alertes rattachées.
- **Données** : 2 équipes, 4 catégories, 20 équipements `PRESSE-01`…`POMPE-05`, 19 seuils.

## Installation

Prérequis : Odoo 17 Community installé sous Windows dans
`C:\Program Files\Odoo 17.0.20260930` (avec son Python et PostgreSQL).

1. Créer la configuration locale à partir du modèle, puis y remplacer les deux
   `CHANGE_ME` par les vrais mots de passe (ceux de `server\odoo.conf`) :

   ```powershell
   Copy-Item "D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\config\odoo.conf.example" "D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\config\odoo.conf"
   ```

   Dans ce fichier, `addons_path` contient le dossier standard **et**
   `D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\odoo`. Le port est **8070**, car le service
   Windows `odoo-server-17.0` occupe déjà 8069.

2. Créer la base **avant** de lancer Odoo. Avec PostgreSQL 18 sous Windows, une base
   créée par Odoo lui-même (`LC_COLLATE "C"` mais `LC_CTYPE` French_Tunisia) est refusée :
   « les collationnements avec des valeurs différentes pour le tri et le jeu de caractères
   ne sont pas supportés ». On la crée donc en `C`/`C` (dans pgAdmin ou psql, utilisateur `openpg`) :

   ```sql
   CREATE DATABASE "predimaint" ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;
   ```

   Odoo détecte que la base existe mais est vide, et l'initialise.

3. Installer le module dans la base de travail `predimaint` :

   ```powershell
   & "C:\Program Files\Odoo 17.0.20260930\python\python.exe" "C:\Program Files\Odoo 17.0.20260930\server\odoo-bin" -c "D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\config\odoo.conf" -d predimaint -i predimaint --without-demo=all --stop-after-init
   ```

## Lancement

### En ligne de commande

```powershell
& "C:\Program Files\Odoo 17.0.20260930\python\python.exe" "C:\Program Files\Odoo 17.0.20260930\server\odoo-bin" -c "D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\config\odoo.conf" -d predimaint
```

Puis ouvrir <http://localhost:8070/web>, application Maintenance, menu **PrediMaint**.

### Depuis PyCharm

Run > Edit Configurations > « + » > Python :

| Champ | Valeur |
| --- | --- |
| Script path | `C:\Program Files\Odoo 17.0.20260930\server\odoo-bin` |
| Parameters | `-c "D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\config\odoo.conf" -d predimaint` |
| Python interpreter | `C:\Program Files\Odoo 17.0.20260930\python\python.exe` |
| Working directory | `C:\Program Files\Odoo 17.0.20260930\server` |

- Modification **Python** : redémarrer Odoo.
- Modification **XML** (vues, données) : ajouter `-u predimaint` aux paramètres, relancer, puis l'enlever.

## Tests

Les tests (`odoo/predimaint/tests/test_predimaint.py`, `TransactionCase`) s'exécutent sur
une base **séparée** `predimaint_test` (créée en `C`/`C` comme ci-dessus), jamais sur la base de travail :

```powershell
& "C:\Program Files\Odoo 17.0.20260930\python\python.exe" "C:\Program Files\Odoo 17.0.20260930\server\odoo-bin" -c "D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\config\odoo.conf" -d predimaint_test -i predimaint --without-demo=all --test-enable --test-tags /predimaint --stop-after-init --log-level=test
```

Pour relancer sur une base déjà créée, remplacer `-i predimaint` par `-u predimaint`.

## Envoyer une alerte (simulation du connecteur Big Data)

```powershell
& "C:\Program Files\Odoo 17.0.20260930\python\python.exe" "D:\3GL Alt\mini projet big data et erp\Mini Projet ERP\scripts\envoyer_alerte.py" COMP-03 temperature 112.4
```

Le mot de passe (ou mieux, une clé d'API : Préférences > Sécurité du compte > Nouvelle clé
d'API) est demandé au clavier, ou lu dans la variable d'environnement `ODOO_KEY`.
Il n'est jamais écrit dans le dépôt.
