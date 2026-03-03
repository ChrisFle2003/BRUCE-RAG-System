# Deployment

**Docker-Setup, GPU-Konfiguration und Produktionsbetrieb des BRUCE RAG Systems**

---

## Docker Compose

Das System wird über `docker-compose.yml` orchestriert und umfasst fünf Services: PostgreSQL (pgvector), API-Gateway, Calc BRUCE, Calc DOCS_DE und Assembler.

### Service-Topologie

```
docker compose up -d

  postgres        (:5433 → :5432)   pgvector/pgvector:pg15
  api             (:9998)           FastAPI Gateway
  calc_bruce      (:8003)           Calc Service (Route BRUCE)
  calc_docs_de    (:8012 → :8002)   Calc Service (Route DOCS_DE)
  assembler       (:8010 → :8000)   Assembly via PG LISTEN/NOTIFY
```

Alle Python-Services verwenden dasselbe Dockerfile (`src/python/Dockerfile`) auf Basis von `python:3.11-slim`. Die Runtime-Dependencies sind in `requirements.runtime.txt` minimiert (FastAPI, uvicorn, psycopg2-binary, pydantic, httpx, numpy — kein PyTorch im Container).

### Datenbank-Initialisierung

Die SQL-Dateien in `schema/` werden beim ersten Start automatisch als Init-Scripts ausgeführt (Volume-Mount auf `/docker-entrypoint-initdb.d`). Bei bestehenden Daten erfolgt kein erneutes Ausführen. Für manuelle Reinitialisierung: `docker compose down -v && docker compose up -d`.

### Persistent Storage

PostgreSQL-Daten liegen im Docker-Volume `postgres_data`. Dieses Volume überlebt Container-Neustarts, wird aber durch `docker compose down -v` gelöscht.

---

## Umgebungsvariablen pro Service

### API-Gateway

```yaml
DB_HOST: postgres
DB_PORT: 5432
DB_NAME: bruce_rag
DB_USER: bruce
DB_PASSWORD: secretpassword
```

### Calc Services

Zusätzlich zu den DB-Variablen:

```yaml
CALC_BACKEND: granite          # oder: extractive, hf, hf_api
HF_FALLBACK_ENABLED: 1         # HF-Fallback bei niedriger Konfidenz
HF_FALLBACK_MIN_CONF: 0.68     # Konfidenz-Schwelle für Fallback
HF_API_TOKEN: hf_...           # HuggingFace API Token
HF_API_MODEL: google/flan-t5-base
```

Der `CALC_BACKEND` bestimmt das primäre Inference-Backend: `extractive` für schnelle snippet-basierte Extraktion ohne LLM, `granite` für llama.cpp mit IBM Granite 350M, `hf` für lokale HuggingFace-Modelle, und `hf_api` für die HuggingFace Inference API.

---

## GPU-Setup (Granite / llama.cpp)

### Voraussetzungen

CUDA 12.1+ mit nvcc, cmake und ninja-build. Unterstützte GPUs: RTX 3080 (sm_86, Ampere) und RTX 4060 Ti (sm_89, Ada Lovelace).

### llama.cpp Build

```bash
./scripts/build_llama_cuda.sh
```

Das Script klont llama.cpp nach `~/llama.cpp`, konfiguriert CMake mit Ninja und CUDA-Unterstützung für die Architekturen sm_86 und sm_89, und baut das Projekt parallel. Das resultierende Binary liegt in `~/llama.cpp/build/bin/llama-server`.

### Granite-Modell

Das System verwendet IBM Granite 3.2 350M im Q8-Format (ca. 370 MB Weights, ca. 100 MB KV-Cache bei ctx=2048). Modell beschaffen über Ollama (`ollama pull granite4:350m-h-q8_0`) oder als GGUF-Datei direkt herunterladen.

### Calc-Server starten

```bash
# Port 8001, GPU 0 (RTX 3080)
./scripts/run_calc_server.sh 8001 0 /models/granite4-350m-h-q8_0.gguf

# Port 8003, GPU 1 (RTX 4060 Ti)
./scripts/run_calc_server.sh 8003 1 /models/granite4-350m-h-q8_0.gguf
```

