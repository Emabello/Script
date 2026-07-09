-- =====================================================================
-- b2f-hub — Step 2: creazione tabelle fatturazione
-- =====================================================================
-- Da lanciare nell'SQL Editor di Supabase (progetto esistente, quello
-- che ospita la tabella `spese`).
--
-- Idempotente: puoi rilanciarlo. Le CREATE usano IF NOT EXISTS,
-- i trigger vengono ricreati.
-- =====================================================================

-- Assicura estensioni utili (di solito già presenti su Supabase)
create extension if not exists pgcrypto;


-- ---------------------------------------------------------------------
-- 1) Anagrafica del cedente (te). Riga singola con id fisso = 1.
-- ---------------------------------------------------------------------
create table if not exists b2f_emittente (
  id           smallint primary key default 1 check (id = 1),
  nome         text,
  cognome      text,
  denominazione text,          -- se opera come ditta individuale con nome commerciale
  piva         text,
  cf           text,
  regime_fisc  text default 'RF19',   -- forfettario
  indirizzo    text,
  cap          text,
  comune       text,
  provincia    text,
  nazione      text default 'IT',
  email        text,
  pec          text,
  telefono     text,
  iban         text,
  cassa_prev   text,           -- es. INPS Gestione Separata
  aliquota_cassa numeric(5,2) default 0,  -- es. 4.00 per addebito 4%
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);


-- ---------------------------------------------------------------------
-- 2) Anagrafica clienti
-- ---------------------------------------------------------------------
create table if not exists b2f_clienti (
  id            bigserial primary key,
  tipo          text not null default 'azienda'
                check (tipo in ('azienda','privato','pa','estero')),
  denominazione text,           -- se azienda/PA/estero
  nome          text,           -- se privato
  cognome       text,           -- se privato
  piva          text,
  cf            text,
  indirizzo     text,
  cap           text,
  comune        text,
  provincia     text,
  nazione       text default 'IT',
  sdi           text,           -- codice destinatario SDI (7 char) o 0000000
  pec           text,
  email         text,
  note          text,
  attivo        boolean default true,
  created_at    timestamptz default now(),
  updated_at    timestamptz default now()
);

create index if not exists idx_b2f_clienti_denominazione on b2f_clienti (denominazione);
create index if not exists idx_b2f_clienti_piva on b2f_clienti (piva);
create index if not exists idx_b2f_clienti_attivo on b2f_clienti (attivo) where attivo = true;


-- ---------------------------------------------------------------------
-- 3) Fatture emesse
-- ---------------------------------------------------------------------
create table if not exists b2f_fatture (
  id                bigserial primary key,
  anno              int  not null,
  progressivo       int  not null,
  numero            text generated always as
                    (anno::text || '/' || lpad(progressivo::text, 3, '0')) stored,
  data              date not null default current_date,
  tipo_doc          text not null default 'TD01'
                    check (tipo_doc in ('TD01','TD02','TD03','TD04','TD05',
                                        'TD06','TD16','TD17','TD18','TD19',
                                        'TD20','TD24','TD25','TD26','TD27')),
  natura_iva        text default 'N2.2',        -- per forfettario
  cliente_id        bigint references b2f_clienti(id) on delete restrict,
  cliente_snapshot  jsonb not null,             -- copia cliente al momento emissione
  righe             jsonb not null,             -- [{descrizione,qta,um,prezzo,tot}, ...]

  imponibile        numeric(12,2) not null default 0,
  bollo             numeric(12,2) not null default 0,
  bollo_addebitato  boolean not null default false,
  cassa_perc        numeric(5,2) not null default 0,   -- % INPS (0 se non addebitata)
  cassa_importo     numeric(12,2) not null default 0,
  totale            numeric(12,2) not null default 0,
  divisa            text not null default 'EUR',

  pagamento_mod     text,                       -- es. bonifico, contanti
  pagamento_cond    text,                       -- es. "30gg data fattura"
  scadenza          date,
  iban              text,

  stato             text not null default 'emessa'
                    check (stato in ('bozza','emessa','incassata','annullata')),
  data_incasso      date,
  spesa_id          bigint,                     -- link alla riga entrata su `spese`
                                                -- FK omessa: `spese` sta in altra area

  pdf_url           text,
  xml_url           text,

  note              text,
  created_at        timestamptz default now(),
  updated_at        timestamptz default now(),

  unique (anno, progressivo)
);

create index if not exists idx_b2f_fatture_data     on b2f_fatture (data desc);
create index if not exists idx_b2f_fatture_cliente  on b2f_fatture (cliente_id);
create index if not exists idx_b2f_fatture_stato    on b2f_fatture (stato);


-- ---------------------------------------------------------------------
-- 4) Trigger: aggiorna updated_at ad ogni UPDATE
-- ---------------------------------------------------------------------
create or replace function b2f_touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists trg_b2f_emittente_updated on b2f_emittente;
create trigger trg_b2f_emittente_updated
  before update on b2f_emittente
  for each row execute function b2f_touch_updated_at();

drop trigger if exists trg_b2f_clienti_updated on b2f_clienti;
create trigger trg_b2f_clienti_updated
  before update on b2f_clienti
  for each row execute function b2f_touch_updated_at();

drop trigger if exists trg_b2f_fatture_updated on b2f_fatture;
create trigger trg_b2f_fatture_updated
  before update on b2f_fatture
  for each row execute function b2f_touch_updated_at();


-- ---------------------------------------------------------------------
-- 5) Funzione: calcola il prossimo progressivo per un anno
-- ---------------------------------------------------------------------
create or replace function b2f_next_progressivo(p_anno int)
returns int language sql as $$
  select coalesce(max(progressivo), 0) + 1
  from b2f_fatture
  where anno = p_anno;
$$;


-- ---------------------------------------------------------------------
-- 6) Riga emittente iniziale (se non c'è ancora)
-- ---------------------------------------------------------------------
insert into b2f_emittente (id, nome, cognome, regime_fisc, nazione)
values (1, 'Emanuele', 'Bellotti', 'RF19', 'IT')
on conflict (id) do nothing;


-- ---------------------------------------------------------------------
-- 7) RLS: allineata alla tabella `spese` (disabilitata; protezione a
--    livello applicativo tramite PIN Flask).
--    Se in futuro vuoi RLS attive con policies, apri un altro turno.
-- ---------------------------------------------------------------------
alter table b2f_emittente disable row level security;
alter table b2f_clienti   disable row level security;
alter table b2f_fatture   disable row level security;


-- =====================================================================
-- Verifica finale
-- =====================================================================
-- select * from b2f_emittente;
-- select b2f_next_progressivo(extract(year from current_date)::int);
