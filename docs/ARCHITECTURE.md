# Architektur

**Systemarchitektur, Pipeline-Flow und Komponentenbeschreibung des BRUCE RAG Systems**

---

## Systemüberblick

BRUCE RAG ist ein Microservice-System mit zwei Sprachebenen: eine C++ Core-Engine für performancekritische Operationen (State-Mapping, Routing, Backpressure) und Python-Services für API, Embedding, Inference und Assembly. Beide Ebenen teilen sich eine gemeinsame PostgreSQL-Datenbank als zentrale Daten- und Kommunikationsschicht.

```
┌──────────────────────────────────────────────────────────┐
│                      Client / curl                       │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP POST /api/v1/queries
                       ▼
┌──────────────────────────────────────────────────────────┐
│                  FastAPI Gateway (:9998)                  │
│                                                          │
│  1. Whitelist-Check ──────────────────┐                  │
│  2. Embedding (sentence-transformers) │                  │
│  3. State-Vector (7D Zone-Mapping)    │                  │
│  4. Route Selection (Intent Scoring)  │                  │
│  5. Chunk Retrieval (pgvector+trgm)   │                  │
│  6. Async Dispatch ──────────┐        │                  │
│                              │        │                  │
└──────────────────────────────┼────────┼──────────────────┘
                               │        │
                    ┌──────────┘        │
                    ▼                   ▼
    ┌───────────────────┐   ┌───────────────────┐
    │  Calc BRUCE (:8003)│   │  Calc DOCS (:8002) │
    │  Granite / Extract │   │  Extract / HF-API  │
    └────────┬──────────┘   └────────┬──────────┘
             │  INSERT calc_results  │
             ▼                       ▼
    ┌──────────────────────────────────────────┐
    │            PostgreSQL + pgvector          │
    │                                          │
    │  pipeline_jobs ──trigger──► NOTIFY        │
    │  calc_results                             │
    │  final_answers                            │
    │  seiten / chunks / vektoren              │
    └──────────────────────┬───────────────────┘
                           │ LISTEN assembly_ready
                           ▼
    ┌──────────────────────────────────────────┐
    │          Assembler Service (:8000)        │
    │  Deduplizierung + Konfidenz-Merge        │
    │  → write_final_answer                    │
    └──────────────────────────────────────────┘
```

---

## Pipeline-Flow im Detail

### Phase 1: Query-Eingang und Validierung

Wenn eine Query bei der API ankommt, wird sie zunächst gegen die `whitelist`-Tabelle geprüft. Die Whitelist unterstützt drei Match-Modi: `exact` für exakte Übereinstimmung, `prefix` für Präfix-Matching und `regex` für reguläre Ausdrücke. Der Spezialeintrag `__ALLOW_ALL__` deaktiviert die Whitelist (Entwicklungsmodus).

### Phase 2: Embedding-Erzeugung

Der `DeterministicEmbedder` erzeugt ein 64-dimensionales int16-Embedding. Dabei wird der Eingabetext durch das sentence-transformers-Modell (all-MiniLM-L6-v2) encodiert, die hochdimensionale Float-Ausgabe in 64 Bins gemittelt, via `tanh` normalisiert und anschließend auf int16 quantisiert (`× 32767`, Clip auf [-32768, 32767]). Ist kein Modell verfügbar, greift ein SHA256-basierter Fallback, der deterministisch Pseudo-Vektoren erzeugt.

### Phase 3: State-Vector-Mapping

Aus den ersten 7 Dimensionen des Embeddings wird ein 7D-State-Vector erzeugt. Jede Dimension wird über `dim_to_zone()` in eine von 27 Zonen abgebildet. Die Formel: Wert wird um 32768 verschoben (auf [0, 65535] normalisiert), durch Zone-Größe (65536 / 27 ≈ 2427) geteilt, und auf [0, 26] begrenzt. Dieser State-Vector dient der Bibliotheks-Zuordnung und dem hierarchischen Routing.

### Phase 4: Route Selection

Die API lädt aktive Routen aus `routing_versions` und scored sie gegen die Query-Tokens:

Der Route-Intent-Score setzt sich zusammen aus einem Basis-Score von 0.05, einem Token-Overlap-Anteil (× 0.6) zwischen Query-Tokens und Route-Name/Tags, einem Domain-Keyword-Bonus (× 0.15) für vordefinierte Intent-Kategorien (code, docs_de, docs_en, math, bruce), und einem Spezialbonus von 0.05 für die BRUCE-Route. Maximal 2 Routen werden selektiert, wobei die zweite Route nur behalten wird, wenn ihr Score ≥ 0.15 beträgt und der Abstand zur Top-Route ≤ 0.25 ist.

### Phase 5: Chunk Retrieval

Für jede selektierte Route werden Context-Chunks in zwei parallelen Pfaden abgerufen. Der Trigram-Pfad verwendet PostgreSQL pg_trgm `similarity()` und ruft bis zu 500 Kandidaten sortiert nach Trigram-Ähnlichkeit ab. Der ANN-Pfad nutzt den pgvector HNSW-Index mit dem `<=>` Cosine-Distance-Operator für die Top-50 nach Vektorähnlichkeit. Die Ergebnisse beider Pfade werden verschmolzen und mit der gewichteten Scoring-Formel (40% Token-Overlap, 20% Anchor-Overlap, 25% Cosine, 15% Trigram) final gerankt.

