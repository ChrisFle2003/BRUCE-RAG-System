# CLI & Build-Referenz

**Kommandozeilen-Tools, Make-Targets und Scripts des BRUCE RAG Systems**

---

## Make-Targets

Das Makefile im Projekt-Root bietet alle gängigen Operationen als Targets an.

### Setup und Build

**`make setup`** erstellt eine Python-Virtual-Environment (`.venv`) und installiert alle Abhängigkeiten aus `src/python/requirements.txt`, einschließlich PyTorch, sentence-transformers und FastAPI.

**`make build-cpp`** baut die C++ Core-Engine mit CMake. Erzeugt das Binary `build/src/cpp/bruce_core`. Erfordert einen C++17-Compiler und libpq (PostgreSQL Client Library).

**`make build-python`** validiert den Python-Import-Graph durch `compileall`. Stellt sicher, dass alle Module fehlerfrei kompilierbar sind.

**`make build-all`** führt sowohl `build-cpp` als auch `build-python` aus.

**`make clean`** entfernt Build-Artefakte (`build/`, `logs/`, `.pytest_cache/`, `__pycache__/`).

### Docker-Operationen

**`make up`** startet alle Services via `docker compose up -d`. Dies umfasst PostgreSQL mit pgvector, den API-Gateway, Calc-Services (BRUCE und DOCS_DE), sowie den Assembler.

**`make down`** stoppt alle Docker-Services.

**`make run-all`** ist ein Alias für `make up`.

### Datenbank

**`make db-init`** wendet die SQL-Schemas `00_knowledge_db.sql` und `01_finish_db.sql` auf die PostgreSQL-Instanz an. Verwendet die Umgebungsvariablen `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` und `DB_NAME` (Standardwerte aus `.env`).

### Daten-Import

**`make import-docs`** importiert Markdown- und Textdateien aus dem `docs/`-Verzeichnis in die Knowledge-DB. Der Ziel-Bibliotheks-ID kann über `BIB_ID` angegeben werden:

```bash
make import-docs BIB_ID=2000   # Standard: BRUCE-Bibliothek
make import-docs BIB_ID=1000   # Deutsche Dokumentation
make import-docs BIB_ID=3000   # Englische Dokumentation
```

Der Import-Prozess läuft innerhalb des API-Docker-Containers: Das Script `scripts/import_docs.py` wird hineinkopiert und ausgeführt.

### Tests und Benchmarks

**`make test`** führt die Unit-Tests aus. Versucht zunächst pytest, fällt auf `unittest discover` zurück falls pytest nicht installiert ist.

**`make benchmark`** startet den C++ Benchmark-Modus, der 500.000 `dim_to_zone`-Operationen ausführt und die Dauer misst.

**`make eval-retrieval`** startet die Retrieval-Qualitäts-Evaluation, die MRR und Recall@K über vordefinierte Testfälle berechnet.

**`make benchmark-backends`** vergleicht die Calc-Backend-Modi `extractive` und `hf_api` über 30 Queries hinweg und misst Latenz, Throughput und Assembly-Qualität.

---

## C++ Core Binary

Das Binary `build/src/cpp/bruce_core` kann eigenständig ausgeführt werden.

### Verwendung

```bash
# Query verarbeiten
./build/src/cpp/bruce_core "Wie funktioniert der Router?"

# Benchmark-Modus
./build/src/cpp/bruce_core --benchmark
```

### Query-Modus

Im Query-Modus lädt das Binary die Whitelist aus der Datenbank, prüft die Query, erzeugt ein Stub-Embedding (Hash-basiert), berechnet den State-Vector, lädt die Routing-Tabelle aus der DB, und dispatcht den Request via HTTP (curl) an die passenden Calc-Service-Endpunkte.

Die Ausgabe zeigt die Route-Informationen:

```
Dispatched query to 1 route(s). state=[13,5,22,8,17,3,11] bib_id=2481
```

Mögliche Exit-Codes: 0 für Erfolg, 2 wenn die Query von der Whitelist blockiert wird, 3 bei Backpressure (zu viele laufende Jobs).

### Benchmark-Modus

Führt 500.000 `dim_to_zone`-Aufrufe aus und gibt die Gesamtdauer in Millisekunden aus. Dient der Validierung der C++ State-Mapping-Performance.

---

## Scripts

### scripts/import_docs.py

Importiert Markdown- und Textdateien in die Knowledge-DB.

```bash
python3 scripts/import_docs.py <path> [--bib-id <id>]
```

