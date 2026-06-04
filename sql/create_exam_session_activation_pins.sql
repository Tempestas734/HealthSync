create table if not exists public.exam_session_activation_pins (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.patients (id) on delete cascade,
  created_by_user_id uuid null references public.users (id) on delete set null,
  session_pin varchar(6) not null unique,
  status text not null default 'pending',
  exam_session_id uuid null references public.exam_sessions (id) on delete set null,
  expires_at timestamptz null,
  activated_at timestamptz null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint exam_session_activation_pins_status_check check (
    status in ('pending', 'activated', 'expired', 'cancelled')
  ),
  constraint exam_session_activation_pins_pin_digits_check check (session_pin ~ '^[0-9]{6}$')
);

create index if not exists exam_session_activation_pins_patient_idx
  on public.exam_session_activation_pins (patient_id);

create index if not exists exam_session_activation_pins_status_idx
  on public.exam_session_activation_pins (status);

create index if not exists exam_session_activation_pins_pin_idx
  on public.exam_session_activation_pins (session_pin);

drop trigger if exists trg_exam_session_activation_pins_updated_at on public.exam_session_activation_pins;
create trigger trg_exam_session_activation_pins_updated_at
before update on public.exam_session_activation_pins
for each row
execute function public.set_updated_at();
