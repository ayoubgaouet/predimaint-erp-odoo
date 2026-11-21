# Journal de bord : Mini Projet ERP (Odoo)

Matière ERP Programming. Le journal du volet Big Data est dans `../Mini Projet Big Data/docs/journal_de_bord.md`.

## Séance S8 : 06/11/2026 · Premier module `predimaint` installable

### Objectif de la séance

Disposer d'un module `predimaint` qui s'installe sans erreur dans Odoo 17 Community et que
l'on peut démontrer : alerte critique → demande d'intervention prédictive → validation
humaine → onglet Santé de l'équipement.

### Ce qui est réalisé

| Élément | Détail |
| --- | --- |
| Étude du standard | Lecture du code du module Maintenance pour relever les identifiants exacts : vue `maintenance.hr_equipment_view_form`, champ `maintenance_type` de `maintenance.request` (corrective / préventive), groupe `maintenance.group_equipment_manager`, étape `maintenance.stage_0`, menu `maintenance.menu_maintenance_title`. |
| Module | `odoo/predimaint`, version `17.0.1.0.0`, dépendances `maintenance` et `stock`. Dossiers `models`, `views`, `security`, `data`, `reports`, `tests`. |
| Modèles | Extension de `maintenance.equipment` (identifiant capteur, score de santé, état calculé et stocké, dernière mesure, MTBF capteurs, disponibilité, alertes) ; nouveaux modèles `predimaint.sensor.threshold` et `predimaint.alert` ; extension de `maintenance.request` (type « Prédictive », alerte d'origine). |
| API | Méthode `predimaint.alert.create_from_api(vals)` appelable en XML-RPC ; une alerte critique crée une demande prédictive à l'étape « Nouvelle demande », affectée à l'équipe de l'équipement, ou se rattache à la demande déjà ouverte. |
| Décision humaine | Boutons « Valider et créer la demande » et « Fausse alerte », réservés au responsable maintenance. Aucune date planifiée par la plateforme. |
| Vues | Onglet « Santé » et bouton « Alertes » ajoutés au formulaire équipement par `inherit_id` + `xpath` ; score et état dans la liste des équipements ; liste, formulaire et recherche des alertes ; liste éditable des seuils ; menu Maintenance › PrediMaint (Alertes, Seuils capteurs). |
| Sécurité | `ir.model.access.csv` : lecture pour les utilisateurs internes, droits complets pour le responsable maintenance. |
| Données | 2 équipes, 4 catégories, 20 équipements `PRESSE-01`…`POMPE-05` (scores variés, voir ci-dessous), 19 seuils réalistes. Fichier `data/predimaint_data.xml` en `noupdate`. |
| Tests | 17 tests `TransactionCase` : état de santé, bornes du score, contrainte des seuils, séquence, déduplication, demande fermée non réutilisée, champs interdits dans l'API, boutons. **Résultat : 0 échec, 0 erreur.** |
| Installation | Base de travail `predimaint` : installation sans WARNING ni ERROR, interface vérifiée en français. |
| Outils | `scripts/envoyer_alerte.py` (simule le connecteur Big Data), `README.md`, `config/odoo.conf.example`. |

Répartition des états dans les données : COMP-04 Critique (35) ; PRESSE-03 (63), CONV-04 (58)
et POMPE-05 (66) en Surveillance ; les 16 autres en Normal.

### Difficultés rencontrées

1. **Champ `mtbf` déjà présent.** Le module Maintenance définit déjà `mtbf` (en jours, calculé
   sur les demandes correctives). Le redéfinir aurait cassé le calcul standard.
2. **Nom de l'étape « Nouvelle ».** Dans le code, l'étape s'appelle « New Request », traduite
   « Nouvelle demande ». Une recherche par nom dépendrait de la langue.
3. **Création de base refusée par PostgreSQL 18.** Odoo crée ses bases depuis `template0` avec
   `LC_COLLATE "C"`, mais `LC_CTYPE` reste `French_Tunisia.1252`. PostgreSQL 18 sous Windows
   refuse alors toute connexion : « les collationnements avec des valeurs différentes pour le
   tri et le jeu de caractères ne sont pas supportés sur cette plateforme ».
4. **Conflit de port.** Le service Windows `odoo-server-17.0` tourne déjà sur le port 8069
   et redémarre automatiquement au démarrage du PC.
5. **Droits d'écriture.** Le dossier de données du service (`Program Files\…\sessions`) n'est
   pas modifiable sans droits administrateur.

### Solutions testées

- Problème 3 : lancer Odoo avec `-d predimaint_test` → échec (base créée en C / French_Tunisia).
  Comparaison avec la base existante `logicile`, qui fonctionne : elle est en `C` / `C`.
- Problème 4 : modifier le `odoo.conf` du service → écarté, car il faut des droits
  administrateur et cela modifie la configuration du service.

### Corrections retenues

| Problème | Correction | Justification |
| --- | --- | --- |
| 1 | Nouveau champ `pm_mtbf_hours` (MTBF capteurs en heures) | On ajoute sans modifier le standard. |
| 2 | Étape retrouvée par son identifiant XML `maintenance.stage_0` | L'identifiant ne change ni avec la langue ni avec un renommage. |
| 3 | Bases créées à l'avance en `LC_COLLATE 'C' LC_CTYPE 'C'` (comme `logicile`) ; Odoo les initialise | Seule configuration acceptée par PostgreSQL 18 sous Windows. |
| 4 | Copie de configuration `config/odoo.conf` pour PyCharm, port **8070** | Le service et PyCharm cohabitent ; aucune manipulation administrateur le jour de la démo. |
| 5 | `data_dir` dans `.odoo_data/` du projet | Dossier accessible en écriture, exclu de Git. |
| Mots de passe | `config/odoo.conf` et `.odoo_data/` dans `.gitignore` ; seul `odoo.conf.example` (sans mot de passe) est versionné ; le script d'alerte demande le mot de passe au clavier | Consigne : aucun mot de passe dans Git. |

### Choix de conception à justifier

- **Héritage (`_inherit`) plutôt que modification** : le module Maintenance reste intact,
  il peut être mis à jour par Odoo sans perdre nos ajouts.
- **`selection_add` avec `ondelete='set default'`** : on ajoute « Prédictive » sans recopier
  la liste ; si le module est désinstallé, les demandes prédictives redeviennent correctives
  au lieu de bloquer la désinstallation.
- **État de santé `store=True`** : il peut être filtré, groupé et utilisé dans un kanban coloré.
- **Liste blanche des champs de l'API** : la chaîne Big Data ne peut envoyer que la mesure ;
  elle ne peut pas forcer l'état d'une alerte ou la demande liée.
- **Déduplication sur « demande ouverte »** (étape non terminée et non archivée) : une machine
  en dérive envoie des dizaines d'alertes ; une seule demande doit être créée.

### Reste à faire (séances suivantes)

- Kanban des équipements coloré par état ; vues graphique et pivot des alertes.
- Rapport QWeb « Fiche santé équipement » (dossier `reports/` préparé).
- `ir.cron` d'escalade (alerte critique non traitée sous 2 h) et message Discuss à l'équipe.
- Groupes de la section 5.4 (opérateur, technicien, direction, utilisateur API), règle
  `ir.rule` par équipe, tests avec des utilisateurs non administrateurs.
- L'action standard « demandes d'une équipe » (tableau de bord Maintenance) filtre
  `maintenance_type in ['preventive', 'corrective']` : les demandes prédictives n'y
  apparaissent pas. À traiter par héritage de l'action.
- Webhook sortant vers le connecteur ; import CSV de l'historique.