Bei Multi-Route-Queries sorgt der Domain-Balanced-Merge dafür, dass Chunks aus verschiedenen Routen gleichmäßig verteilt werden (Round-Robin über Routen, sortiert nach Top-Score).

### Phase 6: Inference Dispatch

Für jede Route wird ein Payload mit Query-Text, Chunks, State-Vector und Task-Konfiguration zusammengestellt und asynchron an den zugehörigen Calc-Service dispatcht (eigener Thread, Fire-and-Forget). Der Dispatch nutzt ein Health-Check-basiertes Fail-Fast: vor jedem Aufruf wird `/health` des Endpunkts geprüft (mit 2-Sekunden-Cache). Bei Fehlern greift ein Retry-Mechanismus mit exponentiellem Backoff, begrenzt durch einen Fail-Fast-Timeout.

### Phase 7: Calc Model Inference

Jeder Calc-Service empfängt den Request und führt die Inference mit dem konfigurierten Backend aus. Das System bietet vier Backend-Modi:

**Extractive (Standard):** Extrahiert die relevantesten Snippets aus den Chunks, berechnet Konfidenz aus Similarity und Token-Overlap, und erkennt Code-Blöcke automatisch. Kein LLM erforderlich.

**Granite (llama.cpp):** Verwendet IBM Granite 3.2 350M über llama.cpp mit route-spezifischen System-Prompts. Temperature=0 und Seed=42 garantieren Determinismus. Das Modell darf ausschließlich aus den übergebenen Chunks antworten.

**HF Local:** Nutzt ein lokal geladenes HuggingFace-Modell (Standard: `sshleifer/tiny-gpt2`) für Textgenerierung.

**HF Inference API:** Ruft die HuggingFace Inference API mit einem konfigurierbaren Modell (Standard: `google/flan-t5-base`) auf.

Zusätzlich existiert ein HF-Fallback-Mechanismus: Wenn das primäre Backend (Extractive) niedrige Konfidenz produziert (Durchschnitt < 0.68 oder Top-Fakt < 0.74), wird automatisch die HF-API als Verstärkung hinzugezogen.

Die Inference-Ergebnisse ("Bausteine") werden als JSONB in `calc_results` geschrieben.

### Phase 8: Assembly

Ein PostgreSQL-Trigger auf `calc_results` prüft nach jedem INSERT, ob alle erwarteten Routen Ergebnisse geliefert haben. Sobald vollständig, wird `pg_notify('assembly_ready', job_id)` ausgelöst.

Der Assembler-Service lauscht via `LISTEN assembly_ready` auf Notifications. Bei Empfang lädt er alle `calc_results` für den Job, führt die Assembly durch — Entity-basierte Deduplizierung (höchste Konfidenz gewinnt), Sortierung nach Konfidenz, Trennung in Haupttext (≥ 0.70) und Low-Confidence-Sections (< 0.70), Code-Blöcke immer inkludiert — und schreibt das Ergebnis in `final_answers`. Der Pipeline-Job-Status wird auf `assembled` gesetzt.

---

## C++ Core-Komponenten

### StateToHierarchyMapper

Bildet ein int16-Embedding auf einen 7D-State-Vector ab. Die `dim_to_zone()`-Funktion ist die elementare Mapping-Operation, die in Python und C++ identisch implementiert ist (Testfall `test_dim_to_zone_boundaries` validiert Konsistenz).

### HierarchicalGuard

Implementiert zwei Schutzmechanismen: Whitelist-Prüfung (exakter Muster-Abgleich) und Backpressure-Kontrolle (atomares Slot-Management mit `compare_exchange_weak`). Der Guard begrenzt die Routing-Tiefe auf `max_depth` und die parallelen Jobs auf `max_pending_jobs`.

### RoutingTable

Lädt Routing-Konfiguration aus der `routing_versions`-Tabelle via JSONB-Parsing. Jede Route hat einen Bibliotheks-ID-Bereich, und `resolve()` gibt alle Routen zurück, deren Bereich die gegebene `bibliothek_id` einschließt.

### IPCClient

Dispatcht HTTP-Requests an Calc-Service-Endpunkte. Verwendet Threads mit temporären JSON-Dateien und `curl`-Aufrufen. Implementiert Backpressure über atomaren Job-Counter.

---

## System-Prompts und RAG-Only-Regel

Das Granite-Backend verwendet route-spezifische System-Prompts, die alle eine gemeinsame Kernregel teilen: Das Modell antwortet ausschließlich auf Basis der bereitgestellten Quellen, verwendet kein Weltwissen, und gibt explizit an, wenn die Quellen unzureichend sind. Die verfügbaren Prompt-Varianten sind CODE (Code-Analyse), DOCS_DE (deutsche Dokumentation), DOCS_EN (englische Dokumentation), BRUCE (Bruce-System-Architektur), MATH (mathematische Extraktion) und DEFAULT (allgemeine Wissensextraktion).

---

## Kommunikationsmuster

Die Microservices kommunizieren über zwei Kanäle: HTTP für synchrone Request-Response-Interaktionen (API → Calc) und PostgreSQL LISTEN/NOTIFY für asynchrone Event-Benachrichtigungen (Calc → Assembler). Dieses Muster vermeidet Message-Broker-Abhängigkeiten und nutzt die ohnehin vorhandene Datenbank als Event-Bus.
