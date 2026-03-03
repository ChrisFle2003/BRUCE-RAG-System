# Bash & Linux Komplettreferenz — Unix/Linux Command Line

> Umfassende Referenz fuer Bash-Shell und Linux-Kommandos.
> Wissensbasis fuer Claude Code + Ollama MCP Tools.

---

## 1. Dateisystem — Navigation & Verzeichnisse

```bash
# Aktuelles Verzeichnis anzeigen
pwd

# Verzeichnis wechseln
cd /home/user
cd ..                                  # Eine Ebene hoch
cd ~                                   # Home-Verzeichnis
cd -                                   # Letztes Verzeichnis

# Verzeichnis erstellen
mkdir mein_ordner
mkdir -p A/B/C                         # Verschachtelt erstellen

# Verzeichnis loeschen
rmdir mein_ordner                      # Nur wenn leer
rm -rf mein_ordner                     # Rekursiv + erzwungen

# Verzeichnisinhalt auflisten
ls                                     # Standard
ls -a                                  # Inkl. versteckte Dateien
ls -l                                  # Ausfuehrliches Format
ls -la                                 # Beide Optionen
ls -lh                                 # Menschenlesbarer Groessen
ls -S                                  # Sortiert nach Groesse
ls -t                                  # Sortiert nach Datum
ls -R                                  # Rekursiv
ls *.txt                               # Nur .txt Dateien

# Verzeichnisstruktur als Baum
tree                                   # Nur Ordner
tree -L 2                              # Max. 2 Ebenen tief
tree -I "node_modules"                 # Ausschliessen
```

---

## 2. Dateien — Kopieren, Verschieben, Loeschen

```bash
# Kopieren
cp quelle.txt ziel.txt
cp -r quelle_ordner ziel_ordner        # Rekursiv
cp -v quelle.txt ziel.txt              # Verbose (Ausgabe)
cp *.txt /backup/                      # Pattern

# Robustes Kopieren
rsync -av --delete quelle/ ziel/       # Spiegeln mit Loesch-Sync
rsync -a --progress quelle/ ziel/      # Mit Fortschrittsanzeige

# Verschieben & Umbenennen
mv alt.txt neu.txt                     # Umbenennen
mv datei.txt /ziel/                    # Verschieben
mv -v *.txt /archiv/                   # Verbose

# Loeschen
rm datei.txt
rm -i datei.txt                        # Mit Nachfrage
rm -rf ordner                          # Rekursiv (VORSICHT!)
rm *.log                               # Pattern

# Dateigroesse & Speicherplatz
du -sh datei.txt                       # Groesse einer Datei
du -sh *                               # Groessen aller Items
du -sh /*                              # Top-Level Groessen
df -h                                  # Festplatten-Speicher
df -i                                  # Inode-Auslastung
```

---

## 3. Dateiinhalt — Lesen, Schreiben, Bearbeiten

```bash
# Dateiinhalt anzeigen
cat datei.txt
less datei.txt                         # Seitenweise (q zum Beenden)
more datei.txt                         # Auch seitenweise
head -n 10 datei.txt                   # Erste 10 Zeilen
tail -n 5 datei.txt                    # Letzte 5 Zeilen
tail -f datei.txt                      # Live-Tail (wie tail -f)

# Datei erstellen / schreiben
echo "Text" > datei.txt                # Ueberschreiben
echo "Text" >> datei.txt               # Anfuegen
cat > datei.txt << EOF
Zeile 1
Zeile 2
EOF

# Text bearbeiten
sed 's/alt/neu/' datei.txt             # Ersetzen (inline)
sed -i 's/alt/neu/g' datei.txt         # Direkt in Datei + global
sed -n '5,10p' datei.txt               # Zeilen 5-10 extrahieren
sed '1d' datei.txt                     # Erste Zeile loeschen

# Zeilenanzahl, Woerter, Bytes
wc -l datei.txt                        # Zeilenanzahl
wc -w datei.txt                        # Woerteranzahl
wc -c datei.txt                        # Byte-Anzahl
wc -l *.txt                            # Alle .txt Dateien

# Sortieren & Uniqness
sort datei.txt
sort -r datei.txt                      # Umgekehrt
sort -n datei.txt                      # Numerisch
sort datei.txt | uniq                  # Duplikate entfernen
sort datei.txt | uniq -c               # Mit Haeufigkeit

# Datei-Vergleich
diff datei1.txt datei2.txt
diff -u datei1.txt datei2.txt          # Unified Format (Git-Style)
cmp datei1.txt datei2.txt              # Byte-Vergleich
```

