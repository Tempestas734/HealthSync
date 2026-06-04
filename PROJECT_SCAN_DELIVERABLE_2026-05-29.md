# Project Scan Deliverable - HealthSync

Date: 2026-05-29
Scope: codebase scan of `d:\Health_stuff\health_api`
Type: architecture + security + maintainability + verification snapshot

## Executive Summary

HealthSync is a Django back-office application connected to Supabase Auth and a PostgreSQL database, with most business data modeled through `managed = False` tables. The project structure is coherent enough to run basic Django checks, but there are several material risks around session trust, PHI data scoping, external auth resilience, and test coverage.

Current maturity: functional prototype / early production candidate, not yet hardened.

## What Was Verified

- Repository structure scanned: Django project with one main app, `apps.accounts`
- `manage.py check --deploy`: passes
- `manage.py test`: runs but reports `0` tests
- `manage.py test apps.accounts`: test discovery fails because there is no usable test suite in the app

## Priority Findings

### P1 - Session trust is too weak for privileged access

Evidence:
- [apps/accounts/decorators.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/decorators.py:5) only checks `request.session["user_id"]`
- [apps/accounts/decorators.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/decorators.py:14) authorizes from `request.session["role"]`
- [apps/accounts/middleware.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/middleware.py:8) sets `request.user = None` if the DB user no longer exists, but does not invalidate the session
- [apps/accounts/views.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/views.py:185) `dashboard` trusts the session role directly
- [apps/accounts/views.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/views.py:3871) `super_admin` screens are protected only by the session role decorator

Impact:
- A stale or compromised session can continue to access privileged screens after user deletion, deactivation, or role change.
- This is especially serious for `super_admin` paths.

Recommendation:
- Rehydrate the current user on every protected request and deny access when the DB user is missing or inactive.
- Stop using raw session role as the authorization source of truth.
- Flush the session when the user cannot be resolved or is inactive.

### P1 - Patient vital signs are not facility-scoped in staff patient detail

Evidence:
- [apps/accounts/views.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/views.py:2047) correctly scopes the patient to the current facility
- [apps/accounts/views.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/views.py:2053) fetches `PatientVitalSign` with `filter(patient=patient)` only
- [apps/accounts/models.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/models.py:583) `PatientVitalSign` carries its own `etablissement`

Impact:
- If a patient has vitals recorded from another facility, staff can see measurements outside their facility perimeter.
- This is a PHI isolation issue.

Recommendation:
- Add `etablissement=facility` to the vital signs query unless cross-facility visibility is explicitly intended and governed.

### P1 - Login flow can hang or 500 when Supabase is slow or unavailable

Evidence:
- [apps/accounts/views.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/views.py:123) calls `requests.post(...)` during login
- The login request has no timeout and no exception handling around network failure
- By contrast, [apps/accounts/services.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/services.py:56) applies explicit timeouts for Supabase admin calls

Impact:
- Authentication availability depends on the remote service path without graceful failure.
- A transient network issue can block workers or produce server errors instead of a controlled message.

Recommendation:
- Add `timeout=10-15` and catch `requests.RequestException`.
- Return a user-safe error and log the failure.

### P2 - Invitation PIN is stored in session in cleartext

Evidence:
- [apps/accounts/views.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/views.py:1144) generates a raw PIN
- [apps/accounts/views.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/views.py:1160) stores it in `request.session["latest_invitation_pin"]`
- [templates/admin_etablissement/invitations.html](/abs/path/d:/Health_stuff/health_api/templates/admin_etablissement/invitations.html:90) displays it after redirect

Impact:
- The PIN remains in server-side session state until consumed.
- It increases exposure of a secret that is only needed once for operator display.

Recommendation:
- Prefer a one-request flash mechanism with tighter lifecycle controls, or render immediately without persisting the raw PIN beyond the response path.

### P2 - No automated tests; regression detection is effectively absent

Evidence:
- [apps/accounts/tests.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/tests.py:1) is effectively empty
- `manage.py test` returns `Found 0 test(s).`

Impact:
- Auth, permissions, and patient workflows can regress silently.
- Refactoring `views.py` is high-risk.

Recommendation:
- Start with request tests for login, role access, facility scoping, invitation acceptance, and staff permissions.

### P3 - Schema drift risk is high because core models are unmanaged

Evidence:
- Many business tables are declared with `managed = False`, for example:
- [apps/accounts/models.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/models.py:567) `patients`
- [apps/accounts/models.py](/abs/path/d:/Health_stuff/health_api/apps/accounts/models.py:616) `patient_vital_signs`
- Additional unmanaged tables exist across most of `models.py`

Impact:
- Django migrations are not the source of truth for core data structures.
- Runtime breakage is more likely after manual SQL changes or Supabase schema evolution.

Recommendation:
- Maintain schema contracts explicitly: SQL versioning, drift checks, and smoke tests against expected columns and constraints.

## Architecture Snapshot

- Framework: Django 6 + Django templates
- Auth: Supabase Auth + custom session handling + DRF bearer auth
- Data layer: PostgreSQL/Supabase, mostly unmanaged Django models
- Frontend: server-rendered templates with page-specific JS/CSS
- App layout: one large app, `apps.accounts`

## Code Health Notes

- `views.py` is very large and mixes auth, business rules, rendering, and data mutation. This increases regression probability.
- The README still describes a simpler product surface than the current codebase. The implementation now includes facility staff, invitations, availability, patients, vital signs, and appointments.
- `.env` is ignored by Git, which is correct. It is not currently tracked.

## Recommended Delivery Plan

### Sprint 1

- Fix session validation for protected routes
- Scope patient vital signs by facility
- Harden login network error handling
- Add tests for role and facility authorization

### Sprint 2

- Split `views.py` by domain: auth, super admin, staff, doctor, facilities
- Add service/repository boundaries around Supabase and high-risk mutations
- Introduce schema drift checks for unmanaged models

### Sprint 3

- Add audit logging for privileged actions: user deletion, doctor access toggles, invitation decisions
- Expand coverage around patient and appointment workflows

## Final Assessment

The project is structurally viable and passes Django deploy checks, but it is not yet sufficiently hardened for sensitive healthcare workflows. The highest-value work is not UI polish; it is authorization hardening, facility data isolation, and basic automated coverage.
