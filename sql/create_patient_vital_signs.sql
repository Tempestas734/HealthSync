create extension if not exists pgcrypto;

alter table if exists public.patients
add column if not exists cin text null;

create table if not exists public.patient_vital_signs (
  id uuid not null default gen_random_uuid(),
  patient_id uuid null,
  etablissement_id uuid null,
  exam_session_id uuid null,
  measured_by_user_id uuid null,
  temperature_c numeric(4, 1) null,
  heart_rate_bpm integer null,
  spo2_percent integer null,
  systolic_bp integer null,
  diastolic_bp integer null,
  respiratory_rate_bpm integer null,
  weight_kg numeric(5, 2) null,
  height_cm numeric(5, 2) null,
  blood_glucose_mg_dl numeric(6, 2) null,
  measurement_source text not null default 'kiosk'::text,
  notes text null,
  measured_at timestamp with time zone not null default now(),
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint patient_vital_signs_pkey primary key (id),
  constraint patient_vital_signs_etablissement_id_fkey foreign key (etablissement_id) references public.etablissements (id) on delete set null,
  constraint patient_vital_signs_exam_session_id_fkey foreign key (exam_session_id) references public.exam_sessions (id) on delete set null,
  constraint patient_vital_signs_measured_by_user_id_fkey foreign key (measured_by_user_id) references public.users (id) on delete set null,
  constraint patient_vital_signs_patient_id_fkey foreign key (patient_id) references public.patients (id) on delete cascade,
  constraint patient_vital_signs_spo2_check check (
    spo2_percent is null
    or (spo2_percent >= 50 and spo2_percent <= 100)
  ),
  constraint patient_vital_signs_temperature_check check (
    temperature_c is null
    or (temperature_c >= 25::numeric and temperature_c <= 45::numeric)
  ),
  constraint patient_vital_signs_bp_check check (
    (
      systolic_bp is null
      and diastolic_bp is null
    )
    or (
      systolic_bp is not null
      and diastolic_bp is not null
      and systolic_bp >= 50
      and systolic_bp <= 300
      and diastolic_bp >= 30
      and diastolic_bp <= 200
      and systolic_bp > diastolic_bp
    )
  ),
  constraint patient_vital_signs_weight_check check (
    weight_kg is null
    or (weight_kg >= 1::numeric and weight_kg <= 400::numeric)
  ),
  constraint patient_vital_signs_heart_rate_check check (
    heart_rate_bpm is null
    or (heart_rate_bpm >= 20 and heart_rate_bpm <= 250)
  ),
  constraint patient_vital_signs_height_check check (
    height_cm is null
    or (height_cm >= 30::numeric and height_cm <= 250::numeric)
  ),
  constraint patient_vital_signs_respiratory_rate_check check (
    respiratory_rate_bpm is null
    or (respiratory_rate_bpm >= 5 and respiratory_rate_bpm <= 80)
  ),
  constraint patient_vital_signs_source_check check (
    measurement_source = any (
      array[
        'manual'::text,
        'kiosk'::text,
        'sensor'::text,
        'device'::text,
        'import'::text
      ]
    )
  )
);

alter table if exists public.patient_vital_signs
  add column if not exists patient_id uuid,
  add column if not exists etablissement_id uuid,
  add column if not exists exam_session_id uuid,
  add column if not exists measured_by_user_id uuid,
  add column if not exists temperature_c numeric(4, 1),
  add column if not exists heart_rate_bpm integer,
  add column if not exists spo2_percent integer,
  add column if not exists systolic_bp integer,
  add column if not exists diastolic_bp integer,
  add column if not exists respiratory_rate_bpm integer,
  add column if not exists weight_kg numeric(5, 2),
  add column if not exists height_cm numeric(5, 2),
  add column if not exists blood_glucose_mg_dl numeric(6, 2),
  add column if not exists measurement_source text,
  add column if not exists notes text,
  add column if not exists measured_at timestamp with time zone,
  add column if not exists created_at timestamp with time zone,
  add column if not exists updated_at timestamp with time zone;

alter table public.patient_vital_signs
  alter column measurement_source set default 'kiosk'::text,
  alter column measured_at set default now(),
  alter column created_at set default now(),
  alter column updated_at set default now();

update public.patient_vital_signs
set measurement_source = coalesce(nullif(measurement_source, ''), 'kiosk'),
    measured_at = coalesce(measured_at, created_at, now()),
    created_at = coalesce(created_at, now()),
    updated_at = coalesce(updated_at, now())
where measurement_source is null
   or measurement_source = ''
   or measured_at is null
   or created_at is null
   or updated_at is null;

