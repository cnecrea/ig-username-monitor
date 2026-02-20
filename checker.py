#!/usr/bin/env python3
"""
Instagram Username Monitor — v1.0 (curl + quiet hours simplificate)
=====================================================================
- curl-based (confirmat funcțional)
- Quiet hours 00:00–09:00: verifică, dar NU trimite emailuri
- Dacă username-ul devine disponibil în quiet hours:
  → stochează UN SINGUR flag
  → la prima verificare după 09:00 trimite O SINGURĂ alertă
- Restul alertelor din quiet hours sunt ignorate (nu se acumulează)
"""

import subprocess
import time
import smtplib
import logging
import random
import json
import sys
import os
import tempfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

TARGET_USERNAME = "IG_USERNAME"

CHECK_INTERVAL = 1800
JITTER_SECONDS = 300

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_SENDER = "email@gmail.com"
EMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"
EMAIL_RECIPIENT = "email@gmail.com"

QUIET_START = 0   # 00:00
QUIET_END = 9     # 09:00

# ============================================================
# LOGGING
# ============================================================

LOG_FILE = "instagram_monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

COOKIE_FILE = os.path.join(tempfile.gettempdir(), "ig_monitor_cookies.txt")

# Flag: username-ul a fost găsit disponibil în quiet hours
found_available_during_quiet = False
found_available_timestamp = None


# ============================================================
# QUIET HOURS
# ============================================================

def is_quiet_hours() -> bool:
    hour = datetime.now().hour
    return QUIET_START <= hour < QUIET_END


# ============================================================
# CURL
# ============================================================

def curl_get_cookies() -> str:
    ua = random.choice(USER_AGENTS)
    cmd = [
        "curl", "-s",
        "-c", COOKIE_FILE,
        "-H", f"User-Agent: {ua}",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-o", "/dev/null",
        "https://www.instagram.com/"
    ]

    try:
        subprocess.run(cmd, timeout=30, capture_output=True)

        if not os.path.exists(COOKIE_FILE):
            return None

        csrf = None
        with open(COOKIE_FILE, "r") as f:
            for line in f:
                if "csrftoken" in line:
                    parts = line.strip().split("\t")
                    if len(parts) >= 7:
                        csrf = parts[6]
                        break

        if csrf:
            log.info(f"Am luat un CSRF ok: {csrf[:8]}…")
        else:
            log.warning("Nu am găsit csrftoken în fișierul de cookies.")

        return csrf

    except Exception as e:
        log.error(f"N-am reușit să obțin cookies (eroare: {e}).")
        return None


def curl_check_username(csrf: str, username: str) -> dict:
    ua = random.choice(USER_AGENTS)
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"

    cmd = [
        "curl", "-s",
        "-w", "\n__HTTP_CODE__:%{http_code}",
        "-b", COOKIE_FILE,
        "-H", f"User-Agent: {ua}",
        "-H", f"X-CSRFToken: {csrf}",
        "-H", "X-IG-App-ID: 936619743392459",
        "-H", "X-Requested-With: XMLHttpRequest",
        "-H", f"Referer: https://www.instagram.com/{username}/",
        "-H", "Sec-Fetch-Dest: empty",
        "-H", "Sec-Fetch-Mode: cors",
        "-H", "Sec-Fetch-Site: same-origin",
        url
    ]

    try:
        result = subprocess.run(cmd, timeout=30, capture_output=True, text=True)
        output = result.stdout

        http_code = 0
        body = output
        if "__HTTP_CODE__:" in output:
            parts = output.rsplit("__HTTP_CODE__:", 1)
            body = parts[0]
            try:
                http_code = int(parts[1].strip())
            except ValueError:
                pass

        if http_code == 429:
            return {"status": "rate_limited", "http_code": 429, "detail": "Instagram ne limitează (429). Mai rar, apoi reiau."}

        if "Page Not Found" in body:
            return {"status": "not_found", "http_code": http_code, "detail": "Pagina nu există — username-ul pare liber."}

        if body.lstrip().startswith("{"):
            try:
                data = json.loads(body)
                user = data.get("data", {}).get("user")

                if user is None:
                    return {"status": "not_found", "http_code": http_code, "detail": "Am primit user=null — username-ul pare liber."}

                full_name = user.get("full_name", "")
                is_private = user.get("is_private", False)
                followers = user.get("edge_followed_by", {}).get("count", "?")
                priv = "da" if is_private else "nu"
                name_part = f"„{full_name}”" if full_name else "fără nume"
                return {"status": "taken", "http_code": http_code, "detail": f"Este luat: {name_part}, privat={priv}, followers={followers}"}
            except json.JSONDecodeError:
                pass

        if "login" in body.lower()[:2000] and "Page Not Found" not in body:
            return {"status": "error", "http_code": http_code, "detail": "Instagram cere login — nu pot citi profilul acum."}

        snippet = body[:150].replace("\n", " ").strip()
        return {"status": "unknown", "http_code": http_code, "detail": f"Răspuns neclar (HTTP {http_code}). Fragment: {snippet}"}

    except subprocess.TimeoutExpired:
        return {"status": "error", "http_code": 0, "detail": "Cererea a expirat (timeout)."}
    except Exception as e:
        return {"status": "error", "http_code": 0, "detail": f"A apărut o eroare: {e}"}


