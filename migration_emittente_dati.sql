-- ==================================================================
-- Dati dell'emittente per l'intestazione del facsimile
--
-- IL PROBLEMA. La riga b2f_emittente conteneva solo nome e cognome:
-- P.IVA, codice fiscale, indirizzo, email e PEC erano rimasti NULL fin
-- dal seed iniziale. Il PDF legge quella riga, quindi l'intestazione
-- usciva col solo nome — mentre i dati del destinatario, che vengono
-- dallo snapshot della fattura, c'erano tutti.
--
-- La pagina /fatture/emittente mostra questi stessi valori come
-- precompilazione, ma finche' non si preme Salva non finiscono a
-- database e il PDF resta senza intestazione. Questa migrazione li
-- scrive una volta per tutte.
--
-- Aggiorna SOLO i campi ancora vuoti: se hai gia' salvato qualcosa dalla
-- pagina, quello che hai scritto tu vince.
--
-- DA ESEGUIRE nell'SQL Editor di Supabase.
-- Idempotente: puoi rilanciarlo.
-- ==================================================================

update b2f_emittente set
  nome        = coalesce(nullif(nome, ''),        'Emanuele'),
  cognome     = coalesce(nullif(cognome, ''),     'Bellotti'),
  piva        = coalesce(nullif(piva, ''),        '14747480961'),
  cf          = coalesce(nullif(cf, ''),          'BLLMNL01S27F205K'),
  regime_fisc = coalesce(nullif(regime_fisc, ''), 'RF19'),
  indirizzo   = coalesce(nullif(indirizzo, ''),   'VIA GABBRO, 5'),
  cap         = coalesce(nullif(cap, ''),         '20161'),
  comune      = coalesce(nullif(comune, ''),      'Milano'),
  provincia   = coalesce(nullif(provincia, ''),   'MI'),
  nazione     = coalesce(nullif(nazione, ''),     'IT'),
  email       = coalesce(nullif(email, ''),       'ebellotti001@gmail.com'),
  pec         = coalesce(nullif(pec, ''),         'ebellotti@pec.it'),
  -- IBAN preso dal facsimile gia' emesso (fattura 2026/002). Compare nel
  -- blocco pagamento del PDF: senza, il cliente non sa dove versare.
  iban        = coalesce(nullif(iban, ''),        'IT03G0503401753000000180479')
where id = 1;

-- Se la riga non esistesse affatto, creala.
insert into b2f_emittente (
  id, nome, cognome, piva, cf, regime_fisc,
  indirizzo, cap, comune, provincia, nazione, email, pec, iban
)
select 1, 'Emanuele', 'Bellotti', '14747480961', 'BLLMNL01S27F205K', 'RF19',
       'VIA GABBRO, 5', '20161', 'Milano', 'MI', 'IT',
       'ebellotti001@gmail.com', 'ebellotti@pec.it',
       'IT03G0503401753000000180479'
on conflict (id) do nothing;


-- ==================================================================
-- Verifica: nessun campo dell'intestazione deve risultare vuoto
-- ==================================================================
-- select nome, cognome, piva, cf, indirizzo, cap, comune, provincia,
--        email, pec, iban, studio_nome, studio_email
--   from b2f_emittente where id = 1;
