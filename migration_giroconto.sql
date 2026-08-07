-- ==================================================================
-- Accantonamento deciso + giroconto P.IVA -> personale
--
-- Contesto: quando una fattura viene incassata, i soldi arrivano sul
-- conto P.IVA. Una parte non e' tua (INPS + imposta, piu' costi e
-- margine): quella resta li'. Il resto si sposta sul conto personale.
--
-- Finora la scelta dello scenario era solo visiva: si poteva premere
-- "minimo/consigliato/sicuro" ma non restava traccia di cosa avessi
-- deciso, ne' il denaro si muoveva. Queste colonne registrano la
-- decisione e collegano i due movimenti che la realizzano.
--
-- AUTOSUFFICIENTE: include le colonne di migration_accantonamento.sql,
-- che sul database di produzione non risultavano ancora applicate. Se
-- l'hai gia' eseguita non succede nulla, sono tutte "if not exists".
--
-- DA ESEGUIRE nell'SQL Editor di Supabase.
-- Idempotente: puoi rilanciarlo.
-- ==================================================================

-- ------------------------------------------------------------------
-- 1) Parametri di accantonamento
--    Erano previsti da migration_accantonamento.sql ma la tabella non
--    li aveva: senza, l'app funziona sui valori di default scritti nel
--    codice e la pagina /fatture/parametri non riesce a salvare.
-- ------------------------------------------------------------------

alter table b2f_parametri_fiscali
  -- Cuscinetto relativo sul dovuto. 0,10 = accantona il 10 % in piu'
  -- del conto matematico.
  add column if not exists margine_sicurezza numeric(5,4) not null default 0.10,

  -- Costi fissi annui della P.IVA: commercialista, PEC, bolli,
  -- commissioni. Non sono tasse, ma escono dagli stessi soldi.
  add column if not exists costi_fissi_annui numeric(12,2) not null default 0,

  -- Fatturato atteso dell'anno, su cui spalmare i costi fissi. A zero,
  -- l'app li spalma sull'incassato effettivo dell'anno in corso.
  add column if not exists fatturato_atteso_anno numeric(12,2) not null default 0,

  -- Acconto dell'imposta sostitutiva: 1,00 = 100 % del saldo, nessuna
  -- riduzione. A differenza dell'INPS, che va all'80 %.
  add column if not exists acconto_imposta_perc numeric(5,4) not null default 1.00,

  -- Scenario mostrato per primo: minimo | consigliato | prudente | sicuro
  add column if not exists scenario_preferito text not null default 'consigliato';


-- ------------------------------------------------------------------
-- 2) Nuovo scenario "prudente"
--    Fra consigliato (~22 %) e sicuro (~36 %) c'era un salto troppo
--    grande. "Prudente" copre il dovuto piu' meta' degli acconti
--    (~30 %): ci si arriva in due anni invece che in uno.
-- ------------------------------------------------------------------

alter table b2f_parametri_fiscali
  drop constraint if exists b2f_parametri_scenario_valido;

alter table b2f_parametri_fiscali
  add constraint b2f_parametri_scenario_valido
  check (scenario_preferito in ('minimo', 'consigliato', 'prudente', 'sicuro'));


-- ------------------------------------------------------------------
-- 3) La decisione di accantonamento, sulla fattura
--    Si registra sulla fattura e non altrove perche' e' li' che nasce:
--    ogni incasso ha la sua quota, con lo scenario scelto in quel
--    momento. Cambiare i parametri dopo non deve riscrivere la storia.
-- ------------------------------------------------------------------

alter table b2f_fatture
  -- Scenario scelto al momento del giroconto. NULL = non ancora deciso.
  add column if not exists accantonamento_scenario text,

  -- Quota rimasta sul conto P.IVA per tasse, costi e margine.
  add column if not exists accantonamento_importo numeric(12,2),

  -- Quota spostata sul conto personale (lordo - accantonamento).
  add column if not exists giroconto_importo numeric(12,2),

  -- Quando e' stato fatto lo spostamento.
  add column if not exists data_giroconto date,

  -- I due movimenti che realizzano lo spostamento. Servono per poterlo
  -- annullare senza lasciare righe orfane sui due conti.
  add column if not exists giroconto_piva_id bigint
    references b2f_spese_piva(id) on delete set null,

  -- Riga sulla tabella `spese` (conto personale). Niente foreign key:
  -- `spese` e' preesistente all'app e non ne governiamo lo schema.
  add column if not exists giroconto_personale_id bigint;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'b2f_fatture_scenario_valido'
  ) then
    alter table b2f_fatture
      add constraint b2f_fatture_scenario_valido
      check (accantonamento_scenario is null
             or accantonamento_scenario in ('minimo', 'consigliato',
                                            'prudente', 'sicuro'));
  end if;
end $$;

-- Ritrovare in fretta le fatture incassate ma non ancora girocontate.
create index if not exists idx_b2f_fatture_da_girocontare
  on b2f_fatture (stato) where data_giroconto is null;


-- ==================================================================
-- Verifica
-- ==================================================================
-- select margine_sicurezza, costi_fissi_annui, scenario_preferito
--   from b2f_parametri_fiscali where id = 1;
--
-- select numero, stato, totale, accantonamento_scenario,
--        accantonamento_importo, giroconto_importo, data_giroconto
--   from b2f_fatture order by anno desc, progressivo desc;
