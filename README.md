# BRUCE RAG System

**Deterministisches Retrieval-Augmented-Generation System mit Multi-Route-Architektur**

Version 1.1 · RFC-001 konform · Autoren: Chris + Claude

---

## Überblick

BRUCE RAG ist ein hybrides RAG-System, das eine C++-Core-Engine mit Python-Microservices kombiniert, um deterministische, nachvollziehbare Antworten aus einer PostgreSQL-Wissensdatenbank zu generieren. Das System vermeidet bewusst Halluzinationen, indem jede Antwort ausschließlich auf den gespeicherten Dokumenten basiert und über ein mehrstufiges Konfidenz-Scoring verifiziert wird.

### Kernprinzipien

Das System folgt drei fundamentalen Designregeln: erstens vollständiger Determinismus — gleiche Eingabe erzeugt immer gleiche Ausgabe (Temperature=0, Seed=42). Zweitens ausschließlich quellenbasierte Antworten — das LLM darf kein Weltwissen einbringen. Drittens vollständige Nachvollziehbarkeit — jede Pipeline-Phase wird in `trace_log` protokolliert.

### Architektur auf einen Blick

```
Client → FastAPI (Port 9998)
           ├── Embedding Service (sentence-transformers/all-MiniLM-L6-v2)
           ├── PostgreSQL + pgvector (Wissensdatenbank)
           ├── Routing Engine (Intent-basiert, Multi-Route)
           ├── Calc Model Services (Granite 350M / Extractive / HF-API)
           └── Assembler Service (LISTEN/NOTIFY, Konfidenz-Merge)
                 → Final Answer
```

Die Verarbeitung einer Query durchläuft folgende Stationen: Embedding-Erzeugung, State-Vector-Mapping, Routing-Auswahl, Chunk-Retrieval via pgvector + Trigram, parallele Inference an Calc-Model-Services, und abschließend Assembly mit Deduplizierung und Konfidenzfilterung.

---

## Schnellstart

### Voraussetzungen

Das System benötigt PostgreSQL 15+ mit pgvector und pg_trgm Extensions, Python 3.11+, einen C++17-Compiler, Docker und docker-compose, sowie optional CUDA 12.1+ und GPUs (RTX 3080 / RTX 4060 Ti) für den Granite-Backend-Betrieb.

### Installation und Start

```bash
# 1. Repository entpacken
unzip BRUCE_RAG_PROJECT.zip && cd BRUCE_RAG_PROJECT

# 2. Python-Umgebung einrichten
make setup

# 3. C++ Core bauen
make build-cpp

# 4. Services starten (Docker)
make up

# 5. Datenbank initialisieren (wird beim ersten Docker-Start automatisch erledigt)
make db-init

# 6. Dokumente importieren
make import-docs BIB_ID=2000
```

### Ersten Query senden

```bash
# Health-Check
curl http://localhost:9998/api/v1/health

# Query absenden
curl -X POST http://localhost:9998/api/v1/queries \
  -H "Content-Type: application/json" \
  -d '{"query": "Wie funktioniert der Bruce Router?", "language": "de"}'

# Ergebnis abfragen (query_id aus Response)
curl http://localhost:9998/api/v1/queries/<query_id>
```

---

## Projektstruktur

```
BRUCE_RAG_PROJECT/
├── src/
│   ├── cpp/                    # C++ Core Engine
│   │   ├── bruce_core.cpp      # Hauptprogramm mit DB-Anbindung
│   │   ├── state_to_hierarchy  # Embedding → 7D-StateVec Mapping
│   │   ├── hierarchical_guard  # Whitelist + Backpressure Guard
│   │   ├── routing_table       # DB-basierte Routing-Auflösung
│   │   └── ipc_client          # HTTP-Dispatch an Calc-Services
│   ├── python/
│   │   ├── api/main.py         # FastAPI REST-Endpunkte
│   │   ├── embedding/service   # Embedding-Erzeugung + Quantisierung
│   │   ├── calc_models/        # Inferenz-Backends (Granite, HF, Extractive)
│   │   ├── assembler/service   # PG LISTEN/NOTIFY Assembler
│   │   └── common/             # Settings, DB-Pool, Assembly-Logik
│   └── cli/                    # CLI-Einstiegspunkt
├── schema/
│   ├── 00_knowledge_db.sql     # Wissensdatenbank (Seiten, Chunks, Vektoren)
│   └── 01_finish_db.sql        # Pipeline-Tabellen (Jobs, Results, Answers)
├── config/bruce.yaml           # YAML-Konfiguration
├── scripts/                    # Import, Benchmark, Evaluation, Build
├── tests/                      # Unit-Tests
├── docker-compose.yml          # Multi-Service Orchestrierung
├── Makefile                    # Build-Automatisierung
└── CMakeLists.txt              # C++ Build-Konfiguration
```

---

## Konfiguration

Alle Einstellungen werden über Umgebungsvariablen gesteuert. Die `.env`-Datei enthält die Standardwerte:

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL Host |
| `DB_PORT` | `5432` | PostgreSQL Port |
| `DB_NAME` | `bruce_rag` | Datenbankname |
| `DB_USER` | `bruce` | Datenbankbenutzer |
| `DB_PASSWORD` | `secretpassword` | Datenbankpasswort |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding-Modell |
| `CALC_BACKEND` | `granite` | Backend-Modus: `granite`, `extractive`, `hf`, `hf_api` |
| `LLAMA_ENDPOINT` | `http://localhost:8080` | llama.cpp Server URL |
| `HF_API_TOKEN` | — | HuggingFace API Token |
| `HF_API_MODEL` | `google/flan-t5-base` | HF Inference API Modell |
| `MAX_PENDING_JOBS` | `50` | Backpressure-Limit |
| `HF_FALLBACK_ENABLED` | `1` | HF-Fallback bei niedriger Konfidenz |
| `HF_FALLBACK_MIN_CONF` | `0.68` | Schwellwert für HF-Fallback |

---

## Services und Ports

| Service | Port | Beschreibung |
|---------|------|-------------|
| API Gateway | 9998 | FastAPI REST-API, Haupteingang |
| Calc BRUCE | 8003 | Granite/Extractive Calc-Service (Route BRUCE) |
| Calc DOCS_DE | 8002 (→8012) | Calc-Service für deutsche Dokumentation |
| Assembler | 8000 (→8010) | Assembly via PG LISTEN/NOTIFY |
| PostgreSQL | 5432 (→5433) | Wissensdatenbank mit pgvector |
| Embedding | 8100 | Optionaler standalone Embedding-Service |

---

## Weiterführende Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [API.md](./API.md) | Vollständige REST-API-Referenz |
| [CLI.md](./CLI.md) | CLI- und Make-Target-Dokumentation |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Architektur, Pipeline-Flow, Datenmodell |
| [DATABASE.md](./DATABASE.md) | Schema-Referenz, Indizes, Trigger |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Docker-Setup, GPU-Konfiguration, Produktion |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Entwicklung, Tests, Benchmarks, Troubleshooting |

---

## Performance-Ziele

| Metrik | Zielwert |
|--------|----------|
| End-to-End Latenz | < 100 ms |
| Determinismus | 100 % |
| VRAM pro GPU | < 6 GB |
| Uptime | 24/7 |
| Cold-Start | < 90 s |

---

## Lizenz und Autoren

Projekt von Chris + Claude. RFC-001 v1.1 konform. Status: Ready for Implementation.
