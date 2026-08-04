-- ==================================================================
-- Accantonamento — colonne nuove su b2f_parametri_fiscali
--
-- DA ESEGUIRE nell'SQL Editor di Supabase PRIMA di usare la pagina
-- /fatture/parametri: senza queste colonne il salvataggio dei parametri
-- risponde errore, perche' l'app prova a scrivere campi inesistenti.
--
-- Le pagine di sola lettura funzionano anche senza: l'app applica i
-- valori di default definiti in fatture/accantonamento.py.
--
-- Idempotente: puoi rilanciarlo.
-- ==================================================================

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
  -- riduzione. A differenza dell'INPS, che va all'80 % (aliquota_acconto).
  add column if not exists acconto_imposta_perc numeric(5,4) not null default 1.00,

  -- Scenario mostrato per primo nella card: minimo | consigliato | sicuro
  add column if not exists scenario_preferito text not null default 'consigliato';

-- Vincolo sui valori ammessi per lo scenario.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'b2f_parametri_scenario_valido'
  ) then
    alter table b2f_parametri_fiscali
      add constraint b2f_parametri_scenario_valido
      check (scenario_preferito in ('minimo', 'consigliato', 'sicuro'));
  end if;
end $$;


-- ------------------------------------------------------------------
-- Valori iniziali suggeriti. Adattali ai tuoi: si cambiano anche
-- dalla pagina /fatture/parametri.
-- ------------------------------------------------------------------
-- update b2f_parametri_fiscali set
--   margine_sicurezza     = 0.10,
--   costi_fissi_annui     = 1200,
--   fatturato_atteso_anno = 0,
--   scenario_preferito    = 'consigliato'
-- where id = 1;


-- ==================================================================
-- Verifica
-- ==================================================================
-- select margine_sicurezza, costi_fissi_annui, fatturato_atteso_anno,
--        acconto_imposta_perc, scenario_preferito
-- from b2f_parametri_fiscali where id = 1;
