-- ===========================================================================
-- Riconciliazione del conto personale: app contro estratto WeBank
-- ===========================================================================
-- Da lanciare nell'SQL Editor di Supabase. Sono tutte query di SOLA LETTURA:
-- nessuna scrive, nessuna cancella, si possono rilanciare a volonta'.
--
-- Verificate sul database reale il 25/08/2026: la query 1 restituisce
-- esattamente il saldo mostrato dalla pagina /saldi (3.763,56), quindi
-- riproduce il calcolo dell'app e non una sua approssimazione.
--
-- IL SALDO DELL'APP E' (spese/dati.py::saldo_conto):
--
--     saldo = saldo_iniziale + entrate - uscite - risparmio dichiarato
--
--   * saldo_iniziale  = `impostazioni`, riga con `valido_dal` PIU' VECCHIA
--   * entrate/uscite  = righe di `spese` con data <= la data del confronto
--                       (le righe storiche con tipo='giroconto' contano
--                        come entrate, vedi TIPI_SEGNO in spese/dati.py)
--   * risparmio       = somma di `risparmi_periodo.effettivo_risparmio`.
--                       NON e' una riga di `spese`: e' denaro uscito dal
--                       conto verso i salvadanai Revolut.
--
-- REGOLA D'ORO PER IL CONFRONTO (imparata a caro prezzo il 14/08/2026):
-- `spese.data` mescola data contabile e data valuta. Circa 537 righe su 927
-- hanno in banca una riga di importo identico ma con data diversa di qualche
-- giorno. Chi accoppia sulla data esatta vede 555 "buchi" invece dei ~18 veri.
-- ACCOPPIARE SEMPRE CON TOLLERANZA DI +/- 7 GIORNI SULLA DATA.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. IL SALDO DELL'APP, SCOMPOSTO, A UNA DATA QUALSIASI
-- ---------------------------------------------------------------------------
-- Cambia le due costanti in cima: la data di chiusura dell'estratto e il
-- saldo che la banca dichiara a quella data. Torna lo scarto gia' calcolato.
-- Rilanciala per OGNI estratto che scarichi: cosi' si vede in quale periodo
-- lo scarto nasce, invece di guardare un solo numero finale.

with param as (
  select date '2026-08-25' as al,          -- <<< data del confronto
         3259.04::numeric   as saldo_banca -- <<< saldo dichiarato dalla banca a quella data
),
apertura as (
  select round(saldo_iniziale::numeric, 2) as v, valido_dal
    from impostazioni
   order by valido_dal asc
   limit 1
),
mov as (
  select
    coalesce(sum(case when s.tipo in ('entrata','giroconto') then abs(s.importo) end), 0) as entrate,
    coalesce(sum(case when s.tipo = 'uscita'                 then abs(s.importo) end), 0) as uscite,
    count(*) as n
  from spese s, param p
  where s.data <= p.al
),
risp as (
  select coalesce(sum(rp.effettivo_risparmio::numeric), 0) as risparmiato
    from risparmi_periodo rp, param p
   where rp.data_bonifico <= p.al
)
select
  p.al                                   as "al",
  a.valido_dal                           as "apertura valido_dal",
  a.v                                    as "apertura",
  round(m.entrate, 2)                    as "entrate",
  round(m.uscite, 2)                     as "uscite",
  round(r.risparmiato, 2)                as "risparmio dichiarato",
  m.n                                    as "righe di spese",
  round(a.v + m.entrate - m.uscite - r.risparmiato, 2)                   as "SALDO APP",
  p.saldo_banca                                                          as "SALDO BANCA",
  round(a.v + m.entrate - m.uscite - r.risparmiato - p.saldo_banca, 2)   as "SCARTO (app - banca)"
from param p, apertura a, mov m, risp r;


-- ---------------------------------------------------------------------------
-- 2. MESE PER MESE, CON SALDO PROGRESSIVO
-- ---------------------------------------------------------------------------
-- La query piu' utile di tutte: affianca ogni mese al saldo di fine mese
-- calcolato dall'app. Basta confrontare la colonna "saldo fine mese" con il
-- saldo finale di ogni estratto per capire IN QUALE MESE lo scarto nasce.
-- Il mese in cui la differenza cambia di valore e' il mese da guardare.

with apertura as (
  select round(saldo_iniziale::numeric, 2) as v
    from impostazioni order by valido_dal asc limit 1
),
m as (
  select date_trunc('month', data)::date as mese,
         coalesce(sum(case when tipo in ('entrata','giroconto') then abs(importo) end), 0) as entrate,
         coalesce(sum(case when tipo = 'uscita'                 then abs(importo) end), 0) as uscite,
         count(*) as righe
    from spese
   group by 1
),
r as (
  select date_trunc('month', data_bonifico)::date as mese,
         coalesce(sum(effettivo_risparmio::numeric), 0) as risparmio
    from risparmi_periodo
   group by 1
),
u as (
  select coalesce(m.mese, r.mese)          as mese,
         coalesce(m.righe, 0)              as righe,
         coalesce(m.entrate, 0)            as entrate,
         coalesce(m.uscite, 0)             as uscite,
         coalesce(r.risparmio, 0)          as risparmio
    from m full join r on r.mese = m.mese
)
select to_char(mese, 'YYYY-MM')                                as "mese",
       righe                                                   as "righe",
       round(entrate, 2)                                       as "entrate",
       round(uscite, 2)                                        as "uscite",
       round(risparmio, 2)                                     as "risparmio dichiarato",
       round(entrate - uscite - risparmio, 2)                  as "netto del mese",
       round((select v from apertura)
             + sum(entrate - uscite - risparmio)
               over (order by mese rows unbounded preceding), 2) as "saldo fine mese (app)"
  from u
 order by mese;


