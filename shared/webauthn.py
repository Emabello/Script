"""
shared/webauthn.py — Sblocco biometrico via WebAuthn (FIDO2).

Blueprint('webauthn', url_prefix='/api/webauthn') con 5 endpoint per
registrare e verificare una credenziale platform authenticator (impronta /
face unlock) come metodo di sblocco alternativo al PIN esistente.

Le challenge non vengono salvate in sessione (rischio di superare il limite
del cookie firmato Werkzeug) ma in un dict a livello modulo con TTL breve.
App single-user con un solo worker gunicorn: non serve altro.
"""
import threading
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from shared.supabase_client import get_client, is_configured

webauthn_bp = Blueprint("webauthn", __name__)

_TABLE = "b2f_webauthn_credentials"
_RP_NAME = "B2F Hub"
_USER_ID = b"b2f-hub-user"  # utente singolo, id fisso
_USER_NAME = "b2f"
_SUPPORTED_ALGS = [
    COSEAlgorithmIdentifier.ECDSA_SHA_256,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
]

_CHALLENGE_TTL = 300  # 5 minuti
_challenges: dict = {}  # {'register' | 'auth': (challenge_bytes, expires_at)}
_challenges_lock = threading.Lock()


def _rp_id() -> str:
    return request.host.split(":")[0]


def _origin() -> str:
    return request.host_url.rstrip("/")


def _store_challenge(kind: str, challenge: bytes) -> None:
    with _challenges_lock:
        _challenges[kind] = (challenge, time.time() + _CHALLENGE_TTL)


def _pop_challenge(kind: str):
    with _challenges_lock:
        item = _challenges.pop(kind, None)
    if not item:
        return None
    challenge, expires_at = item
    if time.time() > expires_at:
        return None
    return challenge


def _sb_or_error():
    if not is_configured():
        return None, (jsonify({"error": "Supabase non configurato"}), 503)
    return get_client(), None


@webauthn_bp.get("/status")
def webauthn_status():
    sb, err = _sb_or_error()
    if err:
        return jsonify({"supported_by_server": True, "credentials_count": 0})
    try:
        r = sb.table(_TABLE).select("*", count="exact", head=True).execute()
        return jsonify({"supported_by_server": True, "credentials_count": r.count or 0})
    except Exception as e:
        return jsonify({
            "supported_by_server": True,
            "credentials_count": 0,
            "error": str(e)[:200],
        })


@webauthn_bp.post("/register/begin")
def webauthn_register_begin():
    if not session.get("ok"):
        return jsonify({"error": "PIN richiesto"}), 401
    sb, err = _sb_or_error()
    if err:
        return err
    try:
        existing = sb.table(_TABLE).select("credential_id").execute().data or []
    except Exception:
        existing = []
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["credential_id"]))
        for row in existing
    ]
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_RP_NAME,
        user_id=_USER_ID,
        user_name=_USER_NAME,
        user_display_name="Emanuele",
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        supported_pub_key_algs=_SUPPORTED_ALGS,
        exclude_credentials=exclude or None,
    )
    _store_challenge("register", options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}


@webauthn_bp.post("/register/complete")
def webauthn_register_complete():
    if not session.get("ok"):
        return jsonify({"error": "PIN richiesto"}), 401
    challenge = _pop_challenge("register")
    if not challenge:
        return jsonify({"error": "Challenge scaduta, riprova"}), 400

    body = request.get_json(force=True, silent=True) or {}
    credential = body.get("credential")
    device_name = (body.get("device_name") or "").strip()[:80] or "Dispositivo"
    if not credential:
        return jsonify({"error": "credential mancante"}), 400

    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            require_user_verification=True,
        )
    except Exception as e:
        return jsonify({"error": f"Verifica fallita: {e}"[:300]}), 400

    sb, err = _sb_or_error()
    if err:
        return err
    transports = ((credential.get("response") or {}).get("transports")) or []
    row = {
        "credential_id": bytes_to_base64url(verified.credential_id),
        "public_key": bytes_to_base64url(verified.credential_public_key),
        "sign_count": verified.sign_count,
        "device_name": device_name,
        "aaguid": verified.aaguid,
        "transports": transports,
    }
    try:
        sb.table(_TABLE).insert(row).execute()
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500
    return jsonify({"ok": True, "credential_id": row["credential_id"]})


@webauthn_bp.post("/auth/begin")
def webauthn_auth_begin():
    sb, err = _sb_or_error()
    allow = []
    if not err:
        try:
            rows = sb.table(_TABLE).select("credential_id").execute().data or []
            allow = [
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["credential_id"]))
                for row in rows
            ]
        except Exception:
            allow = []
    options = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=allow or None,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _store_challenge("auth", options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}


@webauthn_bp.post("/auth/complete")
def webauthn_auth_complete():
    challenge = _pop_challenge("auth")
    if not challenge:
        return jsonify({"error": "Challenge scaduta, riprova"}), 400

    body = request.get_json(force=True, silent=True) or {}
    credential = body.get("credential")
    if not credential:
        return jsonify({"error": "credential mancante"}), 400
    cred_id_b64 = credential.get("id")
    if not cred_id_b64:
        return jsonify({"error": "credential incompleta"}), 400

    sb, err = _sb_or_error()
    if err:
        return err
    try:
        r = sb.table(_TABLE).select("*").eq("credential_id", cred_id_b64).limit(1).execute()
        rows = r.data or []
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500
    if not rows:
        return jsonify({"error": "Credenziale non riconosciuta"}), 401
    stored = rows[0]

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_origin(),
            credential_public_key=base64url_to_bytes(stored["public_key"]),
            credential_current_sign_count=stored["sign_count"],
            require_user_verification=True,
        )
    except Exception as e:
        return jsonify({"error": f"Verifica fallita: {e}"[:300]}), 401

    try:
        sb.table(_TABLE).update({
            "sign_count": verified.new_sign_count,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }).eq("credential_id", cred_id_b64).execute()
    except Exception:
        pass

    session.permanent = True
    session["ok"] = True
    return jsonify({"ok": True})
