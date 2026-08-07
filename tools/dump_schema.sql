-- ==================================================================
-- Struttura completa dello schema `public`.
-- Lancialo nell'SQL Editor di Supabase e incolla il risultato:
-- e' una sola colonna di testo, gia' ordinata per sezioni.
-- Sola lettura: non modifica nulla.
-- ==================================================================
select riga from (

  -- 1. COLONNE (con identity: serve a sapere se `spese.id` si genera da sola)
  select 1 as s, table_name || lpad(ordinal_position::text, 4, '0') as k,
         'COL   ' || rpad(table_name || '.' || column_name, 46) ||
         rpad(data_type, 26) ||
         ' null=' || is_nullable ||
         ' ident=' || is_identity ||
         ' def=' || coalesce(column_default, '—') as riga
  from information_schema.columns
  where table_schema = 'public'

  union all
  -- 2. VINCOLI: chiavi, foreign key, check
  select 2, conrelid::regclass::text || conname,
         'VINC  ' || rpad(conrelid::regclass::text, 30) ||
         rpad(conname, 44) || pg_get_constraintdef(oid)
  from pg_constraint
  where connamespace = 'public'::regnamespace

  union all
  -- 3. INDICI
  select 3, tablename || indexname,
         'IDX   ' || indexdef
  from pg_indexes
  where schemaname = 'public'

  union all
  -- 4. VISTE (definizione completa)
  select 4, viewname,
         'VIEW  ' || viewname || E'\n' ||
         pg_get_viewdef(('public.' || quote_ident(viewname))::regclass, true)
  from pg_views
  where schemaname = 'public'

  union all
  -- 5. FUNZIONI
  select 5, p.proname,
         'FUNC  ' || p.proname || E'\n' || pg_get_functiondef(p.oid)
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public' and p.prokind = 'f'

  union all
  -- 6. TRIGGER
  select 6, c.relname || t.tgname,
         'TRIG  ' || pg_get_triggerdef(t.oid)
  from pg_trigger t
  join pg_class c on c.oid = t.tgrelid
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and not t.tgisinternal

  union all
  -- 7. ROW LEVEL SECURITY: attiva o no, per tabella
  select 7, c.relname,
         'RLS   ' || rpad(c.relname, 34) ||
         case when c.relrowsecurity then 'ATTIVA' else 'disattivata' end
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r'

  union all
  -- 8. POLICY RLS
  select 8, tablename || policyname,
         'POL   ' || rpad(tablename, 26) || rpad(policyname, 30) ||
         cmd || ' | using=' || coalesce(qual, '—')
  from pg_policies
  where schemaname = 'public'

) t
order by s, k;
