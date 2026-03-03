# Entwicklung

**Lokale Entwicklung, Tests, Benchmarks und Troubleshooting für BRUCE RAG**

---

## Lokale Entwicklungsumgebung

### Python-Setup

```bash
make setup                    # Erstellt .venv und installiert Dependencies
source .venv/bin/activate     # Virtual Environment aktivieren
```

Die vollständigen Dependencies (inkl. PyTorch und sentence-transformers) stehen in `src/python/requirements.txt`. Für reine API-Entwicklung ohne GPU reicht `requirements.runtime.txt`.

### C++ Build

```bash
make build-cpp     # CMake + Build in build/
make benchmark     # C++ Benchmark ausführen
```

Erfordert C++17-Compiler, libpq-dev (PostgreSQL Client Library), OpenSSL und pthreads. Das Build-System nutzt CMake mit `-O3 -march=native` Optimierung.

### Alle Services lokal starten

```bash
make up            # Docker Compose starten
make db-init       # Schema anwenden (falls nicht automatisch)
make import-docs   # Dokumente importieren
```

---

## Projektkonventionen

### Python-Modulstruktur

Alle Python-Module liegen unter `src/python/`. Der PYTHONPATH muss darauf zeigen:

```
src/python/
├── api/           # FastAPI Endpunkte
├── embedding/     # Embedding-Erzeugung
├── calc_models/   # Inference-Backends + Prompts
├── assembler/     # Assembly-Service
└── common/        # Geteilte Module (Settings, DB, Assembly-Logik)
```

Imports verwenden absolute Pfade relativ zu `src/python/`, z.B. `from common.db import get_conn`.

### Konfiguration

Alle Konfiguration erfolgt über Umgebungsvariablen, zentralisiert in `common/settings.py` als frozen Dataclass. Keine Konfigurationsdateien werden zur Laufzeit geparst — `config/bruce.yaml` dient nur als Referenz-Dokumentation.

### Datenbankzugriff

Alle DB-Operationen laufen über `common/db.py` und den `get_conn()`-Kontextmanager. Direkter psycopg2-Zugriff außerhalb dieses Moduls ist nicht vorgesehen. Der Connection-Pool wird beim ersten Zugriff als Singleton initialisiert.

---

## Tests

### Unit-Tests ausführen

```bash
make test
# oder direkt:
PYTHONPATH=src/python python3 -m pytest tests/ -q
```

### Vorhandene Tests

**test_assembly.py** testet die Assembly-Logik mit zwei Testfällen: `test_low_confidence_filtered_from_main_text` validiert, dass Fakten mit Konfidenz < 0.70 aus dem Haupttext gefiltert und in `low_confidence_sections` verschoben werden. `test_code_is_never_filtered` stellt sicher, dass Code-Blöcke unabhängig von ihrer Konfidenz immer in den Haupttext aufgenommen werden.

**MappingTest** validiert die `dim_to_zone`-Grenzwerte: -32768 mappt auf Zone 0, 32767 mappt auf Zone 26. Dieser Test sichert die Konsistenz zwischen Python- und C++-Implementierung.

### Neue Tests hinzufügen

Tests liegen in `tests/unit/`. Das Pattern `test_*.py` wird automatisch erkannt. Für Tests, die Datenbankzugriff benötigen, muss eine laufende PostgreSQL-Instanz verfügbar sein.

---

## Benchmarks

### Retrieval-Qualität evaluieren

```bash
make eval-retrieval
# oder:
python3 scripts/eval_retrieval.py --api-base http://localhost:9998
```

Misst MRR (Mean Reciprocal Rank) und Recall@K über 6 vordefinierte Testfälle. Die Testfälle decken typische Fragen ab: Router-Funktionsweise, Startup-Sequence, pgvector-Rolle, Assembler-Konfidenz, Performance-Targets und Cross-Domain-Queries.

### Backend-Vergleich

```bash
make benchmark-backends
# oder:
python3 scripts/benchmark_backends.py --api-base http://localhost:9998 --project-root .
```

Vergleicht `extractive` vs. `hf_api` Backend über 30 End-to-End-Queries. Misst durchschnittliche und P95-Latenz sowie Assembly-Qualitätsscore. Das Script startet die Docker-Services automatisch mit dem jeweiligen Backend-Modus um und stellt danach den Standardbetrieb wieder her.

### Stress-Test

```bash
python3 scripts/real_stress_benchmark.py
```

Umfassende Test-Suite mit 5 Phasen: Progressive Load (1–10 Worker), Complex Queries, Edge Cases (leere Queries, SQL-Injection, XSS, Unicode), 90-Sekunden Dauerlast und Peak Load (20 Worker, 100 Queries). Ergebnisse werden als Markdown-Report in `BENCHMARK.md` gespeichert.

