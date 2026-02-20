# README.md

# IG Username Monitor (Instagram) — v1.0

Script simplu care verifică periodic un username pe Instagram și îți trimite email când se schimbă statusul.

> Pentru instalare și rulare completă (inclusiv systemd), vezi [SETUP.md](SETUP.md).

## Ce face (pe scurt)
- Verifică username-ul folosind `curl` + cookies/CSRF.
- Trimite email **doar când se schimbă statusul** (ca să nu te spameze).
- Are **quiet hours** (implicit `00:00–09:00`): verifică în continuare, dar **nu trimite emailuri**.
- Dacă detectează „posibil liber” în quiet hours, **reține momentul** și trimite **o singură alertă** imediat după ce se termină quiet hours.

## Cerințe
- Linux server (recomandat)
- `python3`
- `curl`
- acces la un SMTP (implicit Gmail)

Verificare rapidă:
```bash
python3 --version
curl --version
```

## Configurare
Deschide `checker.py` și ajustează secțiunea `CONFIG`:

- `TARGET_USERNAME` — username-ul monitorizat
- `CHECK_INTERVAL` — la câte secunde verifică (ex. 1800 = 30 min)
- `JITTER_SECONDS` — random extra delay, ca să nu fie “fix”
- `SMTP_SERVER`, `SMTP_PORT`, `EMAIL_SENDER`, `EMAIL_PASSWORD`, `EMAIL_RECIPIENT`
- `QUIET_START`, `QUIET_END` — intervalul în care nu vrei emailuri

### Gmail (recomandat)
Dacă folosești Gmail, cel mai bine e să folosești **App Password** (nu parola contului).

## Rulare manuală
```bash
cd /root/instagram
python3 checker.py
```

Oprire: `Ctrl + C`

## Loguri
- Fișier local: `instagram_monitor.log` (în directorul unde rulează scriptul)
- Dacă rulează ca service: `journalctl` (vezi mai jos)

---

# Auto-start la reboot (systemd) — varianta recomandată

> Pașii detaliați sunt în `SETUP.md`. Mai jos e varianta “rapidă”.

## 1) Creează service-ul
```bash
nano /etc/systemd/system/ig-username-monitor.service
```

Conținut:
```ini
[Unit]
Description=IG Username Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/instagram
ExecStart=/usr/bin/python3 /root/instagram/checker.py
Restart=always
RestartSec=10
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
```

> Dacă repo-ul tău e în altă locație, schimbă `WorkingDirectory` și `ExecStart` corespunzător.

## 2) Activează și pornește
```bash
systemctl daemon-reload
systemctl enable ig-username-monitor.service
systemctl start ig-username-monitor.service
```

## 3) Status + loguri
Status:
```bash
systemctl status ig-username-monitor.service
```

Loguri live:
```bash
journalctl -u ig-username-monitor.service -f
```

## Comenzi utile
```bash
systemctl stop ig-username-monitor.service
systemctl restart ig-username-monitor.service
systemctl disable ig-username-monitor.service
```

---

## Ce statusuri poți vedea
- `taken` — username-ul există (profil găsit)
- `not_found` — „Page Not Found” / `user=null` (scriptul îl tratează ca „posibil liber”)
- `rate_limited` — 429 (scriptul pune pauză mai mare și reia)
- `error` — timeout / Instagram cere login / alte erori
- `unknown` — răspuns neclar (se loghează un fragment)

## Troubleshooting rapid
- Dacă vezi multe `rate_limited`: crește `CHECK_INTERVAL` și/sau `JITTER_SECONDS`.
- Dacă Gmail refuză login: folosește App Password și verifică `SMTP_PORT=587` + `starttls()`.
- Dacă service nu pornește: verifică `WorkingDirectory`, calea la `python3` și logurile din `journalctl`.
