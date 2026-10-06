-- Bereits angewendet (06.10.2026)
create table public.app_settings (key text primary key, value text not null, updated_at timestamptz not null default now());
alter table public.app_settings enable row level security;
alter table public.documents add column web_url text;
alter table public.documents add column content_tag text;
alter table public.documents add column source text not null default 'onedrive';

create or replace function public.list_faecher()
returns table (fach text, dokumente bigint, seiten bigint)
language sql stable security invoker set search_path = public
as $$
  select d.fach, count(distinct d.id), coalesce(sum(d.page_count),0)::bigint
  from documents d group by d.fach order by d.fach;
$$;
revoke execute on function public.list_faecher() from public, anon, authenticated;
