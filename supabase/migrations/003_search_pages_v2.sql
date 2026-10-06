-- Hybride Suche: deutscher Volltext + Vektor, kombiniert per Reciprocal Rank Fusion
drop function if exists public.search_pages(text, extensions.vector, text, int);

create function public.search_pages(
  query_text text,
  query_embedding extensions.vector(1024) default null,
  fach_filter text default null,
  match_count int default 12
)
returns table (
  page_id bigint, document_id uuid, fach text, path text, name text, web_url text,
  page_number int, image_path text, content text, figure_description text, score double precision
)
language sql stable security invoker
set search_path = public, extensions
as $$
  with q as (select websearch_to_tsquery('german', coalesce(query_text,'')) as tsq),
  ft as (
    select p.id, row_number() over (order by ts_rank_cd(p.fts, q.tsq) desc) as r
    from pages p join documents d on d.id = p.document_id, q
    where p.fts @@ q.tsq and (fach_filter is null or d.fach = fach_filter)
    order by ts_rank_cd(p.fts, q.tsq) desc
    limit 50
  ),
  vec as (
    select p.id, row_number() over (order by p.embedding <=> query_embedding) as r
    from pages p join documents d on d.id = p.document_id
    where query_embedding is not null and p.embedding is not null
      and (fach_filter is null or d.fach = fach_filter)
    order by p.embedding <=> query_embedding
    limit 50
  ),
  fused as (
    select coalesce(ft.id, vec.id) as id,
           coalesce(1.0/(60+ft.r),0) + coalesce(1.0/(60+vec.r),0) as score
    from ft full outer join vec on ft.id = vec.id
  )
  select p.id, d.id, d.fach, d.path, d.name, d.web_url, p.page_number, p.image_path,
         left(p.content, 1500), left(p.figure_description, 800), f.score
  from fused f
  join pages p on p.id = f.id
  join documents d on d.id = p.document_id
  order by f.score desc
  limit match_count;
$$;
revoke execute on function public.search_pages(text, extensions.vector, text, int) from public, anon, authenticated;
grant execute on function public.search_pages(text, extensions.vector, text, int) to service_role;