---

## 4. Suche & Filterung

```bash
# Dateien suchen
find . -name "*.txt"                   # Nach Name
find . -name "test*" -type f           # Dateien nur
find . -type d -name "node_modules"    # Verzeichnisse nur
find . -size +100M                     # Groesser 100MB
find . -mtime -7                       # Aendert in letzten 7 Tagen
find . -name "*.log" -delete            # Loeschen (VORSICHT!)

# Suche im Dateiinhalt (grep)
grep "Begriff" datei.txt
grep -i "Begriff" datei.txt            # Case-insensitive
grep -n "Begriff" datei.txt            # Mit Zeilennummern
grep -r "Begriff" .                    # Rekursiv suchen
grep -v "Begriff" datei.txt            # Inverse Suche (NOT)
grep "^start" datei.txt                # Zeilenstart
grep "end$" datei.txt                  # Zeilenende
grep -E "regex|pattern" datei.txt      # Erweiterte Regex

# Erweiterte grep mit Regex
grep -E "^[0-9]{3}-[0-9]{4}$" datei.txt  # Telefonnummern
grep -o '[a-z]*@[a-z]*\.[a-z]*' datei.txt  # E-Mails extrahieren

# Pfade nach Dateityp suchen
locate dateiname                       # Schnelle Suche (updateldb!)
which programm                         # Wo ist das Programm?
whereis programm                       # Umfassendere Suche
```

---

## 5. Text-Verarbeitung & Awk/Sed

```bash
# awk - Feld-basierte Verarbeitung
awk '{print $1}' datei.txt             # Erste Spalte
awk '{print $1, $3}' datei.txt         # Spalte 1 und 3
awk -F',' '{print $2}' daten.csv       # CSV: Spalte 2 (Delimiter ,)
awk '{sum+=$1} END {print sum}' zahlen.txt  # Summe
awk 'NR>1 {print}' datei.txt           # Ab Zeile 2

# cut - Spalten extrahieren
cut -d',' -f2 daten.csv                # CSV: Spalte 2
cut -d':' -f1,3 /etc/passwd            # Spalten 1 und 3

# paste - Zeilen zusammenfuegen
paste datei1.txt datei2.txt            # Spaltenweise kombinieren

# tr - Zeichen ersetzen
echo "Hallo" | tr 'a-z' 'A-Z'         # Lowercase zu Uppercase
echo "Text" | tr -d 'aeiou'            # Vokale loeschen

# Zeilenumbruch
fold -w 80 datei.txt                   # Nach 80 Zeichen umbrechen
```

---

## 6. Berechtigungen & Eigentum

```bash
# Berechtigungen anzeigen
ls -l datei.txt                        # Ausfuehrliches Format

# Berechtigungen aendern
chmod 755 script.sh                    # Numerisch
chmod u+x script.sh                    # Ausfuehrbar fuer User
chmod g+r datei.txt                    # Lesbar fuer Gruppe
chmod o-w datei.txt                    # Schreiben fuer Others entfernen
chmod -R 755 ordner                    # Rekursiv

# Eigentuemer aendern
chown user datei.txt                   # Besitzer
chown user:gruppe datei.txt            # Besitzer + Gruppe
chown -R user:gruppe ordner            # Rekursiv
sudo chown ...                         # Mit Admin-Rechten

# Sticky Bit, SUID, SGID
chmod 4755 script.sh                   # SUID
chmod 2755 script.sh                   # SGID
chmod 1777 ordner                      # Sticky Bit (nur Owner kann loeschen)
```

---

## 7. Prozesse & Services

