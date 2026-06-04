create table public.exam_sessions (
  id uuid not null default gen_random_uuid (),
  created_at timestamp with time zone not null default now(),
  device_id text not null,
  consent_id uuid not null,
  user_id uuid null,
  rfid_tag_uid text null,
  status text not null default 'active'::text,
  patient_id uuid null,
  family_id uuid null,
  family_member_id uuid null,
  session_pin text null,
  constraint exam_sessions_pkey primary key (id),
  constraint exam_sessions_consent_id_fkey foreign key (consent_id) references consents (id) on delete restrict,
  constraint exam_sessions_family_id_fkey foreign key (family_id) references families (id) on delete set null,
  constraint exam_sessions_family_member_id_fkey foreign key (family_member_id) references family_members (id) on delete set null,
  constraint exam_sessions_patient_id_fkey foreign key (patient_id) references patients (id) on delete set null
) tablespace pg_default;

create index if not exists exam_sessions_patient_idx on public.exam_sessions using btree (patient_id) tablespace pg_default;

create index if not exists exam_sessions_family_idx on public.exam_sessions using btree (family_id) tablespace pg_default;

create index if not exists exam_sessions_family_member_idx on public.exam_sessions using btree (family_member_id) tablespace pg_default;

create index if not exists exam_sessions_session_pin_idx on public.exam_sessions using btree (session_pin) tablespace pg_default;

create unique index if not exists exam_sessions_active_session_pin_unique on public.exam_sessions using btree (session_pin) tablespace pg_default
where
  (
    (status = 'active'::text)
    and (session_pin is not null)
  );

drop trigger if exists trg_generate_exam_session_pin on public.exam_sessions;
create trigger trg_generate_exam_session_pin before insert on public.exam_sessions for each row
execute function public.generate_exam_session_pin ();
