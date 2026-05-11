create extension if not exists pgcrypto;
create extension if not exists btree_gist;

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

create table if not exists public.appointments (
  id uuid not null default gen_random_uuid(),
  patient_id uuid not null,
  medecin_id uuid not null,
  etablissement_id uuid not null,
  scheduled_at timestamp with time zone not null,
  status text not null default 'pending',
  reason text null,
  notes text null,
  created_by_user_id uuid null,
  requested_by_type text null,
  requested_by_id uuid null,
  source text not null default 'web_portal',
  follow_up_of_appointment_id uuid null,
  cancelled_by_user_id uuid null,
  cancel_reason text null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  duration_minutes integer not null default 15,
  scheduled_end_at timestamp with time zone not null,
  constraint appointments_pkey primary key (id),
  constraint appointments_created_by_user_id_fkey foreign key (created_by_user_id) references users (id) on delete set null,
  constraint appointments_patient_id_fkey foreign key (patient_id) references patients (id) on delete cascade,
  constraint appointments_follow_up_of_appointment_id_fkey foreign key (follow_up_of_appointment_id) references appointments (id) on delete set null,
  constraint appointments_medecin_id_fkey foreign key (medecin_id) references medecins (id) on delete cascade,
  constraint appointments_cancelled_by_user_id_fkey foreign key (cancelled_by_user_id) references users (id) on delete set null,
  constraint appointments_etablissement_id_fkey foreign key (etablissement_id) references etablissements (id) on delete cascade,
  constraint appointments_status_check check (
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
  ),
  constraint appointments_duration_minutes_check check (duration_minutes > 0),
  constraint appointments_requested_by_type_check check (
    (requested_by_type is null)
    or (
      requested_by_type = any (
        array[
          'family'::text,
          'patient'::text,
          'doctor'::text,
          'secretary'::text,
          'nurse'::text
        ]
      )
    )
  ),
  constraint appointments_scheduled_end_at_check check (scheduled_end_at > scheduled_at),
  constraint appointments_source_check check (
    source = any (
      array[
        'mobile_app'::text,
        'web_portal'::text,
        'hospital_desk'::text
      ]
    )
  ),
  constraint appointments_no_overlap_for_medecin exclude using gist (
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
  )
);

create index if not exists appointments_patient_idx on public.appointments using btree (patient_id);
create index if not exists appointments_medecin_idx on public.appointments using btree (medecin_id);
create index if not exists appointments_etablissement_idx on public.appointments using btree (etablissement_id);
create index if not exists appointments_scheduled_at_idx on public.appointments using btree (scheduled_at);
