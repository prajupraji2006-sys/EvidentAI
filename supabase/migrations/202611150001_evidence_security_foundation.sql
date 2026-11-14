-- EvidentAI evidence analysis, authenticity, private storage, and audit foundation.
-- Apply through the Supabase SQL editor or Supabase CLI after reviewing the project.

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.evidence_analysis (
  id uuid primary key default gen_random_uuid(),
  evidence_id uuid not null unique references public.evidence(id) on delete cascade,
  analysis jsonb not null,
  extracted_text_preview text,
  extraction_method text,
  created_at timestamptz not null default now()
);

create table if not exists public.authenticity_assessments (
  id uuid primary key default gen_random_uuid(),
  evidence_id uuid not null references public.evidence(id) on delete cascade,
  classification text not null check (classification in (
    'LIKELY AUTHENTIC', 'POSSIBLY ALTERED', 'SUSPICIOUS',
    'LIKELY SYNTHETIC / AI-GENERATED', 'INCONCLUSIVE', 'INSUFFICIENT DATA'
  )),
  confidence numeric(4,3) not null check (confidence between 0 and 1),
  assessment jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists authenticity_assessments_evidence_created_idx
  on public.authenticity_assessments (evidence_id, created_at desc);

alter table public.evidence
  add column if not exists duplicate_of uuid references public.evidence(id) on delete set null;
alter table public.evidence
  add column if not exists analysis_status text not null default 'pending';
create index if not exists evidence_uploaded_by_created_idx
  on public.evidence (uploaded_by, uploaded_at desc);
create index if not exists evidence_incident_idx on public.evidence (incident_id);
create index if not exists evidence_hashes_hash_idx on public.evidence_hashes (sha256_hash);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid not null references auth.users(id) on delete restrict,
  action text not null,
  resource_type text not null,
  resource_id text,
  event_data jsonb not null,
  previous_hash text,
  current_hash text not null,
  created_at timestamptz not null,
  unique (actor_id, current_hash)
);

create index if not exists audit_logs_actor_created_idx
  on public.audit_logs (actor_id, created_at desc);

alter table public.profiles enable row level security;
alter table public.incidents enable row level security;
alter table public.evidence enable row level security;
alter table public.evidence_hashes enable row level security;
alter table public.evidence_analysis enable row level security;
alter table public.authenticity_assessments enable row level security;
alter table public.audit_logs enable row level security;

-- Replace earlier project-local policies on these application tables so a
-- permissive legacy rule cannot accidentally override the owner boundary.
do $$
declare
  existing_policy record;
begin
  for existing_policy in
    select schemaname, tablename, policyname
    from pg_policies
    where schemaname = 'public'
      and tablename in (
        'profiles', 'incidents', 'evidence', 'evidence_hashes',
        'evidence_analysis', 'authenticity_assessments', 'audit_logs'
      )
  loop
    execute format('drop policy %I on %I.%I', existing_policy.policyname, existing_policy.schemaname, existing_policy.tablename);
  end loop;
end;
$$;

drop policy if exists profiles_owner_access on public.profiles;
create policy profiles_owner_access on public.profiles
  for all to authenticated using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists incidents_owner_access on public.incidents;
create policy incidents_owner_access on public.incidents
  for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists evidence_owner_access on public.evidence;
create policy evidence_owner_access on public.evidence
  for all to authenticated
  using (uploaded_by = auth.uid() and exists (
    select 1 from public.incidents i where i.id = incident_id and i.owner_id = auth.uid()
  ))
  with check (uploaded_by = auth.uid() and exists (
    select 1 from public.incidents i where i.id = incident_id and i.owner_id = auth.uid()
  ));

drop policy if exists evidence_hashes_owner_access on public.evidence_hashes;
create policy evidence_hashes_owner_access on public.evidence_hashes
  for all to authenticated using (exists (
    select 1 from public.evidence e where e.id = evidence_id and e.uploaded_by = auth.uid()
  )) with check (exists (
    select 1 from public.evidence e where e.id = evidence_id and e.uploaded_by = auth.uid()
  ));