### C++ Performance

```bash
make benchmark
# oder:
./build/src/cpp/bruce_core --benchmark
```

Führt 500.000 `dim_to_zone`-Aufrufe aus und gibt die Gesamtdauer aus.

---

## Debugging

### Retrieval-Debugging

Der Debug-Endpunkt `POST /api/v1/debug/retrieval` zeigt den vollständigen Retrieval-Prozess ohne Inference:

```bash
curl -X POST http://localhost:9998/api/v1/debug/retrieval \
  -H "Content-Type: application/json" \
  -d '{"query": "Was ist pgvector?", "limit": 6}'
```

Die Response zeigt die selektierten Routen, die abgerufenen Chunks mit Similarity-Scores und Full-Paths, sowie die balancierten Merge-Ergebnisse.

### Trace-Analyse

Jede Query erzeugt Trace-Einträge in `trace_log`. Abfrage der Pipeline-Performance:

```sql
SELECT stage, duration_ms, model, gpu_device, logged_at
FROM trace_log
WHERE trace_id = 'trace_xxx'
ORDER BY logged_at;
```

Typische Stages: `embedding` (Vektorerzeugung), `cascade` (Chunk-Retrieval), `routing` (Dispatch), `inference` (Calc-Model), `assembly` (Final Answer).

### Job-Status prüfen

```sql
SELECT job_id, status, expected_routes, completed_routes,
       created_at, completed_at
FROM pipeline_jobs
ORDER BY created_at DESC
LIMIT 10;
```

### Assembler-Status

```bash
curl http://localhost:8010/health
```

Wenn `listening: false`, prüfe die PostgreSQL-Verbindung des Assembler-Containers und ob der LISTEN-Thread korrekt gestartet wurde.

---

## Häufige Probleme

### "Query blocked by whitelist"

Die Query-Text stimmt mit keinem Whitelist-Pattern überein. Prüfe die Whitelist:

```sql
SELECT pattern, match_type FROM whitelist;
```

Im Entwicklungsmodus sollte `__ALLOW_ALL__` vorhanden sein.

### Calc-Service nicht erreichbar

Die API dispatcht asynchron — ein nicht erreichbarer Calc-Service führt zu einem Timeout beim Polling. Prüfe den Health-Endpunkt:

```bash
curl http://localhost:8003/health
curl http://localhost:8012/health
```

Fallback-Verhalten: Bei Ausfall erzeugt das System einen `route_fail`-Baustein mit Konfidenz 0.45.

### Assembly findet nicht statt

Der Assembler wird über PostgreSQL NOTIFY ausgelöst. Prüfe ob der Trigger korrekt funktioniert:

```sql
SELECT * FROM calc_results WHERE job_id = '<id>' ORDER BY created_at;
SELECT expected_routes, completed_routes FROM pipeline_jobs WHERE job_id = '<id>';
```

Wenn `completed_routes` nicht alle `expected_routes` enthält, warten noch Calc-Results. Wenn alle da sind, aber kein Assembly erfolgt: Assembler-Health und LISTEN-Status prüfen.

### Langsame Retrieval-Performance

Prüfe ob die Indizes korrekt angelegt wurden:

```sql
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename IN ('vektoren', 'chunks', 'pipeline_jobs');
```

Insbesondere der HNSW-Index auf `vektoren.dims` ist kritisch für Vektor-Retrieval-Performance. Fehlt er, greift nur das Trigram-basierte Fallback.

### Docker-Container starten nicht

```bash
docker compose logs postgres    # DB-Initialisierung prüfen
docker compose logs api         # Python-Fehler prüfen
docker compose ps               # Status aller Container
```

Bei Volume-Problemen: `docker compose down -v && docker compose up -d` für einen sauberen Neustart.

---

## Erweiterung um neue Bibliotheken

1. Bibliothek in der Datenbank registrieren:

```sql
INSERT INTO bibliotheken (bib_id, name, language)
VALUES (5000, 'PHYSICS', 'en');
```

2. Dokumente importieren:

```bash
make import-docs BIB_ID=5000
```

3. Route in der Routing-Konfiguration hinzufügen (neues routing_version INSERT mit erweitertem `routes`-Array).

4. Optional: Eigenen Calc-Service für die neue Route deployen.

---

## Erweiterung um neue Backends

Neue Calc-Backends werden in `src/python/calc_models/backends.py` als Klasse implementiert, die von `ModelBackend` erbt und die `infer()`-Methode überschreibt. Die Factory-Funktion `get_backend()` muss um den neuen Backend-Namen erweitert werden. Für route-spezifische System-Prompts wird ein Eintrag in `calc_models/prompts.py` unter `SYSTEM_PROMPTS` hinzugefügt.
