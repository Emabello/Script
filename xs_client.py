"""
xs_client.py — Motore per interagire con XS (Timesheets and Expenses) di cbsoft.

Cosa fa:
  - login con username/password (mantiene la sessione tramite cookie)
  - legge il catalogo: clienti -> progetti -> task (con i relativi ID)
  - legge le ore registrate in un certo giorno
  - registra un'ora (clock on / clock off) per cliente/progetto/task

Dipendenze:
  pip install requests beautifulsoup4

Uso rapido da terminale:
  # le credenziali si possono passare via variabili d'ambiente XS_USER / XS_PASS
  # oppure verranno chieste in modo sicuro al momento

  python xs_client.py catalog                 # stampa clienti/progetti/task
  python xs_client.py day 2026-06-16          # mostra le ore di quel giorno
  python xs_client.py add 2026-06-16 10 745 2501 10:00 18:00
       #                  data        cli proj task  inizio fine

NOTA: questo e' un primo motore di test. Una volta verificato che login,
lettura e inserimento funzionano, ci costruiamo sopra il calendario e l'app.
"""

import os
import re
import sys
import getpass
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://xs.cbsoft.it"


# ---------------------------------------------------------------------------
# Strutture dati per il catalogo
# ---------------------------------------------------------------------------
@dataclass
class Task:
    id: str
    name: str


@dataclass
class Project:
    id: str
    name: str
    client_id: str
    tasks: list = field(default_factory=list)


@dataclass
class Client:
    id: str
    name: str
    projects: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Il motore
