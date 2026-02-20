# SETUP.md

# Instalare și rulare — IG Username Monitor

Documentul ăsta e “pas cu pas”: dependențe, configurare, test, apoi auto-start la reboot cu systemd.

---

## 1) Instalare dependențe

### Ubuntu / Debian
```bash
sudo apt update && sudo apt install python3 python3-pip curl -y
pip3 install requests
```

Verificare:
```bash
python3 --version
curl --version
```

---

## 2) Configurare

Editează `checker.py` și setează:
- `EMAIL_SENDER`
- `EMAIL_PASSWORD` (Gmail App Password)
- `EMAIL_RECIPIENT`
- restul (TARGET_USERNAME, intervale, quiet hours) după preferințe

### Gmail App Password
- Link: https://myaccount.google.com/apppasswords
- Ai nevoie de 2FA activat
- Generează un App Password pentru Mail și folosește codul de 16 caractere

---

## 3) Test rapid

```bash
cd /root/instagram
python3 checker.py
```

Oprire: `Ctrl + C`

Dacă nu primești email:
- verifică datele SMTP
- verifică logurile din `instagram_monitor.log`

---

## 4) Auto-start la reboot (systemd) — varianta recomandată

### 4.1 Creează service-ul
```bash
sudo nano /etc/systemd/system/ig-username-monitor.service
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

> Dacă ai repo-ul în altă cale, ajustează `WorkingDirectory` și `ExecStart`.

### 4.2 Activează și pornește
```bash
sudo systemctl daemon-reload
sudo systemctl enable ig-username-monitor.service
sudo systemctl start ig-username-monitor.service
```

### 4.3 Status + loguri
```bash
systemctl status ig-username-monitor.service
journalctl -u ig-username-monitor.service -f
```

### 4.4 Comenzi utile
```bash
sudo systemctl stop ig-username-monitor.service
sudo systemctl restart ig-username-monitor.service
sudo systemctl disable ig-username-monitor.service
```

---

## Troubleshooting rapid

- **Rate limit des (429):** crește `CHECK_INTERVAL` și/sau `JITTER_SECONDS`.
- **Gmail nu acceptă login:** folosește App Password + `SMTP_PORT=587` + `starttls()`.
- **Service nu pornește:** verifică path-ul către `python3` (`which python3`), fișierul script și `journalctl`.
