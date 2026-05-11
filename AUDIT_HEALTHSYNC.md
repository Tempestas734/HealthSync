# Audit HealthSync

## Portee et methode

Audit realise en lecture statique du code Django et des scripts SQL.

Fichiers analyses :
- `apps/accounts/models.py`
- `apps/accounts/forms.py`
- `apps/accounts/views.py`
- `apps/accounts/urls.py`
- `templates/`
- `sql/`

Controles executes :
- syntaxe Python sur `models.py`, `forms.py`, `views.py` : OK
- verification des templates appeles par `render(...)` : aucun template manquant
- verification des noms d'URL utilises par `redirect(...)` et `reverse(...)` : aucune route manquante
- detection de definitions dupliquees : 1 doublon detecte

Limite importante :
- les tests runtime Django n'ont pas pu etre executes, car `django` n'est pas installe dans l'environnement courant

## Modules testes

### 1. Authentification

Etat :
- `login` existe
- `logout` existe
- redirection vers `dashboard` selon le role existe
- controle d'acces par role existe
- activation de compte et setup du mot de passe initial ne sont pas implementes

Ce qui fonctionne :
- session demarree via `_start_authenticated_session()` dans `apps/accounts/views.py:97`
- `login_view()` appelle bien Supabase Auth dans `apps/accounts/views.py:153`
- `logout_view()` vide bien la session dans `apps/accounts/views.py:174`
- `dashboard()` redirige bien l'affichage selon le role dans `apps/accounts/views.py:180`

Bugs trouves :
- `activate_account_view()` ne fait rien d'autre qu'un redirect vers `login` : `apps/accounts/views.py:162`
- `setup_password_view()` ne fait rien d'autre qu'un redirect vers `login` : `apps/accounts/views.py:168`
- `PasswordSetupForm` existe mais n'est pas utilise : `apps/accounts/forms.py:663`
- le flag Supabase `requires_password_change` est bien pose dans `services.py`, mais aucun flux Django n'exploite ce flag : `apps/accounts/services.py:53`, `apps/accounts/services.py:89`, `apps/accounts/services.py:112`

Impact :
- blocant pour l'activation de compte et le changement initial de mot de passe

### 2. Super Admin

Etat :
- dashboard OK
- CRUD utilisateurs OK
- CRUD medecins OK
- CRUD etablissements OK
- CRUD roles OK

Ce qui fonctionne :
- routes presentes dans `apps/accounts/urls.py`
- templates existants
- creation utilisateur et medecin reliees a Supabase Admin
- detail, edition, suppression exposes

Bugs trouves :
- `super_admin_facility_create` est defini deux fois : `apps/accounts/views.py:3750` et `apps/accounts/views.py:3775`
- `super_admin_facility_delete()` supprime directement l'etablissement sans garde metier ni capture d'erreur : `apps/accounts/views.py:3838`
- `super_admin_doctor_delete()` supprime directement le profil medecin, ce qui peut cascader sur les rendez-vous : `apps/accounts/views.py:4146`
- plusieurs messages contiennent du texte mal encode `Ã©` / `mÃ©decin`, signe d'un probleme d'encodage source : par exemple `apps/accounts/views.py:3760`, `apps/accounts/views.py:3843`, `apps/accounts/views.py:3848`

Verification demandee `public.users.id = auth.users.id` :
- le code suit bien cette convention a la creation utilisateur et medecin
- exemple : `AppUser.objects.create(id=auth_user_id, ...)` dans `apps/accounts/views.py:3510` et `apps/accounts/views.py:3959`
- la contrainte DB vers `auth.users` n'est pas verifiable depuis le repo seul

Verification `utilisateurs medecins non dupliques` :
- le formulaire de liaison exclut les comptes deja lies : `apps/accounts/forms.py:621`
- mais aucune contrainte DB visible dans le repo ne garantit l'unicite de `medecins.user_id`

### 3. Admin Etablissement

Etat :
- dashboard OK
- detail etablissement OK
- invitations medecin OK
- disponibilites / calendrier / conges OK
- gestion staff OK
- patients et rendez-vous en lecture OK

Ce qui fonctionne :
- isolement par etablissement via `_get_managed_facility_for_admin()` : `apps/accounts/views.py:847`
- invitation avec token + PIN hash + expiration : `apps/accounts/views.py:1120`
- annulation invitation OK : `apps/accounts/views.py:1187`
- toggle acces medecin OK