alter table public.patient_vital_signs
  alter column measurement_source set not null,
  alter column measured_at set not null,
  alter column created_at set not null,
  alter column updated_at set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_patient_id_fkey'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_patient_id_fkey
      foreign key (patient_id) references public.patients (id) on delete cascade;
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_etablissement_id_fkey'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_etablissement_id_fkey
      foreign key (etablissement_id) references public.etablissements (id) on delete set null;
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_exam_session_id_fkey'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_exam_session_id_fkey
      foreign key (exam_session_id) references public.exam_sessions (id) on delete set null;
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_measured_by_user_id_fkey'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_measured_by_user_id_fkey
      foreign key (measured_by_user_id) references public.users (id) on delete set null;
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_spo2_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_spo2_check
      check (spo2_percent is null or (spo2_percent >= 50 and spo2_percent <= 100));
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_temperature_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_temperature_check
      check (temperature_c is null or (temperature_c >= 25::numeric and temperature_c <= 45::numeric));
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_bp_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_bp_check
      check (
        (
          systolic_bp is null
          and diastolic_bp is null
        )
        or (
          systolic_bp is not null
          and diastolic_bp is not null
          and systolic_bp >= 50
          and systolic_bp <= 300
          and diastolic_bp >= 30
          and diastolic_bp <= 200
          and systolic_bp > diastolic_bp
        )
      );
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_weight_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_weight_check
      check (weight_kg is null or (weight_kg >= 1::numeric and weight_kg <= 400::numeric));
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_heart_rate_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_heart_rate_check
      check (heart_rate_bpm is null or (heart_rate_bpm >= 20 and heart_rate_bpm <= 250));
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_height_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_height_check
      check (height_cm is null or (height_cm >= 30::numeric and height_cm <= 250::numeric));
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_respiratory_rate_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_respiratory_rate_check
      check (respiratory_rate_bpm is null or (respiratory_rate_bpm >= 5 and respiratory_rate_bpm <= 80));
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'patient_vital_signs_source_check'
  ) then
    alter table public.patient_vital_signs
      add constraint patient_vital_signs_source_check
      check (
        measurement_source = any (
          array[
            'manual'::text,
            'kiosk'::text,
            'sensor'::text,
            'device'::text,
            'import'::text
          ]
        )
      );
  end if;
end
$$;

create index if not exists patient_vital_signs_patient_id_idx
  on public.patient_vital_signs using btree (patient_id);

create index if not exists patient_vital_signs_exam_session_id_idx
  on public.patient_vital_signs using btree (exam_session_id);

create index if not exists patient_vital_signs_measured_at_idx
  on public.patient_vital_signs using btree (measured_at desc);

create index if not exists patient_vital_signs_patient_measured_at_idx
  on public.patient_vital_signs using btree (patient_id, measured_at desc);

drop function if exists public.create_vital_signs_from_session(uuid, uuid, uuid);

create function public.create_vital_signs_from_session(
  p_session_id uuid,
  p_patient_id uuid,
  p_etablissement_id uuid default null
)
returns uuid
language plpgsql
as $$
declare
  v_vital_sign_id uuid;
begin
  if p_session_id is null then
    raise exception 'session_id is required';
  end if;

  if p_patient_id is null then
    raise exception 'patient_id is required';
  end if;

  with session_measurements as (
    select
      lower(trim(m.type)) as measurement_type,
      nullif(trim(m.value::text), '')::numeric as numeric_value,
      m.measured_at,
      m.source
    from public.measurements m
    where m.session_id = p_session_id
  ),
  aggregated as (
    select
      count(*) as measurement_count,
      max(case when measurement_type = 'temperature' then numeric_value end) as temperature_c,
      max(case when measurement_type = 'heart_rate' then numeric_value end) as heart_rate_bpm,
      max(case when measurement_type = 'spo2' then numeric_value end) as spo2_percent,
      max(case when measurement_type = 'systolic_bp' then numeric_value end) as systolic_bp,
      max(case when measurement_type = 'diastolic_bp' then numeric_value end) as diastolic_bp,
      max(case when measurement_type in ('respiratory_rate', 'respiratory_rate_bpm') then numeric_value end) as respiratory_rate_bpm,
      max(case when measurement_type in ('weight', 'weight_kg') then numeric_value end) as weight_kg,
      max(case when measurement_type in ('height', 'height_cm') then numeric_value end) as height_cm,
      max(case when measurement_type in ('blood_glucose', 'blood_glucose_mg_dl', 'glucose') then numeric_value end) as blood_glucose_mg_dl,
      max(measured_at) as measured_at
    from session_measurements
  ),
  latest_source as (
    select sm.source
    from session_measurements sm
    where sm.source is not null and sm.source <> ''
    order by sm.measured_at desc nulls last
    limit 1
  )
  insert into public.patient_vital_signs (
    patient_id,
    etablissement_id,
    exam_session_id,
    temperature_c,
    heart_rate_bpm,
    spo2_percent,
    systolic_bp,
    diastolic_bp,
    respiratory_rate_bpm,
    weight_kg,
    height_cm,
    blood_glucose_mg_dl,
    measurement_source,
    measured_at,
    created_at,
    updated_at
  )
  select
    p_patient_id,
    p_etablissement_id,
    p_session_id,
    round(a.temperature_c::numeric, 1),
    a.heart_rate_bpm::integer,
    a.spo2_percent::integer,
    a.systolic_bp::integer,
    a.diastolic_bp::integer,
    a.respiratory_rate_bpm::integer,
    round(a.weight_kg::numeric, 2),
    round(a.height_cm::numeric, 2),
    round(a.blood_glucose_mg_dl::numeric, 2),
    coalesce((select source from latest_source), 'kiosk'),
    coalesce(a.measured_at, now()),
    now(),
    now()
  from aggregated a
  where a.measurement_count > 0
  on conflict do nothing
  returning id into v_vital_sign_id;

  if v_vital_sign_id is null then
    raise exception 'No measurements found for session %', p_session_id;
  end if;

  return v_vital_sign_id;
end;
$$;

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
end
$$;

do $$
begin
  if exists (
    select 1
    from pg_proc
    where proname = 'set_updated_at'
      and pg_function_is_visible(oid)
  ) and not exists (
    select 1
    from pg_trigger
    where tgname = 'trg_patient_vital_signs_updated_at'
  ) then
    create trigger trg_patient_vital_signs_updated_at
    before update on public.patient_vital_signs
    for each row
    execute function public.set_updated_at();
  end if;
end
$$;
