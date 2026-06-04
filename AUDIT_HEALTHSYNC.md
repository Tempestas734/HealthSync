# Audit HealthSync

## Portee et methode

Audit refait sur l'etat actuel du depot, en lecture statique du code Django et des scripts SQL.

Fichiers analyses :
- `apps/accounts/models.py`
- `apps/accounts/forms.py`
- `apps/accounts/views.py`
- `apps/accounts/urls.py`
- `templates/`
- `sql/`

Controles executes :
- syntaxe Python sur `models.py`, `forms.py`, `views.py`, `urls.py` : OK
- verification des templates appeles par `render(...)` : aucun template manquant
- verification des noms d'URL utilises par `redirect(...)` et `reverse(...)` : aucune route manquante
- revue des flux role par role en statique
- revue des scripts SQL de support

Limite importante :
- les tests runtime Django n'ont pas pu etre executes ici, car `django` n'est pas installe dans l'environnement courant

## Resume executif

Le projet est maintenant mieux aligne qu'au precedent audit sur les points suivants :
- la logique patient a ete corrigee cote Django pour utiliser `patient_code` comme CIN / code optionnel
- `barcode_value` reste l'identifiant technique obligatoire
- les roles staff cibles tombent maintenant sur le bon dashboard
- `staff_frontdesk` est present dans `PersonnelEtablissement.ROLE_CHOICES`
- le doublon runtime de `super_admin_facility_create` n'existe plus ; une ancienne version a ete renommee en fonction legacy inutilisee

Les blocants restants sont surtout :
- flux d'activation de compte et de mot de passe initial non implementes
- quelques incoherences Django <-> PostgreSQL encore ouvertes
- fonctions / triggers critiques attendus en base mais non garantis par le code applicatif seul

## Modules testes

### 1. Authentification

Etat :
- `login` existe
- `logout` existe
- redirection apres login selon le role existe
- controle d'acces par role existe
- activation de compte et setup du mot de passe initial ne sont toujours pas implementes

Ce qui fonctionne :
- session demarree via `_start_authenticated_session()` dans `apps/accounts/views.py:97`
- `login_view()` appelle Supabase Auth dans `apps/accounts/views.py:153`
- `logout_view()` vide la session dans `apps/accounts/views.py:174`
- `dashboard()` route correctement selon le role dans `apps/accounts/views.py:180`

Bugs trouves :
- `activate_account_view()` ne fait qu'un `redirect("login")` : `apps/accounts/views.py:164`
- `setup_password_view()` ne fait qu'un `redirect("login")` : `apps/accounts/views.py:170`
- `PasswordSetupForm` existe mais n'est pas branche au flux reel : `apps/accounts/forms.py`
- le flag Supabase `requires_password_change` est exploitable cote services, mais aucun flux Django ne le traite jusqu'au bout

Impact :
- blocant pour l'activation initiale des comptes et le premier changement de mot de passe

### 2. Super Admin

Etat :
- dashboard OK
- CRUD utilisateurs OK en lecture statique
- CRUD medecins OK en lecture statique
- CRUD etablissements OK en lecture statique
- CRUD roles OK en lecture statique

Ce qui fonctionne :
- routes presentes dans `apps/accounts/urls.py`
- templates associes presents
- creation utilisateur et medecin reliees a Supabase Admin
- detail, edition et suppression exposes

Bugs trouves :
- l'ancien doublon `super_admin_facility_create` a ete neutralise, mais une fonction legacy inutilisee reste dans le fichier : `_legacy_super_admin_facility_create_unused` dans `apps/accounts/views.py:3754`
- `super_admin_facility_delete()` supprime directement l'etablissement sans garde metier ni gestion defensive des dependances : `apps/accounts/views.py`
- `super_admin_doctor_delete()` supprime directement le profil medecin, avec risque de casse metier si des dependances existent en base : `apps/accounts/views.py`
- plusieurs chaines restent mal encodees dans les messages utilisateurs

Verification demandee `public.users.id = auth.users.id` :
- le code suit bien cette convention a la creation utilisateur et medecin
- la contrainte DB vers `auth.users` ne peut pas etre prouvee depuis le repo seul

Verification `utilisateurs medecins non dupliques` :
- le formulaire de liaison filtre deja les comptes lies
- une vraie garantie robuste doit rester cote base avec un index/contrainte unique sur `medecins.user_id`

### 3. Admin Etablissement

Etat :
- dashboard OK
- detail etablissement OK
- invitations medecin OK
- disponibilites / calendrier / conges OK
- gestion staff OK
- patients et rendez-vous en lecture OK

Ce qui fonctionne :
- isolement par etablissement via `_get_managed_facility_for_admin()`
- invitation avec token + PIN hash + expiration
- annulation invitation OK
- activation / desactivation acces medecin OK

