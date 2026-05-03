create extension if not exists pgcrypto;

create table if not exists public.medecin_horaires_semaine (
    id uuid primary key default gen_random_uuid(),
    medecin_id uuid not null references public.medecins (id) on delete cascade,
    etablissement_id uuid not null references public.etablissements (id) on delete cascade,
    weekday integer not null,
    is_active boolean not null default false,
    notes text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint medecin_horaires_semaine_weekday_check check (weekday between 0 and 6),
    constraint medecin_horaires_semaine_unique unique (medecin_id, etablissement_id, weekday)
);

create table if not exists public.medecin_horaire_intervalles (
    id uuid primary key default gen_random_uuid(),
    horaire_id uuid not null references public.medecin_horaires_semaine (id) on delete cascade,
    ordre integer not null default 1,
    heure_debut time not null,
    heure_fin time not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint medecin_horaire_intervalles_hours_check check (heure_fin > heure_debut),
    constraint medecin_horaire_intervalles_unique unique (horaire_id, ordre)
);

create index if not exists idx_medecin_horaires_semaine_medecin
    on public.medecin_horaires_semaine (medecin_id, etablissement_id, weekday);

create index if not exists idx_medecin_horaire_intervalles_horaire
    on public.medecin_horaire_intervalles (horaire_id, ordre);