```bash
# Prozesse anzeigen
ps                                     # Aktuelle Shell-Prozesse
ps aux                                 # Alle Prozesse
ps aux | grep python                   # Nach Name filtern
top                                    # Live-Monitoring
top -n 1 | head -20                    # Einmal ausfuehren, Top 20

# Prozessinformationen
pgrep -f "prozessname"                 # PID finden
pidof apache2                          # PID eines Dienstes
ps -p 1234                             # Info zu PID
ps -aux --sort=-%mem | head -5         # Top 5 RAM-Verbraucher

# Prozess steuern
kill 1234                              # Signal SIGTERM
kill -9 1234                           # Signal SIGKILL (erzwungen)
killall firefox                        # Nach Name beenden
pkill -f "python script.py"            # Nach Pattern

# Hintergrund / Foreground
command &                              # Hintergrund starten
bg                                     # In Hintergrund
fg                                     # Vordergrund zurueck
fg %1                                  # Job %1 zu Vordergrund
jobs                                   # Alle Jobs anzeigen
nohup lange_aufgabe.sh &               # Bleibt nach Logout laufen
```

---

## 8. Systemdienste (systemd)

```bash
# Service-Status
systemctl status apache2
systemctl list-units --type=service
systemctl list-unit-files                      # Autostart-Status

# Service steuern
sudo systemctl start apache2
sudo systemctl stop apache2
sudo systemctl restart apache2
sudo systemctl reload apache2                  # Konfiguration neu laden
sudo systemctl enable apache2                  # Autostart aktivieren
sudo systemctl disable apache2                 # Autostart deaktivieren

# Logs anzeigen
journalctl -u apache2                         # Logs fuer Service
journalctl -u apache2 -n 20                   # Letzte 20 Zeilen
journalctl -u apache2 -f                      # Live-Logs (tail -f)
journalctl --since today                      # Seit heute
```

---

## 9. Netzwerk

### IP & DNS

```bash
# IP-Konfiguration
ip addr                                # Alle IP-Adressen
ip addr show eth0                      # Spezifischer Interface
ifconfig                               # Alternativ (veraltet)
hostname -I                            # IP-Adressen nur

# DNS
cat /etc/resolv.conf                   # DNS-Server anzeigen
nslookup google.com                    # DNS-Abfrage
dig google.com                         # Detaillierte DNS-Abfrage
dig google.com +short                  # Kurze Ausgabe
getent hosts localhost                 # /etc/hosts durchsuchen
```

### Verbindungstest & Ports

```bash
# Ping
ping -c 5 google.com                   # 5 Pakete
ping -i 2 google.com                   # 2 Sekunden Interval

# Port-Test
nc -zv google.com 443                  # Netcat: Port offen?
ss -tuln                               # Socket Statistics (aktiv)
ss -tulpn                              # Mit Prozessnamen
netstat -tuln                          # Alternativ (veraltet)
netstat -tulnp                         # Mit Prozessen

# Traceroute
traceroute google.com
traceroute -m 10 google.com            # Max 10 Hops

# Whois
whois google.com
```

### Downloads & Requests

```bash
# Datei herunterladen
curl -o datei.zip https://example.com/datei.zip
curl -L https://example.com/redirect   # Redirects folgen
curl -s https://api.example.com/data   # Stille Ausgabe
curl -H "Authorization: Bearer TOKEN" https://api.example.com

# Wget (Alternative)
wget https://example.com/datei.zip
wget -c https://example.com/datei.zip  # Fortsetzen
wget -O neuer_name.zip https://...     # Umbenennen

# REST-API Aufrufe
curl -X POST https://api.example.com -d '{"key":"value"}'
curl -X POST -H "Content-Type: application/json" -d '{"key":"value"}' https://api.example.com

# HTTP Status pruefen
curl -I https://example.com            # Headers nur
curl -w "%{http_code}" https://example.com  # Status Code
```

---

## 10. System & Hardware