# ---------------------------------------------------------------------------
class XSClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        # un user-agent "normale" evita rifiuti di alcuni server
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (compatible; XSClient/0.1)"}
        )
        self._logged_in = False

    # ---- login ------------------------------------------------------------
    def login(self, username, password):
        """Esegue il login. Solleva un'eccezione se fallisce."""
        url = f"{self.base_url}/login.php"
        data = {
            "redirect": "",
            "username": username,
            "password": password,
            "Login": "submit",
        }
        r = self.session.post(url, data=data, allow_redirects=True, timeout=30)
        r.raise_for_status()

        # Se siamo ancora sulla pagina di login, le credenziali sono sbagliate.
        if self._looks_like_login(r.text):
            raise RuntimeError(
                "Login fallito: controlla username e password "
                "(oppure il sito ha cambiato la pagina di accesso)."
            )
        # conserviamo le credenziali in memoria per poter rifare il login
        # se la sessione scade (non vengono mai scritte su disco)
        self._user = username
        self._pwd = password
        self._logged_in = True
        return True

    @staticmethod
    def _looks_like_login(html):
        return 'name="loginForm"' in html or "Timesheet Login" in html

    def _relogin(self):
        if not getattr(self, "_user", None):
            raise RuntimeError("Sessione scaduta e nessuna credenziale in memoria.")
        self.login(self._user, self._pwd)

    def _require_login(self):
        if not self._logged_in:
            raise RuntimeError("Devi prima fare login().")

    # ---- lettura di una pagina giornaliera --------------------------------
    def _fetch_daily_page(self, year, month, day):
        self._require_login()
        url = (
            f"{self.base_url}/daily.php"
            f"?month={month}&year={year}&day={day}"
            f"&client_id=0&proj_id=0&task_id=0"
        )
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        # se la sessione e' scaduta XS ci rimanda al login: rifacciamo
        # l'accesso e riproviamo una volta sola
        if self._looks_like_login(r.text):
            self._relogin()
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
        return r.text

    # ---- catalogo (clienti/progetti/task) ---------------------------------
    def get_catalog(self, year=2026, month=6, day=16):
        """
        Estrae il catalogo dai dati JavaScript incorporati nella pagina daily.
        Restituisce un dict {client_id: Client}.
        """
        html = self._fetch_daily_page(year, month, day)
        return self._parse_catalog(html)

    @staticmethod
    def _parse_catalog(html):
        clients = {}      # id -> Client
        projects = {}     # id -> Project

        # nomi clienti:  clientProjectsHash['10']['name'] = 'Logica';
        for cid, name in re.findall(
            r"clientProjectsHash\['(\d+)'\]\['name'\] = '(.*?)';", html
        ):
            clients[cid] = Client(id=cid, name=name)

        # nomi progetti: projectTasksHash['745']['name'] = 'LG1000 - ...';
        proj_names = dict(
            re.findall(r"projectTasksHash\['(\d+)'\]\['name'\] = '(.*?)';", html)
        )

        # associazione progetto -> cliente:
        #   clientProjectsHash['10']['projects'][numProjects] = 745;
        for cid, pid in re.findall(
            r"clientProjectsHash\['(\d+)'\]\['projects'\]\[numProjects\] = (\d+);",
            html,
        ):
            pname = proj_names.get(pid, f"(progetto {pid})")
            proj = Project(id=pid, name=pname, client_id=cid)
            projects[pid] = proj
            if cid in clients:
                clients[cid].projects.append(proj)

        # task:  projectTasksHash['745']['tasks']['2501'] = 'Default Task';
        for pid, tid, tname in re.findall(
            r"projectTasksHash\['(\d+)'\]\['tasks'\]\['(\d+)'\] = '(.*?)';", html
        ):
            if pid in projects:
                projects[pid].tasks.append(Task(id=tid, name=tname))

        return clients

    # ---- lettura ore di un giorno -----------------------------------------
    def get_day_entries(self, year, month, day):
        """
        Restituisce la lista delle ore registrate in un giorno.
        Ogni voce: dict con client/project/task/start/end/total/trans_num.
        """
        html = self._fetch_daily_page(year, month, day)
        return self._parse_day_entries(html)

    @staticmethod
    def _parse_day_entries(html):
        if "No hours recorded" in html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        entries = []
        table = soup.find("table", class_="table_body")
        if not table:
            return entries

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            # le righe dati hanno 8 colonne (Client..Actions)
            if len(cells) < 7:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            # salta l'header
            if texts[0].lower() == "client":
                continue

            # cerca il trans_num nella riga: compare sia nel link Delete
            # (href="javascript:delete_entry(58999);") sia nel link Details
            # (edit.php?...&trans_num=58999&...). Cerchiamo entrambi.
            trans_num = None
            row_html = str(row)
            m = re.search(r"delete_entry\((\d+)\)", row_html)
            if not m:
                m = re.search(r"trans_num=(\d+)", row_html)
            if m:
                trans_num = m.group(1)

            entries.append(
                {
                    "client": texts[0],
                    "project": texts[1],
                    "task": texts[2],
                    "start": texts[4] if len(texts) > 4 else "",
                    "end": texts[5] if len(texts) > 5 else "",
                    "total": texts[6] if len(texts) > 6 else "",
                    "trans_num": trans_num,
                }
            )
        return entries

    # ---- inserimento ore ---------------------------------------------------
    def add_entry(
        self,
        year,
        month,
        day,
        client_id,
        proj_id,
        task_id,
        start_hour,
        start_min,
        end_hour,
        end_min,
        log_message="",
    ):
        """
        Registra un'ora (clock on + clock off) per la combinazione indicata.
        Gli orari sono interi (es. start_hour=10, start_min=0).

        XS richiede DUE passaggi: prima la timbratura, poi una pagina che
        chiede un "log message"; l'ora viene salvata solo confermando quella
        seconda pagina (campo log_message_presented=1).
        """
        self._require_login()
        url = f"{self.base_url}/action.php"
        referer = (
            f"{self.base_url}/daily.php"
            f"?month={month}&year={year}&day={day}"
            f"&client_id=0&proj_id=0&task_id=0"
        )
        headers = {"Referer": referer, "Origin": self.base_url}

        # --- TAPPA 1: timbratura (porta alla pagina del log message) -------
        step1 = [
            ("destination", "daily"),
            ("year", str(year)),
            ("month", str(month)),
            ("day", str(day)),
            ("client_id", str(client_id)),
            ("proj_id", str(proj_id)),
            ("task_id", str(task_id)),
            ("origin", "/daily.php"),
            ("destination", "/daily.php"),
            ("clientSelect", str(client_id)),
            ("projectSelect", str(proj_id)),
            ("taskSelect", str(task_id)),
            ("clock_on_check", "on"),
            ("clock_on_time_hour", str(start_hour)),
            ("clock_on_time_min", str(start_min)),
            ("clock_off_check", "on"),
            ("clock_off_time_hour", str(end_hour)),
            ("clock_off_time_min", str(end_min)),
        ]
        self.session.post(
            url, data=step1, headers=headers, allow_redirects=True, timeout=30
        ).raise_for_status()

        # --- TAPPA 2: conferma "Done" della pagina log message -------------
        # qui c'e' log_message_presented=1: e' questo che salva davvero l'ora
        step2 = [
            ("origin", "/daily.php"),
            ("destination", "/daily.php"),
            ("clock_on_time_hour", str(start_hour)),
            ("clock_off_time_hour", str(end_hour)),
            ("clock_on_time_min", str(start_min)),
            ("clock_off_time_min", str(end_min)),
            ("year", str(year)),
            ("month", str(month)),
            ("day", str(day)),
            ("client_id", str(client_id)),
            ("proj_id", str(proj_id)),
            ("task_id", str(task_id)),
            ("clockonoff", "clockonandoff"),
            ("log_message_presented", "1"),
            ("log_message", log_message),
        ]
        r = self.session.post(
            url, data=step2, headers=headers, allow_redirects=True, timeout=30
        )
        r.raise_for_status()
        return r

    # ---- cancellazione di una voce ----------------------------------------
    def delete_entry(self, year, month, day, trans_num):
        """Cancella una voce dato il suo trans_num (preso da get_day_entries)."""
        self._require_login()
        referer = (
            f"/daily.php?month={month}&year={year}&day={day}"
            f"&client_id=0&proj_id=0&task_id=0"
        )
        url = (
            f"{self.base_url}/delete.php"
            f"?client_id=1&proj_id=0&task_id=0"
            f"&referer={requests.utils.quote(referer, safe='')}"
            f"&trans_num={trans_num}"
        )
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        return True


