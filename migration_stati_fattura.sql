-- ==================================================================
-- Ciclo di vita della fattura + dati dello studio
--
-- Contesto: il documento prodotto dall'app non e' la fattura
-- elettronica. E' il facsimile che viene mandato allo studio, che poi
-- predispone e trasmette l'XML allo SDI (accordo del 5 agosto 2026).
-- Gli stati devono rispecchiare quel passaggio di mano, perche' e' il
-- momento oltre il quale il documento non e' piu' modificabile.
--
-- DA ESEGUIRE nell'SQL Editor di Supabase.
-- Idempotente: puoi rilanciarlo.
-- ==================================================================

-- ------------------------------------------------------------------
-- 1) Nuovi stati
--    bozza -> inviata_studio -> trasmessa_sdi -> incassata
--    piu' annullata.
--    Il vecchio 'emessa' diventa 'inviata_studio': significava
--    esattamente "e' uscita dalle mie mani".
-- ------------------------------------------------------------------

-- Il vincolo va allentato prima di poter riscrivere i dati.
alter table b2f_fatture drop constraint if exists b2f_fatture_stato_check;

update b2f_fatture set stato = 'inviata_studio' where stato = 'emessa';

alter table b2f_fatture
  add constraint b2f_fatture_stato_check
  check (stato in ('bozza', 'inviata_studio', 'trasmessa_sdi',
                   'incassata', 'annullata'));

alter table b2f_fatture alter column stato set default 'bozza';


-- ------------------------------------------------------------------
-- 2) Date dei passaggi di stato
--    Senza queste, "trasmessa" e' un'etichetta senza storia: non sai
--    quando e' successo ne' quanto e' rimasta ferma.
-- ------------------------------------------------------------------

alter table b2f_fatture
  add column if not exists data_invio_studio      date,
  add column if not exists data_trasmissione_sdi  date,

  -- Predisposto ma non ancora usato dall'app: serve solo se un giorno
  -- si scopre che lo studio rinumera in fase di trasmissione. Finche'
  -- il numero e' quello dell'app, resta vuoto.
  add column if not exists numero_sdi             text;

-- Le fatture gia' inviate non hanno una data di invio registrata:
-- si usa la data del documento, che e' l'approssimazione onesta.
update b2f_fatture
   set data_invio_studio = data
 where stato in ('inviata_studio', 'trasmessa_sdi', 'incassata')
   and data_invio_studio is null;


-- ------------------------------------------------------------------
-- 3) Chi predispone e trasmette
--    Compare in fondo al facsimile, cosi' il documento dice da solo
--    di chi e' il pezzo successivo. Se restano vuoti il PDF usa una
--    dicitura generica.
-- ------------------------------------------------------------------

alter table b2f_emittente
  add column if not exists studio_nome   text,
  add column if not exists studio_email  text;

-- Valori dal carteggio. Cambiali dalla pagina /fatture/emittente.
update b2f_emittente
   set studio_nome  = coalesce(studio_nome,  'Studio Bagaglia'),
       studio_email = coalesce(studio_email, 'amministrazione@studiobagaglia.it')
 where id = 1;


-- ------------------------------------------------------------------
-- 4) Indice sullo stato: lo storico filtra spesso per stato
-- ------------------------------------------------------------------
drop index if exists idx_b2f_fatture_stato;
create index if not exists idx_b2f_fatture_stato on b2f_fatture (stato);


-- ==================================================================
-- Verifica
-- ==================================================================
-- select stato, count(*) from b2f_fatture group by stato;
-- select numero, stato, data, data_invio_studio, data_trasmissione_sdi,
--        data_incasso from b2f_fatture order by anno desc, progressivo desc;
-- select studio_nome, studio_email from b2f_emittente where id = 1;