drop policy if exists evidence_analysis_owner_access on public.evidence_analysis;
create policy evidence_analysis_owner_access on public.evidence_analysis
  for all to authenticated using (exists (
    select 1 from public.evidence e where e.id = evidence_id and e.uploaded_by = auth.uid()
  )) with check (exists (
    select 1 from public.evidence e where e.id = evidence_id and e.uploaded_by = auth.uid()
  ));

drop policy if exists authenticity_owner_access on public.authenticity_assessments;
create policy authenticity_owner_access on public.authenticity_assessments
  for all to authenticated using (exists (
    select 1 from public.evidence e where e.id = evidence_id and e.uploaded_by = auth.uid()
  )) with check (exists (
    select 1 from public.evidence e where e.id = evidence_id and e.uploaded_by = auth.uid()
  ));

drop policy if exists audit_logs_actor_read on public.audit_logs;
create policy audit_logs_actor_read on public.audit_logs
  for select to authenticated using (actor_id = auth.uid());

insert into storage.buckets (id, name, public)
values ('evidence-files', 'evidence-files', false)
on conflict (id) do update set public = false;

drop policy if exists evidence_files_owner_read on storage.objects;
create policy evidence_files_owner_read on storage.objects
  for select to authenticated using (
    bucket_id = 'evidence-files' and (storage.foldername(name))[1] = auth.uid()::text
  );
drop policy if exists evidence_files_owner_insert on storage.objects;
create policy evidence_files_owner_insert on storage.objects
  for insert to authenticated with check (
    bucket_id = 'evidence-files' and (storage.foldername(name))[1] = auth.uid()::text
  );
drop policy if exists evidence_files_owner_update on storage.objects;
create policy evidence_files_owner_update on storage.objects
  for update to authenticated using (
    bucket_id = 'evidence-files' and (storage.foldername(name))[1] = auth.uid()::text
  ) with check (
    bucket_id = 'evidence-files' and (storage.foldername(name))[1] = auth.uid()::text
  );
drop policy if exists evidence_files_owner_delete on storage.objects;
create policy evidence_files_owner_delete on storage.objects
  for delete to authenticated using (
    bucket_id = 'evidence-files' and (storage.foldername(name))[1] = auth.uid()::text
  );

create or replace function public.append_audit_log(
  p_actor_id uuid,
  p_action text,
  p_resource_type text,
  p_resource_id text,
  p_metadata jsonb default '{}'::jsonb
) returns public.audit_logs
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  prior_hash text;
  event_time timestamptz := clock_timestamp();
  canonical_data jsonb;
  event_hash text;
  saved public.audit_logs;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_actor_id::text, 1));
  select current_hash into prior_hash
    from public.audit_logs
    where actor_id = p_actor_id
    order by created_at desc, id desc
    limit 1;

  canonical_data := jsonb_build_object(
    'actor_id', p_actor_id,
    'action', p_action,
    'resource_type', p_resource_type,
    'resource_id', p_resource_id,
    'created_at', event_time,
    'metadata', coalesce(p_metadata, '{}'::jsonb)
  );
  event_hash := encode(extensions.digest(coalesce(prior_hash, '') || canonical_data::text, 'sha256'), 'hex');

  insert into public.audit_logs (
    actor_id, action, resource_type, resource_id, event_data,
    previous_hash, current_hash, created_at
  ) values (
    p_actor_id, p_action, p_resource_type, p_resource_id, canonical_data,
    prior_hash, event_hash, event_time
  ) returning * into saved;
  return saved;
end;
$$;

revoke all on function public.append_audit_log(uuid, text, text, text, jsonb) from public, anon, authenticated;
grant execute on function public.append_audit_log(uuid, text, text, text, jsonb) to service_role;
