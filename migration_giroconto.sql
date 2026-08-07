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
-- DA ESEGUIRE nell'SQL Editor di Supabase.
-- Idempotente: puoi rilanciarlo.
-- ==================================================================

-- ------------------------------------------------------------------
-- 1) Nuovo scenario "prudente"
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
-- 2) La decisione di accantonamento, sulla fattura
--    Si registra sulla fattura e non altrove perche' e' li' che nasce:
--    ogni incasso ha la sua quota, con lo scenario scelto in quel
--    momento. Cambiare i parametri dopo non deve riscrivere la storia.
-- ------------------------------------------------------------------

alter table b2f_fatture
  -- Scenario scelto al momento del giroconto: minimo | consigliato |
  -- prudente | sicuro. NULL = non ancora deciso.
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

-- Ritrovare in fretta le fatture incassate ma non ancora girocontate:
-- e' la lista di lavoro della pagina "da sistemare".
create index if not exists idx_b2f_fatture_da_girocontare
  on b2f_fatture (stato) where data_giroconto is null;


-- ==================================================================
-- Verifica
-- ==================================================================
-- select numero, stato, totale, accantonamento_scenario,
--        accantonamento_importo, giroconto_importo, data_giroconto
--   from b2f_fatture order by anno desc, progressivo desc;
