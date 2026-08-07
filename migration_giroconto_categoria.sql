-- ==================================================================
-- Categoria del conto personale per i giroconti dalla P.IVA
--
-- Perche' serve. La vista v_risparmi_mese somma le altre entrate con
--
--     tipo = 'entrata' and categoria <> 'Stipendio'
--
-- Su una riga senza categoria quel confronto NON e' falso: e' NULL. Il
-- movimento non entra ne' fra le entrate contate ne' fra le escluse,
-- sparisce e basta. Il denaro arriverebbe sul conto personale ma il
-- budget non lo vedrebbe, e il "Risparmio consigliato" risulterebbe
-- calcolato su una base piu' bassa del vero.
--
-- Serve quindi una categoria vera. E non puo' essere 'Stipendio':
-- v_periodi_stipendio usa proprio le entrate di quella categoria per
-- delimitare i periodi, quindi un giroconto marcato cosi' aprirebbe un
-- periodo fasullo e sfaserebbe tutto lo storico.
--
-- DA ESEGUIRE nell'SQL Editor di Supabase, dopo migration_giroconto.sql.
-- Idempotente: puoi rilanciarlo.
-- ==================================================================

-- 1) La categoria
insert into cfg_categorie (nome)
values ('Giroconto P.IVA')
on conflict (nome) do nothing;

-- 2) Il legame "categoria senza sottocategoria", che e' quello che
--    finisce in spese.categoria_link_id. L'indice uk_cfg_cat_blank
--    garantisce che ne esista al massimo uno per categoria.
insert into cfg_categoria_sottocategoria (categoria_id, sottocategoria_id)
select c.id, null
  from cfg_categorie c
 where c.nome = 'Giroconto P.IVA'
on conflict do nothing;


-- ==================================================================
-- Verifica: deve restituire una riga con un id di legame valorizzato
-- ==================================================================
-- select c.nome, l.id as categoria_link_id
--   from cfg_categorie c
--   join cfg_categoria_sottocategoria l on l.categoria_id = c.id
--  where c.nome = 'Giroconto P.IVA' and l.sottocategoria_id is null;
