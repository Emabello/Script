"""
spese/views.py — Area /spese, in stile launchpad B2F.
"""
from datetime import date

from flask import Response

from . import spese_bp
from shared.theme import render_page
from shared.supabase_client import get_client, is_configured


def _fmt(v: float) -> str:
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


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
               .order("data", desc=True).limit(5).execute())
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
            if t == "entrata": out["entrate_mese"] += imp
            elif t == "uscita": out["uscite_mese"] += imp
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
        sign  = "+" if saldo >= 0 else "\u2212"
        col   = "var(--emerald)" if saldo >= 0 else "var(--danger)"

        rows = []
        for r in d.get("ultime", []):
            imp  = float(r.get("importo") or 0)
            desc = (r.get("descrizione") or "").strip() or "—"
            tipo = r.get("tipo", "")
            s = "\u2212" if tipo == "uscita" else "+" if tipo == "entrata" else ""
            cls = "neg" if tipo == "uscita" else "pos" if tipo == "entrata" else ""
            rows.append(
                f'<div class="row">'
                f'<div class="d">{r.get("data","")}</div>'
                f'<div class="t">{desc}</div>'
                f'<div class="a {cls} tnum">{s}{_fmt(imp)}</div>'
                f'</div>'
            )
        ultime_block = (f'<div class="card">'
                        f'<div class="eyebrow" style="margin-bottom:10px">Ultime 5</div>'
                        f'<div class="rows">{"".join(rows)}</div></div>' if rows else "")

        content = f"""
        <div class="card">
          <div class="eyebrow" style="margin-bottom:8px">Saldo mese corrente</div>
          <div class="stat">
            <div class="num tnum" style="color:{col}">{sign}€ {_fmt(abs(saldo))}</div>
            <div class="lbl">Netti</div>
          </div>
          <div style="display:flex;gap:22px;margin-top:14px;font-size:12.5px;
                      color:var(--muted);letter-spacing:.04em">
            <div>Entrate <span class="tnum" style="color:var(--emerald);font-weight:500">+{_fmt(d['entrate_mese'])}</span></div>
            <div>Uscite <span class="tnum" style="color:var(--danger);font-weight:500">\u2212{_fmt(d['uscite_mese'])}</span></div>
          </div>
        </div>

        <div class="card">
          <div class="stat">
            <div class="num tnum">{d.get('count', 0)}</div>
            <div class="lbl">Righe totali</div>
          </div>
        </div>

        {ultime_block}

        <div style="display:flex;gap:10px;margin-top:18px">
          <a class="btn is-disabled" href="#" aria-disabled="true">Nuova spesa</a>
        </div>
        <div style="color:var(--faint);font-size:11px;margin-top:10px;
                    letter-spacing:.05em;text-transform:uppercase">
          Disponibile dallo step 7
        </div>
        """

    return Response(
        render_page(section="spese",
                    eyebrow="Movimenti",
                    title_html='Le mie <em>spese</em>',
                    content=content),
        mimetype="text/html")