# ============================================================
# EMAIL
# ============================================================

def send_email(subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECIPIENT
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        log.info(f"Am trimis email către {EMAIL_RECIPIENT}.")
        return True
    except Exception as e:
        log.error(f"N-am putut trimite emailul (eroare: {e}).")
        return False


def send_notification(username: str, result: dict, extra_note: str = ""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_raw = result.get("status", "unknown")
    is_available = status_raw == "not_found"

    # Subiecte clare, fără dramatism / iconițe
    if is_available:
        subject = f"Username posibil liber: @{username}"
    elif status_raw == "rate_limited":
        subject = f"Instagram ne limitează temporar — @{username}"
    elif status_raw in ("error", "unknown"):
        subject = f"Problemă la verificare — @{username}"
    elif status_raw == "taken":
        subject = f"Este luat: @{username}"
    else:
        subject = f"Update @{username}: {status_raw}"

    status = str(status_raw).upper()
    http_code = result.get("http_code", "—")
    detail = result.get("detail", "—")

    # Body fără bullets; aliniat și “uman”
    body = (
        f"Salut,\n\n"
        f"Am verificat @{username} la {timestamp}.\n\n"
        f"Status:   {status}\n"
        f"HTTP:     {http_code}\n"
        f"Detalii:  {detail}\n"
    )

    if extra_note:
        body += f"\nNotă: {extra_note}\n"

    if is_available:
        body += (
            "\nDacă vrei să îl iei, încearcă acum:\n"
            "Instagram → Settings → Edit Profile → Username\n"
            f"Setează username la: {username}\n"
            f"\nLink: https://www.instagram.com/{username}/\n"
            "\nUneori fereastra e scurtă — dacă nu merge din prima, încearcă imediat încă o dată.\n"
        )
    else:
        body += "\nÎți scriu doar când se schimbă statusul, ca să nu te spamez.\n"

    send_email(subject, body)


# ============================================================
# MAIN
# ============================================================

def main():
    global found_available_during_quiet, found_available_timestamp

    def quiet_range() -> str:
        return f"{QUIET_START:02d}:00–{QUIET_END:02d}:00"

    interval_min = CHECK_INTERVAL // 60

    log.info("=" * 60)
    log.info(f"Instagram Monitor v1.0 — @{TARGET_USERNAME}")
    log.info(f"Verific la ~{interval_min} minute.")
    log.info(f"În intervalul {quiet_range()} nu trimit emailuri.")
    log.info(f"Email notificări: {EMAIL_RECIPIENT}")
    log.info("=" * 60)

    csrf = curl_get_cookies()
    if not csrf:
        log.error("N-am reușit să iau cookies. Mai încerc o dată peste 60 secunde...")
        time.sleep(60)
        csrf = curl_get_cookies()
        if not csrf:
            log.error("Tot nimic la cookies. Mă opresc aici.")
            sys.exit(1)

    delay = random.uniform(4, 7)
    log.info(f"Aștept {delay:.1f}s (jitter) înainte de prima verificare.")
    time.sleep(delay)

    if not is_quiet_hours():
        send_email(
            f"Monitor pornit pentru @{TARGET_USERNAME}",
            (
                f"Salut,\n\n"
                f"Am pornit monitorul pentru @{TARGET_USERNAME}.\n\n"
                f"Verific la aproximativ {interval_min} minute (cu un mic jitter).\n"
                f"Între {quiet_range()} nu trimit emailuri.\n"
                f"Dacă apare disponibil în intervalul acesta, rețin momentul și te anunț imediat după.\n"
            ),
        )

    last_status = None
    check_count = 0
    consecutive_errors = 0
    was_quiet = is_quiet_hours()

    while True:
        try:
            check_count += 1
            now_quiet = is_quiet_hours()

            # ─── IEȘIRE DIN QUIET HOURS ───
            if was_quiet and not now_quiet:
                if found_available_during_quiet:
                    log.warning("Am ieșit din quiet hours — username-ul a fost detectat ca liber în timpul nopții. Trimit notificarea acum.")
                    send_notification(
                        TARGET_USERNAME,
                        {
                            "status": "not_found",
                            "http_code": 0,
                            "detail": "L-am văzut ca posibil liber în quiet hours. Acum îți trimit alerta.",
                        },
                        extra_note=f"Detectat la {found_available_timestamp}",
                    )
                    found_available_during_quiet = False
                    found_available_timestamp = None

            was_quiet = now_quiet

            if now_quiet:
                log.info(f"[{check_count}] Quiet hours ({quiet_range()}) — verific în continuare, doar că nu trimit emailuri.")

            # Reînnoiește cookies la fiecare 8 verificări
            if check_count > 1 and check_count % 8 == 0:
                log.info("Refac cookies (refresh periodic)...")
                new_csrf = curl_get_cookies()
                if new_csrf:
                    csrf = new_csrf
                    time.sleep(random.uniform(4, 7))
                else:
                    log.warning("N-am reușit refresh-ul de cookies. Continui cu ce am.")

            # ─── VERIFICARE ───
            result = curl_check_username(csrf, TARGET_USERNAME)
            status = result.get("status", "unknown")
            http_code = result.get("http_code", "—")
            detail = result.get("detail", "—")

            log.info(f"[{check_count}] @{TARGET_USERNAME} → {status} (HTTP {http_code}) — {detail}")

            # ─── RATE LIMITED ───
            if status == "rate_limited":
                pause = random.randint(3600, 5400)
                log.warning(f"Suntem limitați momentan. Pun pauză ~{pause // 60} min, apoi reiau cu cookies noi.")
                time.sleep(pause)
                csrf = curl_get_cookies()
                if csrf:
                    time.sleep(random.uniform(4, 7))
                else:
                    log.warning("După pauză n-am reușit să refac cookies. Voi mai încerca la următoarea rundă.")
                continue

            # ─── ERORI REPETATE ───
            if status in ("error", "unknown"):
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    msg = "Am avut 5 verificări la rând cu probleme. Pun pauză 30 min și reiau cu cookies noi."
                    log.warning(msg)
                    if not now_quiet:
                        send_notification(
                            TARGET_USERNAME,
                            {
                                "status": "erori_repetate",
                                "http_code": 0,
                                "detail": msg,
                            },
                        )
                    time.sleep(1800)
                    csrf = curl_get_cookies()
                    consecutive_errors = 0
                    continue
            else:
                consecutive_errors = 0

            # ─── NOTIFICARE / QUIET HOURS LOGIC ───
            status_changed = last_status is not None and status != last_status
            first_check_available = last_status is None and status == "not_found"

            if status_changed or first_check_available:
                if now_quiet:
                    # În quiet hours: doar reținem dacă e disponibil
                    if status == "not_found" and not found_available_during_quiet:
                        found_available_during_quiet = True
                        found_available_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        log.warning(f"L-am prins ca posibil liber în quiet hours (la {found_available_timestamp}). Îți scriu imediat după ce se termină quiet hours.")
                    elif status != "not_found":
                        log.info(f"Status schimbat în quiet hours ({last_status} → {status}). Nu trimit email.")
                else:
                    # În afara quiet hours: trimite normal
                    log.warning(f"Status schimbat ({last_status} → {status}). Trimit notificare.")
                    send_notification(TARGET_USERNAME, result)

            last_status = status

            # ─── SLEEP ───
            jitter = random.randint(0, JITTER_SECONDS)
            sleep_time = CHECK_INTERVAL + jitter
            log.info(f"Următoarea verificare în ~{sleep_time // 60} min.")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            log.info("Oprit manual (Ctrl+C).")
            sys.exit(0)
        except Exception as e:
            log.error(f"A apărut o eroare neașteptată: {e}. Reîncerc peste 60 secunde.")
            time.sleep(60)


if __name__ == "__main__":
    main()