# ---------------------------------------------------------------------------
# Helper per le credenziali
# ---------------------------------------------------------------------------
def _get_credentials():
    user = os.environ.get("XS_USER") or input("Username XS: ").strip()
    pwd = os.environ.get("XS_PASS") or getpass.getpass("Password XS: ")
    return user, pwd


def _parse_time(s):
    """'10:00' -> (10, 0); '18:30' -> (18, 30)."""
    h, m = s.split(":")
    return int(h), int(m)


# ---------------------------------------------------------------------------
# Interfaccia a riga di comando (per i primi test)
# ---------------------------------------------------------------------------
def main(argv):
    if not argv:
        print(__doc__)
        return

    cmd = argv[0]
    client = XSClient()
    user, pwd = _get_credentials()
    client.login(user, pwd)
    print("Login OK.\n")

    if cmd == "catalog":
        catalog = client.get_catalog()
        for c in catalog.values():
            print(f"[{c.id}] {c.name}")
            for p in c.projects:
                print(f"    proj {p.id}: {p.name}")
                for t in p.tasks:
                    print(f"        task {t.id}: {t.name}")

    elif cmd == "day":
        year, month, day = map(int, argv[1].split("-"))
        entries = client.get_day_entries(year, month, day)
        if not entries:
            print("Nessuna ora registrata in questo giorno.")
        for e in entries:
            print(
                f"  {e['start']}-{e['end']} ({e['total']})  "
                f"{e['client']} / {e['project']} / {e['task']}  "
                f"[trans_num={e['trans_num']}]"
            )

    elif cmd == "add":
        # add  AAAA-MM-GG  client_id  proj_id  task_id  HH:MM  HH:MM
        year, month, day = map(int, argv[1].split("-"))
        client_id, proj_id, task_id = argv[2], argv[3], argv[4]
        sh, sm = _parse_time(argv[5])
        eh, em = _parse_time(argv[6])
        client.add_entry(
            year, month, day, client_id, proj_id, task_id, sh, sm, eh, em
        )
        print("Inviato. Ecco cosa risulta ora nel giorno:")
        for e in client.get_day_entries(year, month, day):
            print(
                f"  {e['start']}-{e['end']} ({e['total']})  "
                f"{e['client']} / {e['project']} / {e['task']}"
            )

    else:
        print(f"Comando sconosciuto: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])