```bash
# Systeminformationen
uname -a                               # Alle Infos
uname -s                               # Kernel-Name
uname -r                               # Kernel-Version
hostname                               # Computername

# OS-Details
cat /etc/os-release                    # OS-Information
lsb_release -a                         # (Ubuntu/Debian)
cat /etc/lsb-release

# Hardware
lsctl                                  # CPU-Informationen
lscpu | grep -E "Architecture|Cores"   # Architektur + Cores
free -h                                # RAM-Auslastung
free -h -t                             # Mit Gesamtsumme
df -h                                  # Festplatten
lsblk                                  # Block Devices
lsusb                                  # USB Devices
lspci | grep -i vga                    # GPU-Information

# Uptime & Laufzeit
uptime
cat /proc/uptime                       # Sekunden seit Boot
last reboot | head -5                  # Letzte Reboots
```

---

## 11. Benutzer & Gruppen

```bash
# Aktueller Benutzer
whoami                                 # Benutzername
id                                     # UID, GID, Gruppen
id username                            # Infos zu User

# Benutzer-Verwaltung
cat /etc/passwd                        # Alle Benutzer
getent passwd                          # Besseres Format
sudo useradd username                  # Benutzer erstellen
sudo userdel username                  # Benutzer loeschen
sudo passwd username                   # Passwort aendern
sudo usermod -aG sudo username         # Zur Sudo-Gruppe hinzufuegen

# Gruppen
groups                                 # Meine Gruppen
groups username                        # Gruppen eines Users
getent group                           # Alle Gruppen
sudo groupadd groupname                # Gruppe erstellen
sudo groupdel groupname                # Gruppe loeschen

# sudo
sudo -l                                # Berechtigungen anzeigen
sudo -i                                # Root-Shell starten
sudo -u andere_user befehl             # Als anderer User
```

---

## 12. Umgebungsvariablen & Shell-Konfiguration

```bash
# Umgebungsvariablen anzeigen
echo $PATH
echo $HOME
echo $USER
env                                    # Alle Variablen
export MEINE_VAR="Wert"                # Variable setzen

# Persistent (in ~/.bashrc oder ~/.bash_profile)
export PATH=$PATH:/neuer/pfad
export LANG=de_DE.UTF-8

# Shell-Informationen
echo $SHELL                            # Aktuelle Shell
echo $0                                # Shell-Name
bash --version                         # Bash-Version
which bash                             # Wo ist Bash?
```

---

## 13. Archive & Kompression

```bash
# TAR
tar -cf archiv.tar ordner/             # Erstellen
tar -tzf archiv.tar.gz                 # Inhalt anzeigen
tar -xf archiv.tar                     # Entpacken
tar -xzf archiv.tar.gz                 # Entpacken + Gzip
tar -xjf archiv.tar.bz2                # Entpacken + Bzip2
tar -czf archiv.tar.gz ordner/         # Erstellen + Gzip

# ZIP
zip -r archiv.zip ordner/              # Erstellen
unzip archiv.zip                       # Entpacken
unzip -l archiv.zip                    # Inhalt anzeigen
unzip -d ziel/ archiv.zip              # In Ziel entpacken

# GZ einzeln
gzip datei.txt                         # Komprimieren
gunzip datei.txt.gz                    # Dekomprimieren
```

---

## 14. Hashes & Checksums

```bash
# MD5
md5sum datei.txt
md5sum datei.txt | cut -d' ' -f1       # Nur Hash

# SHA
sha256sum datei.txt
sha1sum datei.txt
sha512sum datei.txt

# Hash vergleichen
sha256sum datei.txt > datei.sha256
sha256sum -c datei.sha256              # Vergleichen
```

---

## 15. Bash-Scripting — Grundlagen

### Variablen & Ausgabe

```bash
#!/bin/bash

# Variablen
NAME="Welt"
echo "Hallo $NAME"
echo 'Hallo $NAME'                     # Literal (keine Interpolation)

# Eingabe
read -p "Bitte eingeben: " EINGABE
echo "Du hast eingegeben: $EINGABE"

# Arithmetik
RESULT=$((5 + 3))
RESULT=$((RESULT * 2))
((COUNTER++))
echo $RESULT

# String-Operationen
TEXT="Hallo Welt"
echo ${TEXT:0:5}                       # Substring: "Hallo"
echo ${TEXT:6}                         # Ab Position 6: "Welt"
echo ${TEXT/Welt/Erde}                 # Ersetzen: "Hallo Erde"
echo ${TEXT^^}                         # Uppercase
echo ${TEXT,,}                         # Lowercase
```

