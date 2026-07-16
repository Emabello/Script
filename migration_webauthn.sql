-- migration_webauthn.sql
-- Sblocco biometrico via WebAuthn — tabella credenziali.
-- Da lanciare a mano nel SQL editor di Supabase.

create table if not exists b2f_webauthn_credentials (
  id            bigserial primary key,
  credential_id text        not null unique,   -- base64url del credential_id WebAuthn
  public_key    text        not null,          -- base64url del public_key COSE
  sign_count    integer     not null default 0,
  device_name   text,                          -- es. "Pixel 8 (Chrome)"
  aaguid        text,                          -- opzionale
  transports    text[],                        -- ['internal','hybrid',...]
  created_at    timestamptz not null default now(),
  last_used_at  timestamptz
);

alter table b2f_webauthn_credentials disable row level security;
