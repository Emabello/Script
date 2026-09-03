# Schema Supabase — snapshot

Foto dello schema reale su Supabase, presa con la query di [README §8.5](../README.md#85--ispezionare-lo-schema). **Va rigenerata dopo ogni migrazione**: si aggiorna qui, non a mano.

Ultimo aggiornamento: 2026-09-03 (dopo le migrazioni § 8.14, § 8.15, § 8.16, § 8.17 e § 8.18, tutte applicate al database vivo).


> **Nota**: questa foto è stata riverificata campo per campo contro il database
> vivo il 25/08/2026, tramite il connettore MCP di Supabase invece che con l'export
> testuale di §8.5 — colonne, vincoli, indici, definizioni delle viste, funzioni,
> trigger e RLS. Cade con questo anche il dubbio sui nomi troncati dal vecchio
> export (`b2f_parametri_fiscali.anno_fine_regime_agevolato`,
> `cfg_categoria_sottocategoria.sottocategoria_id`, `spese.created_at`,
> `v_spese.created_at`): erano ricostruiti a mano, ora sono confermati.
>
> Allineate in questo giro: `v_risparmi_mese` (era la definizione pre-8.7),
> `v_periodi_stipendio` (mancavano i giroconti dalla P.IVA), la FK
> `b2f_fatture_spesa_piva_id_fkey` di §8.6 (ora esiste davvero), e le tabelle
> `b2f_revolut` e `b2f_saldi_verifica`, che mancavano del tutto.


---

## Indice

- [`b2f_clienti`](#b2fclienti)
- [`b2f_emittente`](#b2femittente)
- [`b2f_fatture`](#b2ffatture)
- [`b2f_parametri_fiscali`](#b2fparametrifiscali)
- [`b2f_revolut`](#b2frevolut)
- [`b2f_saldi_verifica`](#b2fsaldiverifica)
- [`b2f_spese_piva`](#b2fspesepiva)
- [`b2f_webauthn_credentials`](#b2fwebauthncredentials)
- [`cfg_categoria_sottocategoria`](#cfgcategoriasottocategoria)
- [`cfg_categorie`](#cfgcategorie)
- [`cfg_sottocategorie`](#cfgsottocategorie)
- [`impostazioni`](#impostazioni)
- [`risparmi_periodo`](#risparmiperiodo)
- [`spese`](#spese)
- [`v_periodi_stipendio`](#vperiodistipendio)
- [`v_risparmi_mese`](#vrisparmimese)
- [`v_situazione_annuale`](#vsituazioneannuale)
- [`v_spese`](#vspese)
- [Funzioni](#funzioni)
- [Trigger](#trigger)
- [Row Level Security](#row-level-security)


---

## `b2f_clienti`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | bigint | NO | NO | nextval('b2f_clienti_id_seq'::regclass) |
| `tipo` | text | NO | NO | 'azienda'::text |
| `denominazione` | text | YES | NO |  |
| `nome` | text | YES | NO |  |
| `cognome` | text | YES | NO |  |
| `piva` | text | YES | NO |  |
| `cf` | text | YES | NO |  |
| `indirizzo` | text | YES | NO |  |
| `cap` | text | YES | NO |  |
| `comune` | text | YES | NO |  |
| `provincia` | text | YES | NO |  |
| `nazione` | text | YES | NO | 'IT'::text |
| `sdi` | text | YES | NO |  |
| `pec` | text | YES | NO |  |
| `email` | text | YES | NO |  |
| `note` | text | YES | NO |  |
| `attivo` | boolean | YES | NO | true |
| `created_at` | timestamp with time zone | YES | NO | now() |
| `updated_at` | timestamp with time zone | YES | NO | now() |

**Vincoli:**

- `b2f_clienti_pkey`: PRIMARY KEY (id)
- `b2f_clienti_tipo_check`: CHECK ((tipo = ANY (ARRAY['azienda'::text, 'privato'::text, 'pa'::text, 'estero'::text])))

**Indici:**

- `CREATE UNIQUE INDEX b2f_clienti_pkey ON public.b2f_clienti USING btree (id)`
- `CREATE INDEX idx_b2f_clienti_attivo ON public.b2f_clienti USING btree (attivo) WHERE (attivo = true)`
- `CREATE INDEX idx_b2f_clienti_denominazione ON public.b2f_clienti USING btree (denominazione)`
- `CREATE INDEX idx_b2f_clienti_piva ON public.b2f_clienti USING btree (piva)`


---

## `b2f_emittente`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | smallint | NO | NO | 1 |
| `nome` | text | YES | NO |  |
| `cognome` | text | YES | NO |  |
| `denominazione` | text | YES | NO |  |
| `piva` | text | YES | NO |  |
| `cf` | text | YES | NO |  |
| `regime_fisc` | text | YES | NO | 'RF19'::text |
| `indirizzo` | text | YES | NO |  |
| `cap` | text | YES | NO |  |
| `comune` | text | YES | NO |  |
| `provincia` | text | YES | NO |  |
| `nazione` | text | YES | NO | 'IT'::text |
| `email` | text | YES | NO |  |
| `pec` | text | YES | NO |  |
| `telefono` | text | YES | NO |  |
| `iban` | text | YES | NO |  |
| `cassa_prev` | text | YES | NO |  |
| `aliquota_cassa` | numeric | YES | NO | 0 |
| `created_at` | timestamp with time zone | YES | NO | now() |
| `updated_at` | timestamp with time zone | YES | NO | now() |
| `studio_nome` | text | YES | NO |  |
| `studio_email` | text | YES | NO |  |

**Vincoli:**

- `b2f_emittente_id_check`: CHECK ((id = 1))
- `b2f_emittente_pkey`: PRIMARY KEY (id)

**Indici:**

- `CREATE UNIQUE INDEX b2f_emittente_pkey ON public.b2f_emittente USING btree (id)`


---

## `b2f_fatture`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | bigint | NO | NO | nextval('b2f_fatture_id_seq'::regclass) |
| `anno` | integer | NO | NO |  |
| `progressivo` | integer | NO | NO |  |
| `numero` | text | YES | NO |  |
| `data` | date | NO | NO | CURRENT_DATE |
| `tipo_doc` | text | NO | NO | 'TD01'::text |
| `natura_iva` | text | YES | NO | 'N2.2'::text |
| `cliente_id` | bigint | YES | NO |  |
| `cliente_snapshot` | jsonb | NO | NO |  |
| `righe` | jsonb | NO | NO |  |
| `imponibile` | numeric | NO | NO | 0 |
| `bollo` | numeric | NO | NO | 0 |
| `bollo_addebitato` | boolean | NO | NO | false |
| `cassa_perc` | numeric | NO | NO | 0 |
| `cassa_importo` | numeric | NO | NO | 0 |
| `totale` | numeric | NO | NO | 0 |
| `divisa` | text | NO | NO | 'EUR'::text |
| `pagamento_mod` | text | YES | NO |  |
| `pagamento_cond` | text | YES | NO |  |
| `scadenza` | date | YES | NO |  |
| `iban` | text | YES | NO |  |
| `stato` | text | NO | NO | 'bozza'::text |
| `data_incasso` | date | YES | NO |  |
| `spesa_piva_id` | bigint | YES | NO |  |
| `pdf_url` | text | YES | NO |  |
| `xml_url` | text | YES | NO |  |
| `note` | text | YES | NO |  |
| `created_at` | timestamp with time zone | YES | NO | now() |
| `updated_at` | timestamp with time zone | YES | NO | now() |
| `data_invio_studio` | date | YES | NO |  |
| `data_trasmissione_sdi` | date | YES | NO |  |
| `numero_sdi` | text | YES | NO |  |
| `accantonamento_scenario` | text | YES | NO |  |
| `accantonamento_importo` | numeric | YES | NO |  |
| `giroconto_importo` | numeric | YES | NO |  |
| `data_giroconto` | date | YES | NO |  |
| `giroconto_piva_id` | bigint | YES | NO |  |
| `giroconto_personale_id` | bigint | YES | NO |  |
| `data_invio_nadia` | date | YES | NO |  |
| `ore_periodo` | date | YES | NO |  |
| `ore_snapshot` | jsonb | YES | NO |  |
| `ore_lette_il` | timestamp with time zone | YES | NO |  |

**Vincoli:**

- `b2f_fatture_anno_progressivo_key`: UNIQUE (anno, progressivo)
- `b2f_fatture_cliente_id_fkey`: FOREIGN KEY (cliente_id) REFERENCES b2f_clienti(id) ON DELETE RESTRICT
- `b2f_fatture_giroconto_piva_id_fkey`: FOREIGN KEY (giroconto_piva_id) REFERENCES b2f_spese_piva(id) ON DELETE SET NULL
- `b2f_fatture_pkey`: PRIMARY KEY (id)
- `b2f_fatture_scenario_valido`: CHECK (((accantonamento_scenario IS NULL) OR (accantonamento_scenario = ANY (ARRAY['copertura'::text, 'consigliato'::text, 'prudente'::text, 'blindato'::text, 'minimo'::text, 'sicuro'::text]))))
- `b2f_fatture_spesa_piva_id_fkey`: FOREIGN KEY (spesa_piva_id) REFERENCES b2f_spese_piva(id) ON DELETE SET NULL
- `b2f_fatture_stato_check`: CHECK ((stato = ANY (ARRAY['bozza'::text, 'inviata_nadia'::text, 'incassata'::text, 'inviata_studio'::text, 'trasmessa_sdi'::text, 'annullata'::text])))
- `b2f_fatture_tipo_doc_check`: CHECK ((tipo_doc = ANY (ARRAY['TD01'::text, 'TD02'::text, 'TD03'::text, 'TD04'::text, 'TD05'::text, 'TD06'::text, 'TD16'::text, 'TD17'::text, 'TD18'::text, 'TD19'::text, 'TD20'::text, 'TD24'::text, 'TD25'::text, 'TD26'::text, 'TD27'::text])))

**Indici:**

- `CREATE UNIQUE INDEX b2f_fatture_anno_progressivo_key ON public.b2f_fatture USING btree (anno, progressivo)`
- `CREATE UNIQUE INDEX b2f_fatture_pkey ON public.b2f_fatture USING btree (id)`
- `CREATE INDEX idx_b2f_fatture_cliente ON public.b2f_fatture USING btree (cliente_id)`
- `CREATE INDEX idx_b2f_fatture_da_girocontare ON public.b2f_fatture USING btree (stato) WHERE (data_giroconto IS NULL)`
- `CREATE INDEX idx_b2f_fatture_data ON public.b2f_fatture USING btree (data DESC)`
- `CREATE INDEX idx_b2f_fatture_stato ON public.b2f_fatture USING btree (stato)`


---

## `b2f_parametri_fiscali`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | smallint | NO | NO | 1 |
| `regime` | text | NO | NO | 'RF19'::text |
| `ateco` | text | NO | NO | '622010'::text |
| `ateco_descrizione` | text | YES | NO | 'Attività di consulenza informatica'::text |
| `coeff_ateco` | numeric | NO | NO | 0.67 |
| `aliquota_imposta` | numeric | NO | NO | 0.05 |
| `aliquota_inps` | numeric | NO | NO | 0.2607 |
| `aliquota_acconto` | numeric | NO | NO | 0.80 |
| `bollo_soglia` | numeric | NO | NO | 77.47 |
| `bollo_importo` | numeric | NO | NO | 2.00 |
| `limite_fatturato_anno` | numeric | NO | NO | 85000 |
| `data_apertura_piva` | date | NO | NO | '2026-05-28'::date |
| `anno_fine_regime_agevolato` | integer | YES | NO | 2031 |
| `updated_at` | timestamp with time zone | YES | NO | now() |
| `margine_sicurezza` | numeric | NO | NO | 0.10 |
| `costi_fissi_annui` | numeric | NO | NO | 0 |
| `fatturato_atteso_anno` | numeric | NO | NO | 0 |
| `acconto_imposta_perc` | numeric | NO | NO | 1.00 |
| `scenario_preferito` | text | NO | NO | 'consigliato'::text |
| `tariffa_giornaliera` | numeric | NO | NO | 250 |
| `acconto_prima_rata_perc` | numeric | NO | NO | 0.40 |

**Vincoli:**

- `b2f_parametri_fiscali_id_check`: CHECK ((id = 1))
- `b2f_parametri_fiscali_pkey`: PRIMARY KEY (id)
- `b2f_parametri_scenario_valido`: CHECK ((scenario_preferito = ANY (ARRAY['copertura'::text, 'consigliato'::text, 'prudente'::text, 'blindato'::text, 'minimo'::text, 'sicuro'::text])))

**Indici:**

- `CREATE UNIQUE INDEX b2f_parametri_fiscali_pkey ON public.b2f_parametri_fiscali USING btree (id)`


---

## `b2f_revolut`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `data` | date | NO | NO |  |
| `conto` | numeric | NO | NO | 0 |
| `risparmi` | numeric | NO | NO | 0 |
| `investimenti` | numeric | NO | NO | 0 |
| `salvadanai` | jsonb | NO | NO | '{}'::jsonb |
| `fonte` | text | NO | NO | 'estratto'::text |
| `note` | text | YES | NO |  |
| `created_at` | timestamp with time zone | NO | NO | now() |
| `updated_at` | timestamp with time zone | NO | NO | now() |

**Vincoli:**

- `b2f_revolut_pkey`: PRIMARY KEY (data)

**Indici:**

- `CREATE UNIQUE INDEX b2f_revolut_pkey ON public.b2f_revolut USING btree (data)`


---

## `b2f_saldi_verifica`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | bigint | NO | NO | nextval('b2f_saldi_verifica_id_seq'::regclass) |
| `conto` | text | NO | NO |  |
| `data` | date | NO | NO |  |
| `saldo_banca` | numeric | NO | NO |  |
| `note` | text | YES | NO |  |
| `created_at` | timestamp with time zone | NO | NO | now() |

**Vincoli:**

- `b2f_saldi_verifica_conto_check`: CHECK ((conto = ANY (ARRAY['personale'::text, 'piva'::text])))
- `b2f_saldi_verifica_conto_data_key`: UNIQUE (conto, data)
- `b2f_saldi_verifica_pkey`: PRIMARY KEY (id)

**Indici:**

- `CREATE UNIQUE INDEX b2f_saldi_verifica_conto_data_key ON public.b2f_saldi_verifica USING btree (conto, data)`
- `CREATE UNIQUE INDEX b2f_saldi_verifica_pkey ON public.b2f_saldi_verifica USING btree (id)`


---

## `b2f_spese_piva`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | bigint | NO | NO | nextval('b2f_spese_piva_id_seq'::regclass) |
| `data` | date | NO | NO |  |
| `importo` | numeric | NO | NO |  |
| `tipo` | text | NO | NO |  |
| `descrizione` | text | NO | NO |  |
| `categoria` | text | YES | NO |  |
| `sottocategoria` | text | YES | NO |  |
| `fattura_id` | bigint | YES | NO |  |
| `ricorrente` | boolean | YES | NO | false |
| `note` | text | YES | NO |  |
| `created_at` | timestamp with time zone | YES | NO | now() |
| `updated_at` | timestamp with time zone | YES | NO | now() |
| `giroconto_personale_id` | integer | YES | NO |  |

**Vincoli:**

- `b2f_spese_piva_fattura_id_fkey`: FOREIGN KEY (fattura_id) REFERENCES b2f_fatture(id) ON DELETE SET NULL
- `b2f_spese_piva_pkey`: PRIMARY KEY (id)
- `b2f_spese_piva_tipo_check`: CHECK ((tipo = ANY (ARRAY['entrata'::text, 'uscita'::text, 'giroconto'::text])))

**Indici:**

- `CREATE UNIQUE INDEX b2f_spese_piva_pkey ON public.b2f_spese_piva USING btree (id)`
- `CREATE INDEX idx_b2f_spese_piva_categoria ON public.b2f_spese_piva USING btree (categoria)`
- `CREATE INDEX idx_b2f_spese_piva_data ON public.b2f_spese_piva USING btree (data DESC)`
- `CREATE INDEX idx_b2f_spese_piva_fattura ON public.b2f_spese_piva USING btree (fattura_id)`


---

## `b2f_webauthn_credentials`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | bigint | NO | NO | nextval('b2f_webauthn_credentials_id_seq'::regclass) |
| `credential_id` | text | NO | NO |  |
| `public_key` | text | NO | NO |  |
| `sign_count` | integer | NO | NO | 0 |
| `device_name` | text | YES | NO |  |
| `aaguid` | text | YES | NO |  |
| `transports` | ARRAY | YES | NO |  |
| `created_at` | timestamp with time zone | NO | NO | now() |
| `last_used_at` | timestamp with time zone | YES | NO |  |

**Vincoli:**

- `b2f_webauthn_credentials_credential_id_key`: UNIQUE (credential_id)
- `b2f_webauthn_credentials_pkey`: PRIMARY KEY (id)

**Indici:**

- `CREATE UNIQUE INDEX b2f_webauthn_credentials_credential_id_key ON public.b2f_webauthn_credentials USING btree (credential_id)`
- `CREATE UNIQUE INDEX b2f_webauthn_credentials_pkey ON public.b2f_webauthn_credentials USING btree (id)`
- `CREATE INDEX idx_b2f_webauthn_last_used ON public.b2f_webauthn_credentials USING btree (last_used_at DESC NULLS LAST)`


---

## `cfg_categoria_sottocategoria`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | uuid | NO | NO | gen_random_uuid() |
| `categoria_id` | uuid | NO | NO |  |
| `sottocategoria_id` | uuid | YES | NO |  |
| `ordine` | integer | NO | NO | 0 |
| `attiva` | boolean | NO | NO | true |
| `created_at` | timestamp with time zone | NO | NO | now() |

**Vincoli:**

- `cfg_categoria_sottocategoria_categoria_id_fkey`: FOREIGN KEY (categoria_id) REFERENCES cfg_categorie(id) ON DELETE CASCADE
- `cfg_categoria_sottocategoria_pkey`: PRIMARY KEY (id)
- `cfg_categoria_sottocategoria_sottocategoria_id_fkey`: FOREIGN KEY (sottocategoria_id) REFERENCES cfg_sottocategorie(id) ON DELETE CASCADE

**Indici:**

- `CREATE UNIQUE INDEX cfg_categoria_sottocategoria_pkey ON public.cfg_categoria_sottocategoria USING btree (id)`
- `CREATE INDEX idx_cfg_cat_sub_cat ON public.cfg_categoria_sottocategoria USING btree (categoria_id)`
- `CREATE UNIQUE INDEX uk_cfg_cat_blank ON public.cfg_categoria_sottocategoria USING btree (categoria_id) WHERE (sottocategoria_id IS NULL)`
- `CREATE UNIQUE INDEX uk_cfg_cat_sub ON public.cfg_categoria_sottocategoria USING btree (categoria_id, sottocategoria_id) WHERE (sottocategoria_id IS NOT NULL)`


---

## `cfg_categorie`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | uuid | NO | NO | gen_random_uuid() |
| `nome` | text | NO | NO |  |
| `ordine` | integer | YES | NO | 0 |
| `attiva` | boolean | NO | NO | true |
| `created_at` | timestamp with time zone | YES | NO | now() |

**Vincoli:**

- `cfg_categorie_nome_uk`: UNIQUE (nome)
- `cfg_categorie_pkey`: PRIMARY KEY (id)

**Indici:**

- `CREATE UNIQUE INDEX cfg_categorie_nome_uk ON public.cfg_categorie USING btree (nome)`
- `CREATE UNIQUE INDEX cfg_categorie_pkey ON public.cfg_categorie USING btree (id)`
- `CREATE INDEX idx_cfg_categorie_attiva ON public.cfg_categorie USING btree (attiva)`

**Policy RLS:**

- Allow read categorie SELECT | using=true


---

## `cfg_sottocategorie`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | uuid | NO | NO | gen_random_uuid() |
| `nome` | text | NO | NO |  |
| `ordine` | integer | YES | NO | 0 |
| `attiva` | boolean | NO | NO | true |
| `created_at` | timestamp with time zone | YES | NO | now() |

**Vincoli:**

- `cfg_sottocategorie_nome_uk`: UNIQUE (nome)
- `cfg_sottocategorie_pkey`: PRIMARY KEY (id)

**Indici:**

- `CREATE UNIQUE INDEX cfg_sottocategorie_nome_uk ON public.cfg_sottocategorie USING btree (nome)`
- `CREATE UNIQUE INDEX cfg_sottocategorie_pkey ON public.cfg_sottocategorie USING btree (id)`
- `CREATE INDEX idx_cfg_sottocategorie_attiva ON public.cfg_sottocategorie USING btree (attiva)`

**Policy RLS:**

- Allow read sottocategorie SELECT | using=true


---

## `impostazioni`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `saldo_iniziale` | real | NO | NO |  |
| `percentuale_risparmio` | real | NO | NO |  |
| `perc_fondo_emergenze` | real | NO | NO |  |
| `perc_viaggi` | real | NO | NO |  |
| `perc_fondo_casa` | real | NO | NO |  |
| `perc_regali` | real | NO | NO |  |
| `perc_altro` | real | NO | NO |  |
| `valido_dal` | date | NO | NO | '2000-01-01'::date |

**Vincoli:**

- `impostazioni_pkey`: PRIMARY KEY (valido_dal)

**Indici:**

- `CREATE UNIQUE INDEX impostazioni_pkey ON public.impostazioni USING btree (valido_dal)`


---

## `risparmi_periodo`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `data_bonifico` | date | NO | NO |  |
| `effettivo_risparmio` | real | NO | NO | 0 |

**Vincoli:**

- `risparmi_periodo_pkey`: PRIMARY KEY (data_bonifico)

**Indici:**

- `CREATE UNIQUE INDEX risparmi_periodo_pkey ON public.risparmi_periodo USING btree (data_bonifico)`


---

## `spese`

| colonna | tipo | null | identity | default |
|---|---|---|---|---|
| `id` | bigint | NO | YES |  |
| `data` | date | NO | NO |  |
| `descrizione` | text | YES | NO |  |
| `importo` | numeric | NO | NO |  |
| `tipo` | text | NO | NO |  |
| `mese` | integer | NO | NO |  |
| `anno` | integer | NO | NO |  |
| `created_at` | timestamp without time zone | YES | NO | now() |
| `metodo_pagamento` | text | YES | NO |  |
| `categoria_link_id` | uuid | YES | NO |  |
| `fattura_giroconto_id` | bigint | YES | NO |  |

**Vincoli:**

- `fk_spese_categoria_link`: FOREIGN KEY (categoria_link_id) REFERENCES cfg_categoria_sottocategoria(id) ON DELETE RESTRICT
- `spese_fattura_giroconto_fkey`: FOREIGN KEY (fattura_giroconto_id) REFERENCES b2f_fatture(id) ON DELETE SET NULL
- `spese_pkey`: PRIMARY KEY (id)
- `spese_tipo_check`: CHECK ((tipo = ANY (ARRAY['entrata'::text, 'uscita'::text, 'giroconto'::text])))

**Indici:**

- `CREATE UNIQUE INDEX spese_pkey ON public.spese USING btree (id)`
- `CREATE INDEX idx_spese_fattura_giroconto ON public.spese USING btree (fattura_giroconto_id) WHERE (fattura_giroconto_id IS NOT NULL)`


---

## Viste


### `v_periodi_stipendio`

| colonna | tipo |
|---|---|
| `data_bonifico` | date |
| `importo_bonifico` | numeric |
| `prossimo_bonifico` | date |
| `fine_periodo` | timestamp with time zone |

```sql
WITH stipendi AS (
         SELECT vs.data AS data_bonifico,
            vs.importo AS importo_bonifico
           FROM v_spese vs
          WHERE vs.tipo = 'entrata'::text AND (vs.categoria = ANY (ARRAY['Stipendio'::text, 'Giroconto P.IVA'::text]))
        ), ord AS (
         SELECT stipendi.data_bonifico,
            stipendi.importo_bonifico,
            lead(stipendi.data_bonifico) OVER (ORDER BY stipendi.data_bonifico) AS prossimo_bonifico
           FROM stipendi
        )
 SELECT data_bonifico,
    importo_bonifico,
    prossimo_bonifico,
    COALESCE((prossimo_bonifico - '1 day'::interval)::timestamp with time zone, CURRENT_DATE::timestamp with time zone) AS fine_periodo
   FROM ord
  ORDER BY data_bonifico;
```


### `v_risparmi_mese`

| colonna | tipo |
|---|---|
| `Importo Prima Del Bonifico` | numeric |
| `Importo Prima Del Bonifico (dup)` | numeric |
| `Data bonifico` | date |
| `Data prossimo bonifico` | date |
| `Mese` | text |
| `Importo Bonifico` | numeric |
| `Totale Fisso` | numeric |
| `Totale Personale` | numeric |
| `Totale Benzina` | numeric |
| `Totale Viaggi` | numeric |
| `Totale Speso` | numeric |
| `Totale Altre Entrate` | numeric |
| `Totale Rimanente` | numeric |
| `Risparmio consigliato (€)` | numeric |
| `Risparmio effettivo (€)` | numeric |
| `Totale Rimanente (finale)` | numeric |
| `Quota Fondo Emergenze` | numeric |
| `Quota Viaggi` | numeric |
| `Quota Fondo Casa` | numeric |
| `Quota Regali` | numeric |
| `Quota Altro` | numeric |
| `_Fine periodo (debug)` | timestamp with time zone |

```sql
 WITH per AS (
         SELECT ps.data_bonifico,
            ps.importo_bonifico,
            ps.prossimo_bonifico,
            ps.fine_periodo
           FROM v_periodi_stipendio ps
        ), agg AS (
         SELECT per.data_bonifico,
            per.prossimo_bonifico,
            per.fine_periodo,
            per.importo_bonifico,
            round(COALESCE(sum(
                CASE
                    WHEN vs.tipo = 'uscita'::text AND vs.categoria = 'Fisso'::text THEN vs.importo
                    ELSE 0::numeric
                END), 0::numeric), 2) AS totale_fisso,
            round(COALESCE(sum(
                CASE
                    WHEN vs.tipo = 'uscita'::text AND vs.categoria = 'Personale'::text THEN vs.importo
                    ELSE 0::numeric
                END), 0::numeric), 2) AS totale_personale,
            round(COALESCE(sum(
                CASE
                    WHEN vs.tipo = 'uscita'::text AND vs.categoria = 'Benzina'::text THEN vs.importo
                    ELSE 0::numeric
                END), 0::numeric), 2) AS totale_benzina,
            round(COALESCE(sum(
                CASE
                    WHEN vs.tipo = 'uscita'::text AND vs.categoria = 'Viaggi'::text THEN vs.importo
                    ELSE 0::numeric
                END), 0::numeric), 2) AS totale_viaggi,
            round(COALESCE(sum(
                CASE
                    WHEN vs.tipo = 'uscita'::text AND COALESCE(vs.categoria, ''::text) <> 'Risparmi'::text THEN vs.importo
                    ELSE 0::numeric
                END), 0::numeric), 2) AS totale_speso,
            round(COALESCE(sum(
                CASE
                    WHEN vs.tipo = 'entrata'::text AND (vs.categoria <> ALL (ARRAY['Stipendio'::text, 'Giroconto P.IVA'::text, 'Risparmi'::text])) THEN vs.importo
                    ELSE 0::numeric
                END), 0::numeric), 2) AS totale_altre_entrate,
            round(COALESCE(sum(
                CASE
                    WHEN COALESCE(vs.categoria, ''::text) = 'Risparmi'::text THEN
                    CASE
                        WHEN vs.tipo = 'uscita'::text THEN vs.importo
                        ELSE - vs.importo
                    END
                    ELSE 0::numeric
                END), 0::numeric), 2) AS effettivo_risparmio
           FROM per
             LEFT JOIN v_spese vs ON vs.data >= per.data_bonifico AND vs.data <= per.fine_periodo
          GROUP BY per.data_bonifico, per.prossimo_bonifico, per.fine_periodo, per.importo_bonifico
        ), calc AS (
         SELECT a.data_bonifico,
            a.prossimo_bonifico,
            a.fine_periodo,
            a.importo_bonifico,
            a.totale_fisso,
            a.totale_personale,
            a.totale_benzina,
            a.totale_viaggi,
            a.totale_speso,
            a.totale_altre_entrate,
            a.effettivo_risparmio,
            p.saldo_iniziale,
            p.percentuale_risparmio,
            p.perc_fondo_emergenze,
            p.perc_viaggi,
            p.perc_fondo_casa,
            p.perc_regali,
            p.perc_altro,
            sum(a.importo_bonifico + a.totale_altre_entrate - a.totale_speso - a.effettivo_risparmio) OVER (ORDER BY a.data_bonifico ROWS UNBOUNDED PRECEDING) AS running_delta
           FROM agg a
             CROSS JOIN LATERAL ( SELECT i.saldo_iniziale,
                    i.percentuale_risparmio,
                    i.perc_fondo_emergenze,
                    i.perc_viaggi,
                    i.perc_fondo_casa,
                    i.perc_regali,
                    i.perc_altro
                   FROM impostazioni i
                  WHERE i.valido_dal <= a.data_bonifico
                  ORDER BY i.valido_dal DESC
                 LIMIT 1) p
        ), bal AS (
         SELECT c.data_bonifico,
            c.prossimo_bonifico,
            c.fine_periodo,
            c.importo_bonifico,
            c.totale_fisso,
            c.totale_personale,
            c.totale_benzina,
            c.totale_viaggi,
            c.totale_speso,
            c.totale_altre_entrate,
            c.effettivo_risparmio,
            c.saldo_iniziale,
            c.percentuale_risparmio,
            c.perc_fondo_emergenze,
            c.perc_viaggi,
            c.perc_fondo_casa,
            c.perc_regali,
            c.perc_altro,
            c.running_delta,
            COALESCE(lag(c.running_delta) OVER (ORDER BY c.data_bonifico), 0::numeric) AS running_delta_prev
           FROM calc c
        ), outt AS (
         SELECT bal.data_bonifico,
            bal.prossimo_bonifico,
            bal.fine_periodo,
            bal.importo_bonifico,
            bal.totale_fisso,
            bal.totale_personale,
            bal.totale_benzina,
            bal.totale_viaggi,
            bal.totale_speso,
            bal.totale_altre_entrate,
            bal.effettivo_risparmio,
            bal.saldo_iniziale,
            bal.percentuale_risparmio,
            bal.perc_fondo_emergenze,
            bal.perc_viaggi,
            bal.perc_fondo_casa,
            bal.perc_regali,
            bal.perc_altro,
            bal.running_delta,
            bal.running_delta_prev,
            round((bal.saldo_iniziale + bal.running_delta_prev::double precision)::numeric, 2) AS importo_prima_del_bonifico,
            bal.saldo_iniziale + bal.running_delta_prev::double precision + bal.importo_bonifico::double precision + bal.totale_altre_entrate::double precision - bal.totale_speso::double precision AS base_calcolo
           FROM bal
        )
 SELECT importo_prima_del_bonifico AS "Importo Prima Del Bonifico",
    importo_prima_del_bonifico AS "Importo Prima Del Bonifico (dup)",
    data_bonifico AS "Data bonifico",
    prossimo_bonifico AS "Data prossimo bonifico",
    to_char(data_bonifico::timestamp with time zone, 'TMmonth'::text) AS "Mese",
    round(importo_bonifico::numeric, 2) AS "Importo Bonifico",
    totale_fisso AS "Totale Fisso",
    totale_personale AS "Totale Personale",
    totale_benzina AS "Totale Benzina",
    totale_viaggi AS "Totale Viaggi",
    totale_speso AS "Totale Speso",
    totale_altre_entrate AS "Totale Altre Entrate",
    round(importo_bonifico + totale_altre_entrate - totale_speso, 2) AS "Totale Rimanente",
    round(GREATEST(base_calcolo * percentuale_risparmio, 0::double precision)::numeric, 2) AS "Risparmio consigliato (€)",
    effettivo_risparmio AS "Risparmio effettivo (€)",
    round((base_calcolo - effettivo_risparmio::double precision)::numeric, 2) AS "Totale Rimanente (finale)",
    round((effettivo_risparmio::double precision * perc_fondo_emergenze)::numeric, 2) AS "Quota Fondo Emergenze",
    round((effettivo_risparmio::double precision * perc_viaggi)::numeric, 2) AS "Quota Viaggi",
    round((effettivo_risparmio::double precision * perc_fondo_casa)::numeric, 2) AS "Quota Fondo Casa",
    round((effettivo_risparmio::double precision * perc_regali)::numeric, 2) AS "Quota Regali",
    round((effettivo_risparmio::double precision * perc_altro)::numeric, 2) AS "Quota Altro",
    fine_periodo AS "_Fine periodo (debug)"
   FROM outt
  ORDER BY data_bonifico;
```


### `v_situazione_annuale`

| colonna | tipo |
|---|---|
| `anno` | integer |
| `mese` | integer |
| `fatturato_mese` | numeric |
| `imponibile_mese` | numeric |
| `incasso_mese` | numeric |
| `imposta_mese` | numeric |
| `inps_saldo_mese` | numeric |
| `inps_acconto_mese` | numeric |
| `bollo_mese` | numeric |
| `commercialista_mese` | numeric |
| `n_fatture` | bigint |

```sql
WITH param AS (
         SELECT b2f_parametri_fiscali.id,
            b2f_parametri_fiscali.regime,
            b2f_parametri_fiscali.ateco,
            b2f_parametri_fiscali.ateco_descrizione,
            b2f_parametri_fiscali.coeff_ateco,
            b2f_parametri_fiscali.aliquota_imposta,
            b2f_parametri_fiscali.aliquota_inps,
            b2f_parametri_fiscali.aliquota_acconto,
            b2f_parametri_fiscali.bollo_soglia,
            b2f_parametri_fiscali.bollo_importo,
            b2f_parametri_fiscali.limite_fatturato_anno,
            b2f_parametri_fiscali.data_apertura_piva,
            b2f_parametri_fiscali.anno_fine_regime_agevolato,
            b2f_parametri_fiscali.updated_at,
            b2f_parametri_fiscali.margine_sicurezza,
            b2f_parametri_fiscali.costi_fissi_annui,
            b2f_parametri_fiscali.fatturato_atteso_anno,
            b2f_parametri_fiscali.acconto_imposta_perc,
            b2f_parametri_fiscali.scenario_preferito
           FROM b2f_parametri_fiscali
          WHERE b2f_parametri_fiscali.id = 1
        ), fatt AS (
         SELECT EXTRACT(year FROM b2f_fatture.data)::integer AS anno,
            EXTRACT(month FROM b2f_fatture.data)::integer AS mese,
            sum(COALESCE(b2f_fatture.totale, 0::numeric)) AS fatturato_mese,
            sum(COALESCE(b2f_fatture.bollo, 0::numeric)) FILTER (WHERE b2f_fatture.bollo_addebitato) AS bollo_mese,
            count(*) AS n_fatture
           FROM b2f_fatture
          WHERE b2f_fatture.stato <> ALL (ARRAY['bozza'::text, 'annullata'::text])
          GROUP BY (EXTRACT(year FROM b2f_fatture.data)::integer), (EXTRACT(month FROM b2f_fatture.data)::integer)
        ), inc AS (
         SELECT EXTRACT(year FROM b2f_fatture.data_incasso)::integer AS anno,
            EXTRACT(month FROM b2f_fatture.data_incasso)::integer AS mese,
            sum(COALESCE(b2f_fatture.totale, 0::numeric)) AS incasso_mese
           FROM b2f_fatture
          WHERE b2f_fatture.data_incasso IS NOT NULL AND b2f_fatture.stato <> 'annullata'::text
          GROUP BY (EXTRACT(year FROM b2f_fatture.data_incasso)::integer), (EXTRACT(month FROM b2f_fatture.data_incasso)::integer)
        ), spese AS (
         SELECT EXTRACT(year FROM b2f_spese_piva.data)::integer AS anno,
            EXTRACT(month FROM b2f_spese_piva.data)::integer AS mese,
            sum(b2f_spese_piva.importo) FILTER (WHERE b2f_spese_piva.categoria = 'commercialista'::text AND b2f_spese_piva.tipo = 'uscita'::text) AS commercialista_mese
           FROM b2f_spese_piva
          GROUP BY (EXTRACT(year FROM b2f_spese_piva.data)::integer), (EXTRACT(month FROM b2f_spese_piva.data)::integer)
        )
 SELECT f.anno,
    f.mese,
    f.fatturato_mese,
    round(f.fatturato_mese * p.coeff_ateco, 2) AS imponibile_mese,
    COALESCE(i.incasso_mese, 0::numeric) AS incasso_mese,
    round(f.fatturato_mese * p.coeff_ateco * (1::numeric - p.aliquota_inps) * p.aliquota_imposta, 2) AS imposta_mese,
    round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps, 2) AS inps_saldo_mese,
    round(f.fatturato_mese * p.coeff_ateco * p.aliquota_inps * p.aliquota_acconto, 2) AS inps_acconto_mese,
    COALESCE(f.bollo_mese, 0::numeric) AS bollo_mese,
    COALESCE(s.commercialista_mese, 0::numeric) AS commercialista_mese,
    f.n_fatture
   FROM fatt f
     CROSS JOIN param p
     LEFT JOIN inc i USING (anno, mese)
     LEFT JOIN spese s USING (anno, mese)
  ORDER BY f.anno, f.mese;
```


### `v_spese`

| colonna | tipo |
|---|---|
| `id` | bigint |
| `data` | date |
| `descrizione` | text |
| `importo` | numeric |
| `tipo` | text |
| `mese` | integer |
| `anno` | integer |
| `metodo_pagamento` | text |
| `created_at` | timestamp without time zone |
| `categoria` | text |
| `sottocategoria` | text |
| `categoria_link_id` | uuid |
| `categoria_id` | uuid |
| `sottocategoria_id` | uuid |
| `fattura_giroconto_id` | bigint |

```sql
SELECT s.id,
    s.data,
    s.descrizione,
    s.importo,
    s.tipo,
    s.mese,
    s.anno,
    s.metodo_pagamento,
    s.created_at,
    c.nome AS categoria,
    sc.nome AS sottocategoria,
    s.categoria_link_id,
    l.categoria_id,
    l.sottocategoria_id,
    s.fattura_giroconto_id
   FROM spese s
     LEFT JOIN cfg_categoria_sottocategoria l ON l.id = s.categoria_link_id
     LEFT JOIN cfg_categorie c ON c.id = l.categoria_id
     LEFT JOIN cfg_sottocategorie sc ON sc.id = l.sottocategoria_id;
```


---

## Funzioni


### `b2f_next_progressivo`

```sql
CREATE OR REPLACE FUNCTION public.b2f_next_progressivo(p_anno integer)
 RETURNS integer
 LANGUAGE sql
AS $function$
  select coalesce(max(progressivo), 0) + 1
  from b2f_fatture
  where anno = p_anno;
$function$
```


### `b2f_touch_updated_at`

```sql
CREATE OR REPLACE FUNCTION public.b2f_touch_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
begin
  new.updated_at = now();
  return new;
end $function$
```


### `insert_spesa_first_free_id`

```sql
CREATE OR REPLACE FUNCTION public.insert_spesa_first_free_id(p_anno integer, p_categoria_link_id uuid, p_data date, p_importo numeric, p_mese integer, p_metodo_pagamento text, p_tipo text, p_descrizione text DEFAULT NULL::text)
 RETURNS spese
 LANGUAGE plpgsql
AS $function$
declare
  v_id bigint;
  v_row public.spese;
begin
  perform pg_advisory_xact_lock(987654);

  select coalesce(min(t.missing_id), (select coalesce(max(id),0)+1 from public.spese))
    into v_id
  from (
    select (s.id + 1) as missing_id
    from public.spese s
    left join public.spese s2 on s2.id = s.id + 1
    where s2.id is null
      and s.id >= 1
  ) t
  where t.missing_id not in (select id from public.spese);

  if v_id is null then
    v_id := 1;
  end if;

  insert into public.spese(
    id, data, descrizione, importo, tipo, mese, anno,
    metodo_pagamento, categoria_link_id
  ) values (
    v_id,
    p_data,
    p_descrizione,          -- lascia null oppure usa coalesce(p_descrizione,'')
    p_importo,
    p_tipo,
    p_mese,
    p_anno,
    p_metodo_pagamento,
    p_categoria_link_id
  )
  returning * into v_row;

  return v_row;
end;
$function$
```


---

## Trigger

- `CREATE TRIGGER trg_b2f_clienti_updated BEFORE UPDATE ON public.b2f_clienti FOR EACH ROW EXECUTE FUNCTION b2f_touch_updated_at()`
- `CREATE TRIGGER trg_b2f_emittente_updated BEFORE UPDATE ON public.b2f_emittente FOR EACH ROW EXECUTE FUNCTION b2f_touch_updated_at()`
- `CREATE TRIGGER trg_b2f_fatture_updated BEFORE UPDATE ON public.b2f_fatture FOR EACH ROW EXECUTE FUNCTION b2f_touch_updated_at()`
- `CREATE TRIGGER trg_b2f_parametri_updated BEFORE UPDATE ON public.b2f_parametri_fiscali FOR EACH ROW EXECUTE FUNCTION b2f_touch_updated_at()`
- `CREATE TRIGGER trg_b2f_revolut_updated BEFORE UPDATE ON public.b2f_revolut FOR EACH ROW EXECUTE FUNCTION b2f_touch_updated_at()`
- `CREATE TRIGGER trg_b2f_spese_piva_updated BEFORE UPDATE ON public.b2f_spese_piva FOR EACH ROW EXECUTE FUNCTION b2f_touch_updated_at()`


---

## Row Level Security

| tabella | RLS |
|---|---|
| `b2f_clienti` | ATTIVA |
| `b2f_emittente` | ATTIVA |
| `b2f_fatture` | ATTIVA |
| `b2f_parametri_fiscali` | ATTIVA |
| `b2f_revolut` | ATTIVA |
| `b2f_saldi_verifica` | ATTIVA |
| `b2f_spese_piva` | ATTIVA |
| `b2f_webauthn_credentials` | ATTIVA |
| `cfg_categoria_sottocategoria` | ATTIVA |
| `cfg_categorie` | ATTIVA |
| `cfg_sottocategorie` | ATTIVA |
| `impostazioni` | ATTIVA |
| `risparmi_periodo` | disattivata |
| `spese` | disattivata |


> `spese` e `risparmi_periodo` restano apposta senza RLS: sono tabelle preesistenti, potenzialmente lette da altro con la chiave anon. Vedi README §9.