### Kontrollstrukturen

```bash
# IF / ELSE
if [ $ZAHL -gt 10 ]; then
    echo "Groesser als 10"
elif [ $ZAHL -eq 10 ]; then
    echo "Genau 10"
else
    echo "Kleiner als 10"
fi

# Test-Operatoren
# -eq (gleich), -ne (ungleich), -gt (groesser), -ge (groesser/gleich)
# -lt (kleiner), -le (kleiner/gleich)
# -z (leer), -n (nicht leer)
# [ -f datei ] (ist Datei?), [ -d ordner ] (ist Verzeichnis?)

# CASE / SWITCH
case $STATUS in
    OK)    echo "Alles gut" ;;
    WARN)  echo "Warnung!" ;;
    ERROR) echo "Fehler!" ;;
    *)     echo "Unbekannt" ;;
esac

# Ternary (Bash 4+)
ERGEBNIS=$( [ $ZAHL -gt 10 ] && echo "gross" || echo "klein" )
```

### Schleifen

```bash
# FOR mit Liste
for item in apfel birne kirsche; do
    echo $item
done

# FOR mit Bereiche
for i in {1..10}; do
    echo $i
done

# FOR mit C-Stil
for ((i=0; i<10; i++)); do
    echo $i
done

# FOR mit Dateien
for file in *.txt; do
    echo $file
done

# WHILE
i=0
while [ $i -lt 10 ]; do
    echo $i
    ((i++))
done

# UNTIL
i=0
until [ $i -eq 10 ]; do
    echo $i
    ((i++))
done

# Schleifen-Kontrolle
break                                  # Schleife verlassen
continue                               # Naechste Iteration
```

### Funktionen

```bash
#!/bin/bash

# Einfache Funktion
greet() {
    echo "Hallo $1!"
}
greet "Chris"

# Mit return
is_even() {
    if [ $((($1) % 2)) -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

# Mit Ausgabe einfangen
RESULT=$(is_even 4)
echo $?                                # Exit-Code

# Lokale Variablen
my_func() {
    local LOCAL_VAR="Nur in Funktion"
    GLOBAL_VAR="Ueberall"
}
```

### Fehlerbehandlung

```bash
#!/bin/bash
set -e                                 # Beim Fehler beenden
set -u                                 # Undefined Variablen Error
set -o pipefail                        # Fehler in Pipes beachten

# Manuell
command.sh
if [ $? -ne 0 ]; then
    echo "Fehler: $?"
    exit 1
fi

# Verkettung
command1.sh && command2.sh || echo "Fehler"

# Try-Catch equivalent
{
    command.sh || { echo "Fehler!"; exit 1; }
} || { echo "Fehler gefangen"; }
```

---

## 16. Pipes & Umleitung

```bash
# Output-Umleitung
command > datei.txt                    # stdout ueberschreiben
command >> datei.txt                   # stdout anfuegen
command 2> fehler.txt                  # stderr in Datei
command 2>&1                           # stderr zu stdout
command > datei.txt 2>&1               # Beides in eine Datei
command > /dev/null 2>&1               # Alles verwerfen

# Input-Umleitung
command < eingabe.txt                  # Datei als stdin

# Pipes
cat datei.txt | grep "Begriff"         # Pipe
ps aux | grep "python" | grep -v grep  # Mehrere Pipes

# Befehlsverkettung
command1; command2                     # Sequenziell
command1 & command2                    # Parallel
command1 && command2                   # Nur wenn 1 OK
command1 || command2                   # Nur wenn 1 FEHLER
```

---

## 17. Nützliche One-Liner