Bugs trouves :
- le code suppose un seul etablissement admin "principal" via `.first()` dans plusieurs flux, ce qui peut masquer les autres etablissements geres
- pas de garde DB visible sur l'unicite d'une liaison `medecin_id + etablissement_id`

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
- affichage etablissements lies OK
- disponibilites / horaires / conges OK

Ce qui fonctionne :
- ouverture invitation par token : `apps/accounts/views.py:2400`
- acceptation / refus avec verification PIN : `apps/accounts/views.py:2438`
- creation ou mise a jour de la liaison etablissement : `apps/accounts/views.py:2489`

Bugs trouves :
- `doctor_invitation_open()` n'est protege que par `login_required`, pas par `role_required`, meme si le flux se rattrape ensuite par recherche du profil medecin : `apps/accounts/views.py:2400`
- le role `doctor` est supporte dans certains endroits et `medecin` dans d'autres ; il faut stabiliser la nomenclature DB

Tables ciblees :
- `medecins` : utilisee
- `medecin_etablissements` : utilisee
- `medecin_horaires_semaine` / `medecin_horaire_intervalles` : utilisees
- `medecin_indisponibilites` : utilisee
- `medecin_presences` : utilisee

### 5. Staff / Infirmier / Secretaire

Etat :
- dashboard partiel
- presences medecin OK
- creation / recherche patient OK
- ticket patient OK sous Windows si `win32print` est disponible
- creation rendez-vous rapide OK
- calendrier rendez-vous OK

Ce qui fonctionne :
- isolement par etablissement via `_get_current_staff_facility_link()` : `apps/accounts/views.py:881`
- permissions staff gerees via table `personnel_etablissement_permissions`
- recherche patient par nom / code / barcode / CIN / email / telephone dans `staff_patient_list()` : `apps/accounts/views.py:1989`
- creation rendez-vous avec verification patient + medecin + etablissement : `apps/accounts/views.py:2175`

Bugs trouves :
- le dashboard ne gere que `secretaire`, `secretary`, `infirmier` ; les roles `assistant`, `receptionniste`, `technicien`, `staff_frontdesk` tombent sur `dashboard/default.html` au lieu du dashboard staff : `apps/accounts/views.py:294-443`
- `staff_frontdesk` est demande metier mais n'apparait pas dans `PersonnelEtablissement.ROLE_CHOICES` : `apps/accounts/models.py:292`
- les secretaires et receptionnistes ne recoivent pas `view_documents` dans `STAFF_ROLE_PERMISSION_MAP`, donc ils peuvent etre bloques pour l'impression du ticket patient, alors que c'est un flux coeur : `apps/accounts/views.py:59-65`, `apps/accounts/views.py:2124`
- la recherche des rendez-vous staff filtre seulement `patient__patient_code` et pas `barcode_value` ni `cin` : `apps/accounts/views.py:2224` et `apps/accounts/views.py:2236`

### 6. Patients, sans profil patient

Etat :
- creation patient depuis staff OK techniquement
- barcode / ticket / QR ticket OK
- recherche OK
- mais la logique identite patient est incoherente avec la regle metier cible

Bug metier majeur :
- le code utilise encore `patient_code` comme identifiant auto-genere obligatoire
- alors que la cible demandee est : `patient_code = CIN / carte nationale`, optionnel

Preuves :
- modele : `patient_code = models.TextField(unique=True)` : `apps/accounts/models.py:549`
- modele : `barcode_value = models.TextField(unique=True)` : `apps/accounts/models.py:550`
- nouveau champ `cin` ajoute en plus, ce qui duplique le concept identite : `apps/accounts/models.py:558`
- formulaire : `generate_patient_code()` fabrique encore un code automatique : `apps/accounts/forms.py:1068`
- vue : `staff_patient_create()` force `patient.patient_code = generated_patient_code` : `apps/accounts/views.py:2097`

Conclusion :
- blocant metier
- il faut faire de `patient_code` un champ optionnel de type CIN / carte nationale
- `barcode_value` doit rester obligatoire et genere automatiquement
- le champ `cin` devient redondant si `patient_code` porte deja le CIN

### 7. Rendez-vous

