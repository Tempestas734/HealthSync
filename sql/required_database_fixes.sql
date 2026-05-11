create extension if not exists pgcrypto;
create extension if not exists btree_gist;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  table_name text not null,
  operation text not null,
  row_id text null,
  old_data jsonb null,
  new_data jsonb null,
  changed_at timestamptz not null default now()
);

create or replace function public.audit_trigger_fn()
returns trigger
language plpgsql
as $$
begin
  insert into public.audit_logs (
    table_name,
    operation,
    row_id,
    old_data,
    new_data
  )
  values (
    tg_table_name,
    tg_op,
    coalesce(new.id, old.id)::text,
    case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) else null end,
    case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) else null end
  );

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

insert into public.roles (id, code, nom, description, created_at)
select gen_random_uuid(), payload.code, payload.nom, payload.description, now()
from (
  values
    ('super_admin', 'Super Admin', 'Administration globale'),
    ('admin_etablissement', 'Admin Etablissement', 'Administration d''un etablissement'),
    ('medecin', 'Medecin', 'Compte medecin'),
    ('doctor', 'Doctor', 'Alias legacy pour medecin'),
    ('infirmier', 'Infirmier', 'Staff infirmier'),
    ('secretaire', 'Secretaire', 'Staff secretariat'),
    ('staff_frontdesk', 'Staff Frontdesk', 'Accueil et orientation'),
    ('patient', 'Patient', 'Compte patient')
) as payload(code, nom, description)
where not exists (
  select 1
  from public.roles r
  where lower(r.code) = lower(payload.code)
);

alter table if exists public.patients
  alter column patient_code drop not null;

alter table if exists public.patients
  alter column barcode_value set not null;

do $$
begin
  if exists (
    select 1
    from pg_constraint
    where conname = 'patients_patient_code_key'
      and conrelid = 'public.patients'::regclass
  ) then
    alter table public.patients
      drop constraint patients_patient_code_key;
  end if;
end;
$$;

create unique index if not exists patients_patient_code_not_null_idx
  on public.patients (patient_code)
  where patient_code is not null;

create unique index if not exists patients_barcode_value_idx
  on public.patients (barcode_value);

create or replace function public.set_patient_defaults()
returns trigger
language plpgsql
as $$
begin
  new.patient_code = nullif(btrim(coalesce(new.patient_code, '')), '');
  new.barcode_value = nullif(btrim(coalesce(new.barcode_value, '')), '');

  if new.barcode_value is null then
    new.barcode_value := 'BC-' || to_char(now(), 'YYYYMMDDHH24MISSUS') || '-' || substr(gen_random_uuid()::text, 1, 8);
  end if;

  if tg_op = 'INSERT' then
    new.created_at = coalesce(new.created_at, now());
  end if;

  new.updated_at = coalesce(new.updated_at, now());
  return new;
end;
$$;

drop trigger if exists trg_patients_set_defaults on public.patients;
create trigger trg_patients_set_defaults
before insert or update on public.patients
for each row
execute function public.set_patient_defaults();

drop trigger if exists trg_patients_updated_at on public.patients;
create trigger trg_patients_updated_at
before update on public.patients
for each row
execute function public.set_updated_at();

create table if not exists public.patient_etablissements (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.patients (id) on delete cascade,
  etablissement_id uuid not null references public.etablissements (id) on delete cascade,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  relation_type text not null default 'primary',
  status text not null default 'active',
  created_by_user_id uuid null references public.users (id) on delete set null,
  notes text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint patient_etablissements_unique unique (patient_id, etablissement_id),
  constraint patient_etablissements_relation_type_check check (
    relation_type in ('primary', 'secondary', 'referral', 'temporary')
  ),
  constraint patient_etablissements_status_check check (
    status in ('active', 'inactive', 'archived')
  )
);

create index if not exists patient_etablissements_patient_idx
  on public.patient_etablissements (patient_id);

create index if not exists patient_etablissements_etablissement_idx
  on public.patient_etablissements (etablissement_id);

drop trigger if exists trg_patient_etablissements_updated_at on public.patient_etablissements;
create trigger trg_patient_etablissements_updated_at
before update on public.patient_etablissements
for each row
execute function public.set_updated_at();