```bash
# Groesste Dateien finden
find . -type f -exec ls -lh {} \; | sort -k5 -hr | head -20

# Dateien aelter als 30 Tage loeschen
find . -type f -mtime +30 -delete

# Backup mit Zeitstempel
tar -czf backup_$(date +%Y-%m-%d).tar.gz /wichtiger/ordner/

# Duplikate finden (nach Hash)
find . -type f -exec sha256sum {} \; | sort | uniq -d -w 64

# Leere Ordner loeschen
find . -type d -empty -delete

# Installierte Pakete (Debian/Ubuntu)
dpkg -l | grep "^ii"

# Offene Ports mit Prozess
ss -tulpn | grep LISTEN

# System-Uptime
uptime

# Top CPU-Verbraucher
ps aux --sort=-%cpu | head -10

# Top RAM-Verbraucher
ps aux --sort=-%mem | head -10

# Schnelles Backup (rsync)
rsync -av --delete /quelle/ /ziel/

# Batch-Umbenennung
for file in *.jpeg; do mv "$file" "${file%.jpeg}.jpg"; done

# Ordnergroessen berechnen
du -sh */ | sort -hr

# Port-Scan (einfach)
for port in {80,443,8080,3306,5432}; do echo "Port $port: $(nc -zv localhost $port 2>&1)"; done

# Komplexe Suche + Ersetzung
find . -name "*.txt" -exec sed -i 's/alt/neu/g' {} \;

# CSV in HTML Tabelle
awk -F',' '{print "<tr><td>" $1 "</td><td>" $2 "</td></tr>"}' daten.csv

# IP-Adressen aus Log extrahieren
grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' logfile.log | sort | uniq

# Groesste Verzeichnisse
du -sh /* | sort -hr | head -10

# Text-Datei in Base64
base64 < datei.txt > datei.b64
base64 -d < datei.b64 > datei.txt

# Zeitgesteuerter Backup-Job
(crontab -l 2>/dev/null; echo "0 2 * * * /scripts/backup.sh") | crontab -

# Alle .log Dateien zusammen
cat *.log | grep "ERROR" | wc -l
```

---

## 18. Cron & Geplante Aufgaben

```bash
# Crontab bearbeiten
crontab -e                             # Bearbeiten
crontab -l                             # Anzeigen
crontab -r                             # Loeschen

# Cron-Format: Minute Stunde Tag Monat Wochentag Befehl
0 2 * * * /scripts/backup.sh           # Taeglich um 2:00 Uhr
*/5 * * * * /scripts/check.sh          # Alle 5 Minuten
0 9-17 * * 1-5 /scripts/work.sh        # Mo-Fr 9-17 Uhr jede Stunde
0 0 1 * * /scripts/monatlich.sh        # Monatlich am 1.

# At-Befehl (einmalig)
at 14:30 < script.sh                   # Heute um 14:30 Uhr
at 14:30 tomorrow < script.sh          # Morgen um 14:30 Uhr
atq                                    # Geplante At-Jobs
atrm 1                                 # Job 1 loeschen
```

---

## 19. SSH & Remote-Verwaltung

```bash
# SSH-Verbindung
ssh user@host.com
ssh -p 2222 user@host.com              # Nicht-Standard-Port
ssh -i ~/.ssh/private_key user@host    # Mit privatem Key

# SCP (Datei-Transfer)
scp lokal.txt user@host.com:/remote/
scp -r user@host.com:/remote/ordner .  # Ordner lokal

# SSH-Key erstellen
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa
ssh-copy-id -i ~/.ssh/id_rsa.pub user@host  # Public Key kopieren

# SSH-Config
# ~/.ssh/config
# Host myserver
#     HostName host.com
#     User username
#     IdentityFile ~/.ssh/id_rsa
#     Port 2222

ssh myserver                           # Verbindung via Config
```

---

## 20. Package Management

```bash
# Debian / Ubuntu
sudo apt update                        # Paketliste aktualisieren
sudo apt upgrade                       # Systeme aktualisieren
sudo apt install paketname             # Paket installieren
sudo apt remove paketname              # Paket entfernen
apt search paketname                   # Paket suchen
apt show paketname                     # Paket-Details

# Rpm/Fedora/CentOS
sudo dnf install paketname
sudo dnf remove paketname
sudo dnf update

# Arch
sudo pacman -S paketname               # Installieren
sudo pacman -R paketname               # Entfernen
sudo pacman -Syu                       # Update all
```

---

## 21. Wildcards & Globbing