Jede Instanz benötigt ca. 470 MB VRAM. Auf einer RTX 3080 (10 GB) sind theoretisch 15 Instanzen möglich, praktisch empfehlen sich 4–5 Instanzen pro GPU. Die Server-Konfiguration umfasst Context-Size 2048, 4 parallele Slots, Flash-Attention, Seed 42 und deaktiviertes Logging.

---

## Produktionskonfiguration

### Sicherheit

Für den Produktionsbetrieb sollten folgende Maßnahmen ergriffen werden: Datenbankpasswort in `.env` ändern und über Secrets-Management bereitstellen, die Whitelist von `__ALLOW_ALL__` auf spezifische Patterns umstellen, API hinter einen Reverse-Proxy (nginx, Traefik) mit TLS setzen, und den PostgreSQL-Port (5433) nur intern exponieren.

### Whitelist konfigurieren

```sql
-- Allow-All entfernen
DELETE FROM whitelist WHERE pattern = '__ALLOW_ALL__';

-- Spezifische Patterns hinzufügen
INSERT INTO whitelist (pattern, match_type)
VALUES ('Wie funktioniert', 'prefix');

INSERT INTO whitelist (pattern, match_type)
VALUES ('^(Was|Wie|Welche)', 'regex');
```

### Routing erweitern

Neue Routen werden über INSERT in `routing_versions` deployt. Dabei wird die vorherige Version deaktiviert:

```sql
UPDATE routing_versions SET is_active = FALSE WHERE is_active = TRUE;

INSERT INTO routing_versions (version_tag, config_json, is_active, deployed_by)
VALUES ('v1.2-production', '{
  "version": 2,
  "routes": [
    {
      "route_id": 3,
      "name": "BRUCE",
      "endpoint": "http://calc_bruce:8003",
      "bibliothek_id_range": [2000, 2999],
      "priority": 1,
      "confidence_threshold": 0.70,
      "timeout_ms": 1800,
      "max_retries": 1,
      "tags": ["bruce", "router", "pipeline"]
    }
  ]
}'::jsonb, TRUE, 'admin');
```

### Health-Checks

```bash
# API-Gateway
curl http://localhost:9998/api/v1/health

# Calc-Services
curl http://localhost:8003/health
curl http://localhost:8012/health

# Assembler
curl http://localhost:8010/health

# PostgreSQL direkt
PGPASSWORD=secretpassword psql -h localhost -p 5433 -U bruce -d bruce_rag -c "SELECT 1"
```

### Logs

```bash
docker compose logs -f api
docker compose logs -f calc_bruce
docker compose logs -f assembler
docker compose logs -f postgres
```

---

## Skalierung

### Horizontale Skalierung

Calc-Services können repliziert werden, indem zusätzliche Instanzen mit eigenen Ports gestartet und in der Routing-Konfiguration als separate Routen oder Load-Balanced-Endpunkte eingetragen werden.

### Connection Pool Tuning

Der Python-Connection-Pool ist auf 5–50 Verbindungen konfiguriert. Für höhere Last kann `maxconn` in `common/db.py` erhöht oder ein externer Connection-Pooler wie PgBouncer vorgeschaltet werden.

### VRAM-Budget

| Komponente | VRAM |
|-----------|------|
| Granite 350M Q8 Weights | ~370 MB |
| KV-Cache (ctx=2048) | ~100 MB |
| Total pro Instanz | ~470 MB |
| RTX 3080 (10 GB) | max. 15 Instanzen |
| RTX 4060 Ti (8 GB) | max. 12 Instanzen |

---

## Cold-Start-Verhalten

Beim Systemstart durchläuft BRUCE RAG folgende Phasen: Docker-Container starten (PostgreSQL wartet auf Init-Scripts), Python-Services verbinden sich zum DB-Pool, der Assembler startet den LISTEN-Thread, und optionale Warmup-Requests (`POST /warmup`) können an Calc-Services gesendet werden. Der vollständige Cold-Start sollte unter 90 Sekunden liegen.
