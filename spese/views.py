"""
spese/views.py — Area /spese: il conto personale.

I movimenti della P.IVA (fatturato incassato, commercialista, licenze)
vivono invece sotto /fatture/spese-piva, perche' entrano nel calcolo
fiscale. Qui c'e' solo il personale.
"""
from datetime import date

from flask import Response

from . import spese_bp
from shared.theme import render_page
from shared.design import icon
from shared.fmt import eur, eur_segno, data_breve
from shared.supabase_client import get_client, is_configured


def _diag():
    if not is_configured():
        return None
    sb = get_client()
    out = {"ultime": [], "entrate_mese": 0.0, "uscite_mese": 0.0}
    try:
        r = sb.table("spese").select("*", count="exact", head=True).execute()
        out["count"] = r.count
    except Exception as e:
        return {"err": str(e)[:200]}

    try:
        r = (sb.table("spese").select("data,importo,descrizione,tipo")
               .order("data", desc=True).limit(8).execute())
        out["ultime"] = r.data or []
    except Exception:
        pass

    today = date.today()
    d_from = today.replace(day=1).isoformat()
    try:
        r = (sb.table("spese").select("importo,tipo")
               .gte("data", d_from).lte("data", today.isoformat()).execute())
        for row in (r.data or []):
            imp = float(row.get("importo") or 0)
            t = row.get("tipo") or ""
            if t == "entrata":
                out["entrate_mese"] += imp
            elif t == "uscita":
                out["uscite_mese"] += imp
        out["saldo_mese"] = out["entrate_mese"] - out["uscite_mese"]
    except Exception:
        out["saldo_mese"] = None

    return out


@spese_bp.get("/")
def index():
    d = _diag()

    if d is None:
        content = """
        <div class="notice warn">
          Supabase non configurato. Aggiungi <code>SUPABASE_URL</code> e
          <code>SUPABASE_KEY</code> alle env vars di Render.
        </div>
        """
    elif "err" in d:
        content = f'<div class="notice err">Errore <code>spese</code>: {d["err"]}</div>'
    else:
        saldo = d.get("saldo_mese") or 0

        righe = []
        for r in d.get("ultime", []):
            imp = float(r.get("importo") or 0)
            desc = (r.get("descrizione") or "").strip() or "—"
            tipo = r.get("tipo", "")
            cls = "neg" if tipo == "uscita" else "pos" if tipo == "entrata" else ""
            firmato = imp if tipo == "entrata" else -imp
            righe.append(
                f'<div class="row">'
                f'<span class="k">{data_breve(r.get("data"))}</span>'
                f'<span class="t">{desc}</span>'
                f'<span class="v tnum {cls}">{eur_segno(firmato)}</span>'
                f'</div>'
            )
        ultimi = (
            f'<div class="card">'
            f'<div class="card-head"><div class="eyebrow">Ultimi movimenti</div></div>'
            f'<div class="rows">{"".join(righe)}</div></div>'
        ) if righe else (
            '<div class="empty">'
            + icon("spese")
            + '<div class="t">Nessun movimento</div>'
            + '<div class="s">La tabella <code>spese</code> è vuota.</div></div>'
        )

        content = f"""
        <div class="grid kpi mb-4">
          <div class="card"><div class="stat">
            <div class="val tnum {"pos" if saldo >= 0 else "neg"}">€ {eur_segno(saldo, 0)}</div>
            <div class="lbl">Saldo del mese</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum pos">€ {eur(d['entrate_mese'], 0)}</div>
            <div class="lbl">Entrate</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum neg">€ {eur(d['uscite_mese'], 0)}</div>
            <div class="lbl">Uscite</div></div></div>
          <div class="card"><div class="stat sm">
            <div class="val tnum">{d.get('count', 0)}</div>
            <div class="lbl">Movimenti totali</div></div></div>
        </div>

        <div class="grid split">
          <div class="stack">{ultimi}</div>
          <div class="stack">
            <div class="card">
              <div class="card-head"><div class="eyebrow">Due conti separati</div></div>
              <p class="small muted">
                Qui c'è il conto personale. I movimenti della P.IVA — fatturato
                incassato, commercialista, licenze — stanno sotto Fatture,
                perché entrano nel calcolo fiscale.
              </p>
              <a class="btn ghost block mt-4" href="/fatture/spese-piva">
                {icon("wallet")}Movimenti P.IVA
              </a>
            </div>

            <div class="card">
              <div class="card-head"><div class="eyebrow">In arrivo</div></div>
              <p class="small muted">
                L'inserimento dei movimenti personali non è ancora attivo da qui:
                per ora la scrittura passa dal database.
              </p>
              <span class="btn is-disabled block mt-4" aria-disabled="true">
                {icon("plus")}Nuovo movimento
              </span>
            </div>
          </div>
        </div>
        """

    return Response(
        render_page(section="spese",
                    eyebrow="Conto personale",
                    title_html='Le mie <em>spese</em>',
                    content=content),
        mimetype="text/html")
