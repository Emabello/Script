-- ==================================================================
-- 1) v_situazione_annuale riallineata
-- 2) Row Level Security sulle tabelle rimaste scoperte
--
-- DA ESEGUIRE nell'SQL Editor di Supabase.
-- Idempotente: puoi rilanciarlo.
-- ==================================================================


-- ==================================================================
-- 1) VISTA v_situazione_annuale
--
-- Era rimasta indietro su due punti, entrambi silenziosi:
--
--   a) filtrava  stato in ('emessa', 'incassata').  Dopo la migrazione
--      del ciclo di vita 'emessa' non esiste piu' (e' diventato
--      'inviata_studio') e il vincolo di tabella lo vieta: la vista
--      vedeva quindi le sole incassate, sottostimando il fatturato.
--
--   b) calcolava  imposta = imponibile x aliquota.  L'imposta
--      sostitutiva si applica al reddito al netto dei contributi INPS,
--      che sono deducibili: imposta = (imponibile - INPS) x aliquota.
--      E' la stessa correzione gia' fatta nell'app e nell'export Excel.
--
-- L'app non usa questa vista (calcola in Python), ma chi la interroga
-- da Supabase deve leggere gli stessi numeri.
-- ==================================================================

create or replace view v_situazione_annuale as
with param as (
  select * from b2f_parametri_fiscali where id = 1
),
fatt as (
  select
    extract(year  from data)::int as anno,
    extract(month from data)::int as mese,
    sum(coalesce(totale, 0))                                as fatturato_mese,
    sum(coalesce(bollo, 0)) filter (where bollo_addebitato) as bollo_mese,
    count(*)                                                as n_fatture
  from b2f_fatture
  -- Stati che concorrono al fatturato: la bozza non e' ancora un
  -- documento, l'annullata non conta piu'.
  where stato in ('inviata_studio', 'trasmessa_sdi', 'incassata')
  group by 1, 2
),
inc as (
  select
    extract(year  from data_incasso)::int as anno,
    extract(month from data_incasso)::int as mese,
    sum(coalesce(totale, 0)) as incasso_mese
  from b2f_fatture
  where stato = 'incassata' and data_incasso is not null
  group by 1, 2
),
spese as (
  select
    extract(year  from data)::int as anno,
    extract(month from data)::int as mese,
    sum(importo) filter (
      where categoria = 'commercialista' and tipo = 'uscita'
    ) as commercialista_mese
  from b2f_spese_piva
  group by 1, 2
)
select
  f.anno,
  f.mese,
  f.fatturato_mese,
  round(f.fatturato_mese * p.coeff_ateco, 2) as imponibile_mese,
  coalesce(i.incasso_mese, 0)                as incasso_mese,
  -- (imponibile - INPS) x aliquota, cioe'
  -- imponibile x (1 - aliquota_inps) x aliquota_imposta
  round(f.fatturato_mese * p.coeff_ateco
        * (1 - p.aliquota_inps) * p.aliquota_imposta, 2) as imposta_mese,
  round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps, 2) as inps_saldo_mese,
  round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps
        * p.aliquota_acconto, 2)                              as inps_acconto_mese,
  coalesce(f.bollo_mese, 0)          as bollo_mese,
  coalesce(s.commercialista_mese, 0) as commercialista_mese,
  f.n_fatture
from fatt f
cross join param p
left join inc   i using (anno, mese)
left join spese s using (anno, mese)
order by f.anno, f.mese;


-- ==================================================================
-- 2) ROW LEVEL SECURITY
--
-- Come stanno le cose. L'app si collega con la chiave service_role, che
-- bypassa la RLS: per lei non cambia nulla. La chiave anon invece NON e'
-- un segreto (nasce per stare nei client) e su una tabella con RLS
-- disattivata permette lettura E scrittura a chiunque la conosca.
--
-- b2f_fatture, b2f_clienti e b2f_emittente hanno gia' RLS attiva senza
-- policy: nessuno entra tranne l'app. E' la configurazione giusta, e
-- qui sotto viene estesa alle tabelle rimaste scoperte.
--
-- Non servono policy permissive: aggiungerle riaprirebbe l'accesso che
-- stiamo chiudendo.
-- ==================================================================

-- --- Tabelle della sola app B2F: nessun altro client le tocca --------
alter table b2f_webauthn_credentials enable row level security;  -- credenziali biometriche
alter table b2f_spese_piva           enable row level security;  -- movimenti P.IVA
alter table b2f_parametri_fiscali    enable row level security;  -- parametri fiscali


-- --- Tabelle del sistema personale preesistente ----------------------
-- ATTENZIONE, LEGGI PRIMA DI TOGLIERE I COMMENTI.
--
-- `spese`, `risparmi_periodo` e le cfg_* nascono dal tuo sistema di
-- gestione personale, non da questa app. Se qualcosa oltre a questa app
-- le legge con la chiave anon — un foglio, una dashboard, un altro
-- frontend — attivare la RLS lo lascia fuori all'istante.
--
-- L'indizio che qualcosa lo faccia c'e': cfg_categorie,
-- cfg_sottocategorie e cfg_categoria_sottocategoria hanno gia' RLS
-- attiva con una policy "Allow read ... using (true)", che serve
-- proprio a farle leggere con la chiave anon.
--
-- Togli i commenti solo dopo aver verificato che nient'altro le usi.
--
-- alter table spese            enable row level security;
-- alter table risparmi_periodo enable row level security;


-- ==================================================================
-- Verifica
-- ==================================================================
-- select c.relname,
--        case when c.relrowsecurity then 'ATTIVA' else 'DISATTIVATA' end as rls
--   from pg_class c join pg_namespace n on n.oid = c.relnamespace
--  where n.nspname = 'public' and c.relkind = 'r'
--  order by c.relrowsecurity, c.relname;
--
-- select * from v_situazione_annuale order by anno desc, mese;
