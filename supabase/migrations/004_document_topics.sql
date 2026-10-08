-- Bereits angewendet (08.10.2026)
alter table public.documents add column if not exists topics jsonb;
alter table public.documents add column if not exists lecture_date date;
