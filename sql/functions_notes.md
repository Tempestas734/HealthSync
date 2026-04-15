# Documentation des triggers et fonctions

## Tableau récapitulatif

| Nom | Rôle | Table concernée | Trigger ou non | Dépendances |
|---|---|---|---|---|
| `audit_trigger_fn` | Audit des opérations `INSERT / UPDATE / DELETE` | appointments, documents, patients, prescriptions | Trigger | table d’audit, OLD/NEW, contexte utilisateur |
| `check_appointment_against_indisponibilites` | Validation des rendez-vous contre les indisponibilités | appointments | Trigger | medecin_indisponibilites, logique métier |
| `set_appointment_end_at` | Calcule `scheduled_end_at` | appointments | Trigger | scheduled_at, duration_minutes |
| `set_updated_at` | Met à jour `updated_at` automatiquement | plusieurs tables | Trigger | colonne updated_at |
| `set_lab_request_defaults` | Définit valeurs par défaut labo | demandes_laboratoire | Trigger | logique métier |
| `set_radiology_request_defaults` | Définit valeurs par défaut radiologie | demandes_radiologie | Trigger | logique métier |
| `set_patient_defaults` | Définit valeurs par défaut patient | patients | Trigger | logique métier |
| `create_qr_for_prescription` | Génère QR code pour prescription | prescriptions | Trigger | qr_tokens |
| `set_prescription_defaults` | Définit valeurs par défaut prescription | prescriptions | Trigger | logique métier |
| `set_qr_token_defaults` | Définit valeurs par défaut QR token | qr_tokens | Trigger | logique métier |

---

## Liste simplifiée

- `audit_trigger_fn` → trigger audit insert/update/delete  
- `check_appointment_against_indisponibilites` → trigger validation rendez-vous  
- `set_appointment_end_at` → trigger calcul fin rendez-vous  
- `set_updated_at` → trigger technique updated_at  
- `set_lab_request_defaults` → trigger defaults laboratoire  
- `set_radiology_request_defaults` → trigger defaults radiologie  
- `set_patient_defaults` → trigger defaults patient  
- `create_qr_for_prescription` → trigger génération QR  
- `set_prescription_defaults` → trigger defaults prescription  
- `set_qr_token_defaults` → trigger defaults QR token  

---

## Notes

- Les rôles sont déduits des noms des fonctions.
- Pour une documentation exacte, vérifier le code PL/pgSQL associé.