Bugs trouves :
- plusieurs flux supposent un seul etablissement admin principal via `.first()`, ce qui masque le cas multi-etablissements
- aucune garantie visible cote code sur l'unicite d'une liaison `medecin_id + etablissement_id`

Tables ciblees :
- `etablissements` : utilisee
- `medecin_etablissements` : utilisee
- `medecin_etablissement_invitations` : utilisee
- `personnel_etablissements` : utilisee

### 4. Medecin

Etat :
- dashboard OK
- invitations et validation PIN OK
- creation / reactivation de `medecin_etablissements` OK
- affichage des etablissements lies OK
- disponibilites / horaires / conges OK

Ce qui fonctionne :
- ouverture invitation par token
- acceptation / refus avec verification PIN
- creation ou reactivation de la liaison etablissement

Bugs trouves :
- `doctor_invitation_open()` est seulement protege par `login_required`, pas par `role_required(["medecin", "doctor"])` : `apps/accounts/views.py:2406`
- la nomenclature `medecin` / `doctor` reste mixte selon les zones du projet ; cela fonctionne partiellement, mais reste une source d'erreurs de role et de donnees

Tables ciblees :
- `medecins` : utilisee
- `medecin_etablissements` : utilisee
- `medecin_horaires_semaine` / `medecin_horaire_intervalles` : utilisees
- `medecin_indisponibilites` : utilisee
- `medecin_presences` : utilisee

### 5. Staff / Infirmier / Secretaire / Staff Frontdesk

Etat :
- dashboard staff OK pour les roles cibles
- presences medecin OK en lecture statique
- creation / recherche patient OK
- ticket patient OK en statique
- creation rendez-vous rapide OK
- calendrier rendez-vous OK

Ce qui fonctionne :
- isolement par etablissement via `_get_current_staff_facility_link()`
- permissions staff gerees via `personnel_etablissement_permissions`
- recherche patient par nom / code / barcode / email / telephone dans `staff_patient_list()`
- creation rendez-vous avec verification patient + medecin + etablissement dans `staff_appointments()`
- `staff_frontdesk` est present dans le dashboard, la navbar et les choix de role du modele

Bugs trouves :
- le ticket patient depend toujours de `win32print` pour l'impression locale Windows ; aucune strategie alternative n'est visible si le module ou l'imprimante ne sont pas disponibles
- `templates/staff/patients/detail.html` contient encore un affichage haut de fiche non harmonise : `{{ patient.patient_code }} • {{ patient.barcode_value }}` sans fallback visuel pour `patient_code`
- les permissions staff restent gerees principalement au niveau de l'etablissement lie ; un mauvais rattachement `personnel_etablissements` continuerait d'ouvrir des donnees d'un mauvais etablissement

### 6. Patients, sans profil patient

Etat :
- creation patient depuis staff OK en lecture statique
- recherche OK
- ticket patient OK
- QR / barcode OK
- pas de module profil patient ajoute, conforme a la consigne

Ce qui fonctionne maintenant :
- `patient_code` est optionnel dans le modele Django : `apps/accounts/models.py:550`
- `barcode_value` reste obligatoire et unique dans le modele Django : `apps/accounts/models.py:551`
- `PatientForm` traite `patient_code` comme `CIN / Carte nationale`
- `staff_patient_create()` n'auto-genere plus `patient_code` et genere seulement `barcode_value`
- la recherche patient staff couvre `patient_code` et `barcode_value`

Points a verifier cote base :
- la base doit aussi rendre `patients.patient_code` optionnel
- l'unicite doit etre partielle : unique seulement quand `patient_code` n'est pas `NULL`
- `barcode_value` doit etre genere cote base si absent, pas seulement cote formulaire

Conclusion :
- le code Django est aligne avec la regle metier cible
- la base doit etre alignee via `sql/required_database_fixes.sql`

### 7. Rendez-vous

Etat :
- creation staff OK en lecture statique
- liaison patient / medecin / etablissement OK
- `scheduled_end_at` renseigne cote vue
- recherche par `patient_code` et `barcode_value` ajoutee dans le flux staff

Ce qui fonctionne :
- `duration_minutes` est valide dans le formulaire
- la vue staff calcule `scheduled_end_at`
- les vues staff filtrent maintenant les rendez-vous aussi par `barcode_value`

Bugs trouves :
- le repo applicatif ne garantit pas a lui seul `scheduled_end_at` en base ; cela depend encore du SQL a appliquer
- `sql/create_appointments.sql` contient bien `check_appointment_against_indisponibilites()`, mais pas `set_appointment_end_at()` ni les triggers finaux attendus
- l'anti-chevauchement `appointments_no_overlap_for_medecin` doit encore etre confirme en base reelle

## Verification structurelle

