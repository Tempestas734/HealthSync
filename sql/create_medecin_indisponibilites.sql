create extension if not exists pgcrypto;

create table if not exists public.medecin_indisponibilites (
    id uuid primary key default gen_random_uuid(),
    medecin_id uuid not null references public.medecins (id) on delete cascade,
    etablissement_id uuid not null references public.etablissements (id) on delete cascade,
    declared_by_user_id uuid references public.users (id) on delete set null,
    type_indisponibilite text not null default 'indisponible',
    motif text not null,
    date_debut date not null,
    date_fin date not null,
    heure_debut time null,
    heure_fin time null,
    toute_la_journee boolean not null default true,
    notes text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint medecin_indisponibilites_type_check check (
        type_indisponibilite in ('absence', 'conge', 'formation', 'indisponible')
    ),
    constraint medecin_indisponibilites_dates_check check (date_fin >= date_debut),
    constraint medecin_indisponibilites_hours_check check (
        toute_la_journee = true
        or heure_debut is not null and heure_fin is not null
    )
);

create index if not exists idx_medecin_indisponibilites_medecin
    on public.medecin_indisponibilites (medecin_id, date_debut, date_fin);

create index if not exists idx_medecin_indisponibilites_etablissement
    on public.medecin_indisponibilites (etablissement_id, date_debut, date_fin);

create index if not exists idx_medecin_indisponibilites_type
    on public.medecin_indisponibilites (type_indisponibilite);