Etat :
- creation staff OK
- liaison patient / medecin / etablissement OK
- `scheduled_end_at` renseigne dans les vues
- prevention logique des indisponibilites preparee en SQL

Ce qui fonctionne :
- `duration_minutes` controle en formulaire : `apps/accounts/forms.py:1207`
- la vue staff calcule `scheduled_end_at` : `apps/accounts/views.py:2201`
- la fonction SQL `check_appointment_against_indisponibilites()` existe dans `sql/create_appointments.sql`

Bugs trouves :
- le repo ne contient pas `set_appointment_end_at()` alors qu'elle est referencee dans `sql/functions_notes.md`
- le repo ne contient pas `set_updated_at()` ni `set_patient_defaults()` ni `audit_trigger_fn()`
- `sql/create_appointments.sql` cree la fonction de controle indisponibilites, mais pas les triggers qui l'appellent
- l'exclusion `appointments_no_overlap_for_medecin` existe dans le schema SQL, mais il faut verifier sa presence reelle en base

## Verification structurelle

### Routes manquantes

Aucune route nommee manquante detectee.

### Templates manquants

Aucun template manquant detecte parmi les templates appeles par les vues analysees.

### Formulaires manquants

Aucun import de formulaire manquant detecte dans `apps/accounts/views.py`.

### Modeles manquants ou incoherents

Problemes detectes :
- `MedecinIndisponibilite`, `MedecinHoraireSemaine` et `MedecinHoraireIntervalle` n'ont pas `managed = False`, contrairement au reste des tables Supabase : `apps/accounts/models.py:403`, `apps/accounts/models.py:456`, `apps/accounts/models.py:495`
- `PatientVitalSign.patient` est obligatoire dans Django, alors que le schema SQL actuel l'autorise a `NULL`
- absence de modele `PatientEtablissement`, alors que la cible metier demande un patient global multi-etablissements

## Ce qui fonctionne globalement

- architecture des roles deja bien segregee
- aucune route nommee manquante
- aucun template appele manquant
- flux super admin largement presents
- flux invitation medecin bien structures
- staff : patient, ticket et rendez-vous deja utilisables
- logique de permissions staff plus propre via table dediee

## Bugs prioritaires a corriger

### Blocants

1. Auth initiale incomplete :
   - `activate_account_view()` et `setup_password_view()` ne sont pas implementes
2. Logique patient incoherente :
   - `patient_code` encore obligatoire et auto-genere
   - `cin` duplique la meme information metier
3. Dashboard staff incomplet :
   - `assistant`, `receptionniste`, `technicien`, `staff_frontdesk` ne tombent pas sur le bon dashboard
4. SQL appointments incomplet :
   - fonctions/triggers techniques manquants (`set_appointment_end_at`, `set_updated_at`, `set_patient_defaults`, `audit_trigger_fn`)

### Importants

1. Doublon de fonction `super_admin_facility_create`
2. `managed = False` manquant sur plusieurs modeles SQL existants
3. Impression ticket potentiellement bloquee pour `secretaire` / `receptionniste`
4. Suppressions super admin trop agressives sur etablissement et medecin
5. Pas de contrainte DB visible sur l'unicite `medecins.user_id`

### Optionnels

1. Harmoniser `medecin` vs `doctor`
2. Corriger les textes mal encodes
3. Etendre les filtres rendez-vous staff a `barcode_value` et `cin`

## Fichiers a corriger en priorite

- `apps/accounts/views.py`
- `apps/accounts/forms.py`
- `apps/accounts/models.py`
- `sql/create_appointments.sql`
- `sql/create_patient_vital_signs.sql`
- `sql/required_database_fixes.sql`

## Routes manquantes

- aucune

## Templates manquants

- aucun

## Modeles manquants

- `PatientEtablissement` si le patient doit devenir global multi-etablissements

## Formulaires manquants

- aucun

## Corrections prioritaires recommandees sur 2 jours

### Jour 1

- finaliser `setup_password_view()` et `activate_account_view()`
- corriger la logique `patient_code` / `barcode_value`
- brancher les roles staff manquants sur le dashboard staff
- supprimer le doublon `super_admin_facility_create`

### Jour 2

- aligner les modeles Django sur Supabase avec `managed = False`
- appliquer `sql/required_database_fixes.sql`
- securiser les suppressions super admin
- verifier les triggers `appointments`

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