create table if not exists public.medecin_etablissement_invitations (
  id uuid primary key default gen_random_uuid(),
  medecin_id uuid null references public.medecins (id) on delete cascade,
  medecin_email text not null,
  etablissement_id uuid not null references public.etablissements (id) on delete cascade,
  invited_by_user_id uuid null references public.users (id) on delete set null,
  role text not null default 'medecin',
  invitation_token text not null,
  pin_hash text not null,
  pin_expires_at timestamptz null,
  status text not null default 'pending',
  can_issue_prescriptions boolean not null default true,
  can_sign_documents boolean not null default true,
  accepted_at timestamptz null,
  rejected_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint medecin_etablissement_invitations_token_key unique (invitation_token),
  constraint medecin_etablissement_invitations_status_check check (
    status in ('pending', 'accepted', 'rejected', 'expired', 'cancelled')
  ),
  constraint medecin_etablissement_invitations_role_check check (
    role in ('medecin', 'chef_service', 'consultant')
  )
);

create index if not exists medecin_etablissement_invitations_email_idx
  on public.medecin_etablissement_invitations (medecin_email);

create index if not exists medecin_etablissement_invitations_etablissement_idx
  on public.medecin_etablissement_invitations (etablissement_id, status);

drop trigger if exists trg_medecin_etablissement_invitations_updated_at on public.medecin_etablissement_invitations;
create trigger trg_medecin_etablissement_invitations_updated_at
before update on public.medecin_etablissement_invitations
for each row
execute function public.set_updated_at();

alter table if exists public.personnel_etablissements
  add column if not exists can_manage_patients boolean not null default false,
  add column if not exists can_manage_appointments boolean not null default false,
  add column if not exists can_declare_presences boolean not null default false,
  add column if not exists can_view_documents boolean not null default false;

do $$
declare
  constraint_name text;
begin
  for constraint_name in
    select con.conname
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'personnel_etablissements'
      and con.contype = 'c'
      and pg_get_constraintdef(con.oid) ilike '%role%'
  loop
    execute format('alter table public.personnel_etablissements drop constraint %I', constraint_name);
  end loop;

  alter table public.personnel_etablissements
    add constraint personnel_etablissements_role_check
    check (
      role in (
        'admin',
        'medecin',
        'infirmier',
        'secretaire',
        'assistant',
        'technicien',
        'receptionniste',
        'staff_frontdesk'
      )
    );
exception
  when duplicate_object then
    null;
end;
$$;

alter table if exists public.medecin_etablissements
  add column if not exists pin_hash text null,
  add column if not exists pin_updated_at timestamptz null,
  add column if not exists actif boolean not null default true,
  add column if not exists can_issue_prescriptions boolean not null default true,
  add column if not exists can_sign_documents boolean not null default true,
  add column if not exists updated_at timestamptz not null default now();

create unique index if not exists medecin_etablissements_unique_idx
  on public.medecin_etablissements (medecin_id, etablissement_id);

create unique index if not exists medecins_user_id_unique_idx
  on public.medecins (user_id)
  where user_id is not null;

create or replace function public.set_appointment_end_at()
returns trigger
language plpgsql
as $$
begin
  if new.duration_minutes is null or new.duration_minutes <= 0 then
    raise exception 'duration_minutes must be greater than 0';
  end if;

  if new.scheduled_at is null then
    return new;
  end if;

  new.scheduled_end_at := new.scheduled_at + make_interval(mins => new.duration_minutes);
  return new;
end;
$$;

create or replace function public.check_appointment_against_indisponibilites()
returns trigger
language plpgsql
as $$
declare
  has_conflict boolean;
begin
  if new.status not in ('pending', 'confirmed', 'follow_up_planned') then
    return new;
  end if;

  select exists (
    select 1
    from public.medecin_indisponibilites mi
    where mi.medecin_id = new.medecin_id
      and mi.etablissement_id = new.etablissement_id
      and tstzrange(
            (
              (mi.date_debut::timestamp)
              + coalesce(mi.heure_debut, time '00:00')
            ) at time zone current_setting('TIMEZONE'),
            (
              case
                when mi.toute_la_journee then ((mi.date_fin + 1)::timestamp)
                else ((mi.date_fin::timestamp) + coalesce(mi.heure_fin, time '23:59:59'))
              end
            ) at time zone current_setting('TIMEZONE'),
            '[)'
          )
          &&
          tstzrange(new.scheduled_at, new.scheduled_end_at, '[)')
  )
  into has_conflict;

  if has_conflict then
    raise exception 'Le medecin est indisponible sur ce creneau.';
  end if;

  return new;