-- ---------------------------------------------------------------------------
-- 3. RIGA PER RIGA DA UNA DATA, CON PROGRESSIVO
-- ---------------------------------------------------------------------------
-- Da spuntare a mano contro l'estratto quando la query 2 ha individuato il
-- mese. Il progressivo qui e' solo dei movimenti (niente apertura, niente
-- risparmi): serve a seguire l'andamento, non a dare il saldo assoluto.

select data                                            as "data",
       tipo                                            as "tipo",
       importo                                         as "importo",
       coalesce(categoria, '(SENZA CATEGORIA)')        as "categoria",
       coalesce(metodo_pagamento, '—')                 as "metodo",
       left(coalesce(descrizione, ''), 70)             as "descrizione",
       round(sum(case when tipo = 'uscita' then -abs(importo) else abs(importo) end)
             over (order by data, id rows unbounded preceding), 2) as "progressivo"
  from v_spese
 where data >= date '2026-07-01'          -- <<< inizio del periodo da spuntare
 order by data, id;


-- ---------------------------------------------------------------------------
-- 4. EXPORT PER IL CONFRONTO AUTOMATICO
-- ---------------------------------------------------------------------------
-- "Download CSV" sul risultato di questa query: e' il file da incrociare con
-- gli estratti (accoppiamento per importo con tolleranza di 7 giorni).

select id, data, tipo, importo,
       coalesce(categoria, '')        as categoria,
       coalesce(metodo_pagamento, '') as metodo,
       coalesce(descrizione, '')      as descrizione
  from v_spese
 where data >= date '2026-07-01'          -- <<< o togli il filtro per lo storico intero
 order by data, id;


-- ---------------------------------------------------------------------------
-- 5. I TRASFERIMENTI VERSO REVOLUT: LA CAUSA PIU' PROBABILE
-- ---------------------------------------------------------------------------
-- Ogni euro uscito verso Revolut e non dichiarato in `risparmi_periodo`
-- resta nel saldo dell'app per sempre: il movimento bancario che proverebbe
-- l'uscita e' escluso apposta da `spese`. Al 30/06/2026 questo residuo
-- valeva 631,52 EUR. Le due strade (uscita registrata / risparmio
-- dichiarato) convivono, e nulla dice quale valga per quale bonifico.

-- 5a. Quello che l'app SA di aver messo via
select data_bonifico, effettivo_risparmio
  from risparmi_periodo
 order by data_bonifico;

-- 5b. I bonifici verso Revolut registrati come normali uscite
--     (se un bonifico compare qui E dentro un effettivo_risparmio,
--      viene tolto DUE volte dal saldo)
select data, tipo, importo, coalesce(categoria,'—') as categoria,
       coalesce(metodo_pagamento,'—') as metodo, descrizione
  from v_spese
 where descrizione ilike '%revolut%'
    or descrizione ilike '%risparmi%'
    or categoria   ilike '%risparmi%'
 order by data;


-- ---------------------------------------------------------------------------
-- 6. DOPPIONI SOSPETTI (stesso importo e tipo entro 3 giorni)
-- ---------------------------------------------------------------------------
-- Un movimento importato due volte alza il saldo senza lasciare traccia.
-- Attenzione ai falsi positivi: ordini permanenti e spese ricorrenti dello
-- stesso importo sono legittimi — guarda la descrizione.

select a.id as "id A", a.data as "data A", b.id as "id B", b.data as "data B",
       a.tipo, a.importo,
       left(coalesce(a.descrizione,''), 45) as "descrizione A",
       left(coalesce(b.descrizione,''), 45) as "descrizione B"
  from spese a
  join spese b on b.id > a.id
              and b.tipo = a.tipo
              and b.importo = a.importo
              and b.data between a.data - 3 and a.data + 3
 order by a.data desc;


-- ---------------------------------------------------------------------------
-- 7. RIGHE CHE SFUGGONO AI CONTROLLI
-- ---------------------------------------------------------------------------

-- 7a. Senza categoria: invisibili al budget dei risparmi (il confronto
--     `categoria not in (...)` su NULL non e' falso, e' NULL: la riga non
--     entra ne' fra le contate ne' fra le escluse)
select id, data, tipo, importo, descrizione
  from v_spese
 where categoria is null
 order by data desc;

-- 7b. Con data futura: nel saldo non entrano (data <= oggi), in lista si'
select id, data, tipo, importo, descrizione
  from spese
 where data > current_date
 order by data;

-- 7c. Con tipo 'giroconto' (righe storiche pre-migrazione 8.9): contano
--     come entrate nel saldo ma sono invisibili a v_periodi_stipendio
select id, data, tipo, importo, descrizione
  from spese
 where tipo = 'giroconto'
 order by data;

-- 7d. Il giroconto dalla P.IVA: deve esistere in banca come bonifico in
--     entrata dal conto P.IVA, di importo identico
select data, importo, descrizione
  from v_spese
 where categoria = 'Giroconto P.IVA'
 order by data;
