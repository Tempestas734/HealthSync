# HealthSync

HealthSync est une plateforme web de gestion sante construite avec Django. L'application centralise l'authentification, l'administration des utilisateurs, la gestion des medecins et le suivi des etablissements de sante dans une interface web orientee back-office.

Le projet s'appuie sur Django pour le framework web, Supabase pour l'authentification et PostgreSQL pour la persistence des donnees. Il est pense pour des environnements de clinique, cabinet ou structure medicale qui ont besoin d'un espace d'administration clair et extensible.

## Overview

HealthSync fournit une base solide pour un systeme de gestion medicale avec :

- une authentification connectee a Supabase
- un dashboard adapte au role de l'utilisateur
- une administration centralisee par `super_admin`
- une gestion des medecins, des etablissements et des comptes utilisateurs
- une architecture Django simple a faire evoluer

## Main Features

### Authentication

- connexion via email et mot de passe
- gestion de session cote serveur
- deconnexion securisee
- controle d'acces par role

### Role-Based Dashboards

L'interface affiche un tableau de bord different selon le profil connecte :

- `super_admin`
- `medecin`
- `secretaire`
- `patient`

Le dashboard `super_admin` expose des statistiques globales, les derniers utilisateurs, les derniers medecins et les etablissements recents.

### Super Admin Back Office

Le back-office permet au `super_admin` de gerer les principales entites du systeme :

- utilisateurs : liste, recherche, creation, modification, detail et suppression
- medecins : liste, filtre, creation, modification, detail et suppression
- etablissements : liste, filtre, creation, modification, detail et suppression

## Tech Stack

- Backend : Django
- API/Auth integration : Supabase
- Database : PostgreSQL
- Frontend rendering : Django Templates
- Environment management : `python-dotenv`

## Project Structure

```text
health_api/
|-- apps/
|   `-- accounts/
|       |-- views.py
|       |-- urls.py
|       |-- forms.py
|       |-- models.py
|       `-- management/commands/runserver_nodb.py
|-- config/
|   |-- settings.py
|   `-- urls.py
|-- templates/
|-- static/
|-- manage.py
|-- requirements.txt
`-- runserver.bat
```

## Local Setup

### 1. Create the virtual environment

```powershell
python -m venv .health
```

### 2. Activate it

```powershell
.\.health\Scripts\activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

## Environment Configuration

Create a `.env` file from `.env.example`, then provide your Supabase and database values.

Example:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_or_publishable_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=your_password
SUPABASE_DB_HOST=your_db_host
SUPABASE_DB_PORT=5432
SUPABASE_DB_SSLMODE=require
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
TIME_ZONE=Africa/Casablanca
```

## Run The Project

On Windows, use:

```powershell
.\runserver.bat
```

This launcher:

- uses `.health\Scripts\python.exe` when available
- falls back to `py` or `python`
- starts Django with the custom command `runserver_nodb`

`runserver_nodb` skips the startup migration database check so the development server can boot more reliably when the remote database is temporarily unreachable. Pages and actions that query the database still require a valid Supabase/PostgreSQL connection.

Manual alternative:

```powershell
.\.health\Scripts\python.exe manage.py runserver_nodb 127.0.0.1:8000 --skip-checks
```

## Available Routes

Main routes currently exposed by the project:

- `/admin/`
- `/api/auth/login/`
- `/api/auth/logout/`
- `/api/auth/dashboard/`
- `/api/auth/super-admin/doctors/`
- `/api/auth/super-admin/facilities/`
- `/api/auth/super-admin/users/`

## GitHub

The repository is prepared for GitHub with:

- a `.gitignore` adapted for Python and Django
- a `requirements.txt` file for dependency installation
- a `.env.example` file for secure configuration setup

Standard commands:

```powershell
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

If Git shows a `dubious ownership` warning on Windows:

```powershell
git config --global --add safe.directory D:/Health_stuff/health_api
```

## Vision

HealthSync is designed as a clean foundation for a broader healthcare platform. It can be extended to support appointments, patient records, prescriptions, billing, notifications, and richer role workflows while keeping the current administrative core intact.