end;
$$;

alter table if exists public.appointments
  add column if not exists scheduled_end_at timestamptz,
  alter column duration_minutes set default 15,
  alter column updated_at set default now();

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'appointments_duration_minutes_check'
  ) then
    alter table public.appointments
      add constraint appointments_duration_minutes_check check (duration_minutes > 0);
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'appointments_scheduled_end_at_check'
  ) then
    alter table public.appointments
      add constraint appointments_scheduled_end_at_check check (scheduled_end_at > scheduled_at);
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'appointments_status_check'
  ) then
    alter table public.appointments
      add constraint appointments_status_check check (
        status = any (
          array[
            'pending'::text,
            'confirmed'::text,
            'cancelled'::text,
            'completed'::text,
            'no_show'::text,
            'follow_up_planned'::text
          ]
        )
      );
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'appointments_source_check'
  ) then
    alter table public.appointments
      add constraint appointments_source_check check (
        source = any (
          array[
            'mobile_app'::text,
            'web_portal'::text,
            'hospital_desk'::text
          ]
        )
      );
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'appointments_requested_by_type_check'
  ) then
    alter table public.appointments
      add constraint appointments_requested_by_type_check check (
        requested_by_type is null
        or requested_by_type = any (
          array[
            'family'::text,
            'patient'::text,
            'doctor'::text,
            'secretary'::text,
            'nurse'::text
          ]
        )
      );
  end if;
end;
$$;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'appointments_no_overlap_for_medecin'
  ) then
    alter table public.appointments
      add constraint appointments_no_overlap_for_medecin
      exclude using gist (
        medecin_id with =,
        tstzrange(scheduled_at, scheduled_end_at, '[)') with &&
      )
      where (
        status = any (
          array[
            'pending'::text,
            'confirmed'::text,
            'follow_up_planned'::text
          ]
        )
      );
  end if;
end;
$$;

create index if not exists appointments_patient_idx
  on public.appointments (patient_id);

create index if not exists appointments_medecin_idx
  on public.appointments (medecin_id);

create index if not exists appointments_etablissement_idx
  on public.appointments (etablissement_id);

create index if not exists appointments_scheduled_at_idx
  on public.appointments (scheduled_at);

drop trigger if exists trg_appointments_set_end_at on public.appointments;
create trigger trg_appointments_set_end_at
before insert or update of scheduled_at, duration_minutes on public.appointments
for each row
execute function public.set_appointment_end_at();

drop trigger if exists trg_appointments_check_indisponibilites on public.appointments;
create trigger trg_appointments_check_indisponibilites
before insert or update of scheduled_at, scheduled_end_at, duration_minutes, status, medecin_id, etablissement_id
on public.appointments
for each row
execute function public.check_appointment_against_indisponibilites();

drop trigger if exists trg_appointments_updated_at on public.appointments;
create trigger trg_appointments_updated_at
before update on public.appointments
for each row
execute function public.set_updated_at();

do $$
declare
  existing_constraint text;
begin
  select con.conname
  into existing_constraint
  from pg_constraint con
  join pg_class rel on rel.oid = con.conrelid
  join pg_namespace nsp on nsp.oid = rel.relnamespace
  join pg_attribute att on att.attrelid = rel.oid and att.attnum = any (con.conkey)
  where nsp.nspname = 'public'
    and rel.relname = 'symptoms'
    and con.contype = 'f'
    and att.attname = 'session_id'
  limit 1;

  if existing_constraint is not null and existing_constraint <> 'symptoms_session_id_fkey' then
    execute format('alter table public.symptoms drop constraint %I', existing_constraint);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'symptoms_session_id_fkey'
  ) then
    alter table public.symptoms
      add constraint symptoms_session_id_fkey
      foreign key (session_id) references public.exam_sessions (id) on delete cascade;
  end if;
end;
$$;