| Argument | Beschreibung |
|----------|-------------|
| `path` | Datei oder Verzeichnis zum Import |
| `--bib-id` | Ziel-Bibliotheks-ID (Standard: 2000) |

Das Script durchsucht rekursiv nach `.md`- und `.txt`-Dateien, teilt den Inhalt in Chunks (800 Zeichen mit 35 Wörtern Overlap), erzeugt Embeddings via sentence-transformers, berechnet Checksummen, und fügt alles in die Tabellen `seiten`, `vektoren` und `chunks` ein.

### scripts/eval_retrieval.py

Evaluiert die Retrieval-Qualität über den Debug-Endpunkt der API.

```bash
python3 scripts/eval_retrieval.py [--api-base <url>] [--limit <n>]
```

| Argument | Standard | Beschreibung |
|----------|----------|-------------|
| `--api-base` | `http://localhost:9998` | API-Basis-URL |
| `--limit` | `6` | Chunks pro Route |

Berechnet MRR (Mean Reciprocal Rank), Recall@1, Recall@3 und Recall@5 über 6 vordefinierte Testfälle, darunter Fragen zu Router, Startup-Sequence, pgvector, Assembler-Konfidenz und Performance-Targets.

### scripts/benchmark_backends.py

Vergleicht die Calc-Backend-Modi in einem End-to-End-Benchmark über 30 Queries.

```bash
python3 scripts/benchmark_backends.py [--api-base <url>] [--project-root <path>] [--hf-model <name>]
```

Das Script startet zunächst die Services im `extractive`-Modus, misst Latenz und Qualität, wechselt dann auf `hf_api` (sofern `HF_API_TOKEN` gesetzt), und stellt abschließend den Default-Backend wieder her. Die Ergebnisse umfassen Average/P95-Latenz, Durchschnittliche Qualität und Anzahl erfolgreicher Cases.

### scripts/real_stress_benchmark.py

Umfassende Stress-Test-Suite mit 5 Testphasen.

```bash
python3 scripts/real_stress_benchmark.py
```

Die Suite durchläuft: (1) Progressive Load Tests mit 1-10 parallelen Workern, (2) komplexe Long-Query-Tests, (3) Edge-Cases wie leere Queries, SQL-Injection und XSS-Versuche, (4) einen 90-sekündigen Dauerlasttest, und (5) einen Peak-Load-Test mit 20 parallelen Workern und 100 Queries. Ergebnisse werden als Markdown-Report in `BENCHMARK.md` gespeichert.

### scripts/run_calc_server.sh

Startet einen llama.cpp-Server für Granite-Inferenz.

```bash
./scripts/run_calc_server.sh <PORT> <GPU_DEVICE> <MODEL_PATH>
```

| Argument | Standard | Beschreibung |
|----------|----------|-------------|
| PORT | 8001 | Server-Port |
| GPU_DEVICE | 0 | CUDA Device ID |
| MODEL_PATH | `/models/granite4-350m-h-q8_0.gguf` | GGUF-Modelldatei |

Konfiguriert den Server mit Kontext-Größe 2048, 4 parallelen Slots, Flash-Attention und festem Seed 42 für Determinismus. Der Granite 350M Q8 benötigt ca. 470 MB VRAM pro Instanz.

### scripts/build_llama_cuda.sh

Klont oder aktualisiert llama.cpp und baut es mit CUDA-Support via Ninja. Konfiguriert GPU-Architekturen sm_86 (RTX 3080, Ampere) und sm_89 (RTX 4060 Ti, Ada Lovelace).

```bash
./scripts/build_llama_cuda.sh
```

Erfordert nvcc (CUDA ≥ 12.1), ninja-build und cmake. Das Ergebnis liegt in `~/llama.cpp/build/bin/llama-server`.

### scripts/setup_database.sh

Minimaler Shell-Wrapper, der die SQL-Schemas auf PostgreSQL anwendet.

### scripts/install_dependencies.sh

Installiert PostgreSQL, pgvector und zugehörige Systemabhängigkeiten via apt.

---

## Umgebungsvariablen für Scripts

Alle Scripts verwenden die gemeinsamen Datenbankeinstellungen aus `common.settings`:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=bruce_rag
export DB_USER=bruce
export DB_PASSWORD=secretpassword
```

Die `.env`-Datei wird von `benchmark_backends.py` automatisch gelesen. Für andere Scripts muss PYTHONPATH auf `src/python` gesetzt sein:

```bash
PYTHONPATH=src/python python3 scripts/import_docs.py docs/ --bib-id 2000
```
