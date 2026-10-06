-- Bereits angewendet (06.10.2026)
create extension if not exists vector with schema extensions;

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  onedrive_item_id text not null unique,
  fach text, path text not null, name text not null,
  etag text, last_modified timestamptz, page_count int, indexed_at timestamptz
);

create table public.pages (
  id bigint generated always as identity primary key,
  document_id uuid not null references public.documents(id) on delete cascade,
  page_number int not null,
  content text not null default '',
  figure_description text not null default '',
  image_path text,
  fts tsvector generated always as (
    to_tsvector('german', coalesce(content,'') || ' ' || coalesce(figure_description,''))
  ) stored,
  embedding extensions.vector(1024),
  unique (document_id, page_number)
);
create index pages_fts_idx on public.pages using gin (fts);
create index pages_embedding_idx on public.pages using hnsw (embedding extensions.vector_cosine_ops);
create index pages_document_idx on public.pages (document_id);
create index documents_fach_idx on public.documents (fach);
alter table public.documents enable row level security;
alter table public.pages enable row level security;
insert into storage.buckets (id, name, public) values ('pages', 'pages', false) on conflict (id) do nothing;
