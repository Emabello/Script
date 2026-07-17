-- ==================================================================
-- Blocco C — Gestione fiscale
-- Da eseguire nell'SQL Editor di Supabase PRIMA del merge della PR
-- feat/gestione-fiscale.
-- ==================================================================

-- 1) Parametri fiscali (riga singola id=1)
create table if not exists b2f_parametri_fiscali (
  id                     smallint primary key default 1 check (id=1),
  regime                 text     not null default 'RF19',
  ateco                  text     not null default '622010',
  ateco_descrizione      text     default 'Attività di consulenza informatica',
  coeff_ateco            numeric(5,4) not null default 0.67,
  aliquota_imposta       numeric(5,4) not null default 0.05,     -- 5% primi 5 anni, 15% dopo
  aliquota_inps          numeric(6,4) not null default 0.2607,   -- Gestione Separata 26.07%
  aliquota_acconto       numeric(5,4) not null default 0.80,     -- 80% metodo storico (solo INPS)
  bollo_soglia           numeric(8,2) not null default 77.47,
  bollo_importo          numeric(6,2) not null default 2.00,
  limite_fatturato_anno  numeric(12,2) not null default 85000,
  data_apertura_piva     date     not null default '2026-05-28',
  anno_fine_regime_agevolato int default 2031,                  -- primo anno con aliquota 15%
  updated_at             timestamptz default now()
);

insert into b2f_parametri_fiscali (id) values (1)
  on conflict (id) do nothing;

-- 2) Spese/movimenti P.IVA (separati da `spese` personali)
create table if not exists b2f_spese_piva (
  id             bigserial primary key,
  data           date not null,
  importo        numeric(12,2) not null,
  tipo           text not null check (tipo in ('entrata','uscita','giroconto')),
  descrizione    text not null,
  categoria      text,          -- vedi CATEGORIE_SPESE_PIVA in fatture/costanti.py
  sottocategoria text,
  fattura_id     bigint references b2f_fatture(id) on delete set null,
  ricorrente     boolean default false,
  note           text,
  created_at     timestamptz default now(),
  updated_at     timestamptz default now()
);

create index if not exists idx_b2f_spese_piva_data       on b2f_spese_piva (data desc);
create index if not exists idx_b2f_spese_piva_categoria  on b2f_spese_piva (categoria);
create index if not exists idx_b2f_spese_piva_fattura    on b2f_spese_piva (fattura_id);

-- 3) Trigger updated_at (riusa la funzione b2f_touch_updated_at, già esistente
--    — vedi migration_step2.sql)
drop trigger if exists trg_b2f_parametri_updated on b2f_parametri_fiscali;
create trigger trg_b2f_parametri_updated
  before update on b2f_parametri_fiscali
  for each row execute function b2f_touch_updated_at();

drop trigger if exists trg_b2f_spese_piva_updated on b2f_spese_piva;
create trigger trg_b2f_spese_piva_updated
  before update on b2f_spese_piva
  for each row execute function b2f_touch_updated_at();

-- 4) RLS disable (l'app usa service_role, coerente con le altre tabelle b2f_*)
alter table b2f_parametri_fiscali disable row level security;
alter table b2f_spese_piva        disable row level security;

-- 5) Rinomina b2f_fatture.spesa_id -> spesa_piva_id
--    Ora il collegamento punta a b2f_spese_piva invece che a `spese` personali.
alter table b2f_fatture rename column spesa_id to spesa_piva_id;

-- 6) View aggregata annuale (comoda per dashboard ed export Excel)
--    Nota: l'acconto 80% ("metodo storico") si applica SOLO all'INPS.
--    Per l'imposta sostitutiva l'acconto è pari al 100% del saldo (nessuna
--    riduzione) — verificato sul file di riferimento fornito dall'utente.
create or replace view v_situazione_annuale as
with param as (select * from b2f_parametri_fiscali where id=1),
fatt as (
  select
    extract(year from data)::int  as anno,
    extract(month from data)::int as mese,
    sum(coalesce(totale,0))       as fatturato_mese,
    sum(coalesce(bollo,0)) filter (where bollo_addebitato)  as bollo_mese,
    count(*) filter (where stato in ('emessa','incassata')) as n_fatture
  from b2f_fatture
  where stato in ('emessa','incassata')
  group by 1, 2
),
inc as (
  select
    extract(year from data_incasso)::int  as anno,
    extract(month from data_incasso)::int as mese,
    sum(coalesce(totale,0))               as incasso_mese
  from b2f_fatture
  where stato = 'incassata' and data_incasso is not null
  group by 1, 2
),
spese as (
  select
    extract(year from data)::int  as anno,
    extract(month from data)::int as mese,
    sum(importo) filter (where categoria = 'commercialista' and tipo = 'uscita') as commercialista_mese
  from b2f_spese_piva
  group by 1, 2
)
select
  f.anno, f.mese,
  f.fatturato_mese,
  round(f.fatturato_mese * p.coeff_ateco, 2)                          as imponibile_mese,
  coalesce(i.incasso_mese, 0)                                          as incasso_mese,
  round(f.fatturato_mese * p.coeff_ateco * p.aliquota_imposta, 2)      as imposta_mese,
  round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps, 2)         as inps_saldo_mese,
  round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps * p.aliquota_acconto, 2) as inps_acconto_mese,
  coalesce(f.bollo_mese, 0)                                            as bollo_mese,
  coalesce(s.commercialista_mese, 0)                                   as commercialista_mese,
  f.n_fatture
from fatt f
cross join param p
left join inc i using (anno, mese)
left join spese s using (anno, mese)
order by f.anno, f.mese;