### Routes manquantes

Aucune route nommee manquante detectee.

### Templates manquants

Aucun template manquant detecte parmi les templates appeles par les vues analysees.

### Formulaires manquants

Aucun import de formulaire manquant detecte dans `apps/accounts/views.py`.

### Modeles manquants ou incoherents

Problemes detectes :
- `MedecinIndisponibilite`, `MedecinHoraireSemaine` et `MedecinHoraireIntervalle` n'ont toujours pas `managed = False`, contrairement au reste des tables Supabase : `apps/accounts/models.py:404`, `apps/accounts/models.py:457`, `apps/accounts/models.py:496`
- `PatientVitalSign.patient` est obligatoire dans Django, alors que le script SQL courant de `patient_vital_signs` autorise encore `patient_id null`
- absence de modele `PatientEtablissement` cote Django, alors que le SQL de correction propose une table globale multi-etablissements

## Ce qui fonctionne globalement

- architecture des roles globalement bien segregee
- aucune route nommee manquante
- aucun template appele manquant
- flux super admin largement presents
- flux invitation medecin bien structures
- flux staff patient / ticket / rendez-vous deja exploitables
- logique patient cote Django maintenant alignee sur `CIN optionnel + barcode obligatoire`
- `staff_frontdesk` est bien integre au flux staff

## Bugs prioritaires a corriger

### Blocants

1. Auth initiale incomplete :
   - `activate_account_view()` et `setup_password_view()` ne sont pas implementes
2. Alignement base patients encore requis :
   - le code Django est corrige, mais la base doit encore appliquer la logique `patient_code optionnel + unique partiel + barcode auto`
3. SQL appointments incomplet tant qu'il n'est pas applique :
   - `set_appointment_end_at`, triggers de calcul et trigger anti-indisponibilites doivent etre presents en base reelle
4. Incoherence Django / SQL sur certaines tables :
   - `managed = False` manquant sur plusieurs modeles Supabase
   - `PatientVitalSign` pas totalement aligne avec le script SQL courant

### Importants

1. Securiser les suppressions super admin sur medecin et etablissement
2. Ajouter `role_required` a `doctor_invitation_open()`
3. Stabiliser la nomenclature `medecin` / `doctor`
4. Verifier et imposer l'unicite DB de `medecins.user_id`
5. Corriger les textes et messages mal encodes
6. Harmoniser l'affichage detail patient staff quand `patient_code` est vide

### Optionnels

1. Supprimer completement la fonction legacy `_legacy_super_admin_facility_create_unused`
2. Ajouter un fallback d'impression ticket hors `win32print`
3. Etendre la meme recherche `barcode_value` aux autres vues rendez-vous non staff si souhaite metierement

## Fichiers a corriger en priorite

- `apps/accounts/views.py`
- `apps/accounts/models.py`
- `sql/create_appointments.sql`
- `sql/required_database_fixes.sql`
- `sql/create_patient_vital_signs.sql`
- `templates/staff/patients/detail.html`

## Routes manquantes

- aucune

## Templates manquants

- aucun

## Modeles manquants

- `PatientEtablissement` cote Django si le patient doit etre exploite comme entite globale multi-etablissements dans l'application

## Formulaires manquants

- aucun

## Corrections prioritaires recommandees sur 2 jours

### Jour 1

- finaliser `setup_password_view()` et `activate_account_view()`
- appliquer `sql/required_database_fixes.sql` en base
- corriger `managed = False` sur les modeles Supabase restants
- ajouter `role_required` a l'ouverture d'invitation medecin

### Jour 2

- securiser les suppressions super admin
- verifier les triggers et contraintes `appointments` en base reelle
- aligner `PatientVitalSign` avec le schema SQL finalement retenu
- nettoyer les derniers textes / affichages incoherents

## Checklist finale de validation

- [ ] login fonctionnel
- [ ] logout fonctionnel
- [ ] activation de compte fonctionnelle
- [ ] changement de mot de passe initial fonctionnel
- [ ] redirection par role fonctionnelle
- [ ] acces interdit par role fonctionnel
- [ ] dashboard super admin OK
- [ ] CRUD utilisateurs OK
- [ ] CRUD medecins OK
- [ ] CRUD etablissements OK
- [ ] dashboard admin etablissement OK
- [ ] invitations medecin OK
- [ ] dashboard medecin OK
- [ ] disponibilites medecin OK
- [ ] dashboard staff pour tous les roles staff cibles OK
- [ ] creation patient OK
- [ ] recherche patient OK
- [ ] ticket patient OK
- [ ] barcode / QR patient OK
- [ ] creation rendez-vous OK
- [ ] anti-chevauchement rendez-vous OK
- [ ] blocage sur indisponibilite medecin OK
- [ ] contraintes DB alignees sur le code