```bash
# * (Alles)
ls *.txt                               # Alle .txt Dateien
rm test*                               # Alle die mit "test" beginnen

# ? (Ein Zeichen)
ls file?.txt                           # file1.txt, file2.txt, ...

# [...] (Zeichenbereich)
ls file[0-9].txt                       # file0-9.txt
ls file[abc].txt                       # filea, fileb, filec

# {...} (Alternativen)
echo {a,b,c}                           # a b c
cp file.{txt,log,bak} /backup/         # Alle kopieren

# Extended Globbing (shopt -s extglob)
?(pattern)                             # 0 oder 1 Mal
*(pattern)                             # 0 oder mehr
+(pattern)                             # 1 oder mehr
!(pattern)                             # Alles ausser
```

---

## 22. Exit-Codes & $?

```bash
# Erfolg
command && echo "OK"                   # Exit-Code 0
if [ $? -eq 0 ]; then echo "OK"; fi

# Fehler
command || echo "FEHLER"               # Exit-Code != 0
command || exit 1

# Letzter Exit-Code
echo $?                                # 0 = Erfolg, != 0 = Fehler

# In Funktionen
my_function() {
    return 42
}
my_function
echo $?                                # Zeigt 42
```

---

## 23. Spezielle Variablen

```bash
$0                                     # Script-Name
$1, $2, ...                            # Parameter 1, 2, ...
$#                                     # Anzahl Parameter
$@                                     # Alle Parameter (Array)
$*                                     # Alle Parameter (String)
$?                                     # Letzter Exit-Code
$$                                     # Process ID des Scripts
$!                                     # PID letzter Background-Prozess
$-                                     # Shell-Optionen
```

---

## 24. Regex & Pattern Matching

```bash
# grep mit Regex
grep "^start" datei.txt                # Zeilenanfang
grep "end$" datei.txt                  # Zeilenende
grep -E "regex|pattern" datei.txt      # Erweiterte Regex
grep -E "^[0-9]{3}-[0-9]{4}$" datei.txt  # Muster

# sed mit Regex
sed -E 's/([0-9]+)-([0-9]+)/\2-\1/g' datei.txt  # Gruppen-Ersetzung

# Zeichenklassen
[a-z]                                  # Kleinbuchstaben
[A-Z]                                  # Grossbuchstaben
[0-9]                                  # Ziffern
[a-zA-Z0-9]                            # Alphanumerisch
\d                                     # Ziffer (in erweiterten Regex)
\w                                     # Wort-Zeichen
\s                                     # Whitespace
```

---

## 25. Debugging & Profiling

```bash
# Bash Debug-Modus
bash -x script.sh                      # Alle Befehle anzeigen
set -x                                 # In Script einschalten
set +x                                 # Ausschalten

# set-Optionen
set -e                                 # Beim Fehler beenden
set -u                                 # Undefined Variablen Error
set -o pipefail                        # Fehler in Pipes beachten
set -x                                 # Debug

# Laufzeit messen
time script.sh                         # Ausfuehrungszeit
time command                           # Auch fuer einzelne Befehle
```

---

## 26. Datei-Beobachtung

```bash
# Watch (kontinuierliche Ueberwachung)
watch -n 2 'ls -la'                    # Alle 2 Sekunden
watch 'df -h'                          # Festplatten (live)

# inotifywait (Event-basiert)
inotifywait -m -e modify datei.txt     # Auf Aenderung warten
inotifywait -r /ordner                 # Rekursiv alle Aenderungen

# tail mit Folgen
tail -f logfile.log                    # Live-Logs
tail -f logfile.log | grep "ERROR"     # Nur Fehler
```

---

## 27. Signale & Process Management

```bash
# Signale
SIGTERM (15)                           # Beenden (graceful)
SIGKILL (9)                            # Sofort beenden
SIGSTOP (19)                           # Pausieren
SIGCONT (18)                           # Fortsetzen
SIGHUP (1)                             # Hang up (neu laden)

# Signale senden
kill -TERM 1234                        # SIGTERM
kill -9 1234                           # SIGKILL
kill -HUP 1234                         # SIGHUP

# Process-Gruppen
jobs                                   # Alle Jobs
fg %1                                  # Job 1 vordergrund
bg %1                                  # Job 1 hintergrund
disown %1                              # Job vom Shell loesen
```

