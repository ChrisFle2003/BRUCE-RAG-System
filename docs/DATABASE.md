# Datenbank-Referenz

**PostgreSQL-Schema, Indizes, Trigger und Partitionierung des BRUCE RAG Systems**

---

## Übersicht

BRUCE RAG verwendet eine einzelne PostgreSQL-Datenbank (`bruce_rag`) mit drei Extensions: `pgvector` für Vektorähnlichkeitssuche, `pg_trgm` für Trigram-basierte Textsuche und `pgcrypto` für UUID-Generierung. Das Schema ist in zwei SQL-Dateien aufgeteilt: `00_knowledge_db.sql` definiert die Wissensspeicherung, `01_finish_db.sql` die Pipeline-Verarbeitung.

---

## Knowledge-DB-Tabellen (00_knowledge_db.sql)

### bibliotheken

Zentrale Registry der Wissensbereiche. Die `bib_id` ist fest zugeordnet und bestimmt das Routing:

| bib_id | Name | Sprache | Routing-Bereich |
|--------|------|---------|----------------|
| 1 | CODE | multi | 1–999 |
| 1000 | DOCS-DE | de | 1000–1999 |
| 2000 | BRUCE | multi | 2000–2999 |
| 3000 | DOCS-EN | en | 3000–3999 |
| 4000 | MATH | multi | 4000–4999 |

### seiten

Hauptinhaltsspeicher, partitioniert nach `bib_id` für Partition Pruning bei Queries. Jede Seite gehört zu genau einer Bibliothek.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| bib_id | INT | FK → bibliotheken, Teil des PK |
| seite_id | BIGINT (Identity) | Auto-generierte Seiten-ID |
| title | VARCHAR(512) | Dokumenttitel |
| content | TEXT | Volltext des Dokuments |
| full_path | VARCHAR(1024) | Originaler Dateipfad |
| imported_at | TIMESTAMPTZ | Import-Zeitstempel |

Die Tabelle ist per `PARTITION BY RANGE (bib_id)` aufgeteilt in die Partitionen `seiten_p01` (1–999), `seiten_p02` (1000–1999), `seiten_p03` (2000–2999), `seiten_p04` (3000–3999), `seiten_p05` (4000–4999), `seiten_p06` (5000–5999), `seiten_p99` (9000–9999) und `seiten_p_misc` als Default-Partition.

### chunks

Aufgeteilte Textfragmente der Seiten, vorbereitet für Retrieval.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| chunk_id | BIGSERIAL | Primärschlüssel |
| bib_id | INT | Bibliotheks-Zuordnung |
| seite_id | BIGINT | FK → seiten |
| chunk_index | INT | Position innerhalb der Seite |
| text | TEXT | Chunk-Inhalt |
| vektor_id | BIGINT | FK → vektoren (SET NULL bei DELETE) |
| created_at | TIMESTAMPTZ | Erstellungszeitpunkt |

Unique Constraint: `(bib_id, seite_id, chunk_index)`.

### vektoren

Quantisierte Embedding-Vektoren mit 7D-Cube-Koordinaten für hierarchisches Indexing.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| vektor_id | BIGSERIAL | Primärschlüssel |
| bib_id | INT | Bibliotheks-Zuordnung |
| seite_id | BIGINT | FK → seiten (CASCADE) |
| dims | INT2[64] | 64-dim int16-Embedding |
| checksum | INT8 | SHA256-basierter Unique-Hash |
| embedding_model | VARCHAR(64) | Modellname (Standard: all-MiniLM-L6-v2) |
| embedding_dim | SMALLINT | Dimensionalität (Standard: 64) |
| cascade_level | SMALLINT | Granularitätsstufe (0–5) |
| cube_x..cube_t | SMALLINT | 7D State-Vector-Koordinaten |
| indexed_at | TIMESTAMPTZ | Indexierungszeitpunkt |

Der Check-Constraint `chk_dims_len` stellt sicher, dass `dims` exakt 64 Elemente enthält. Wenn die `int2_cosine_ops` OpClass verfügbar ist, wird ein HNSW-Index (`m=16, ef_construction=128`) erstellt.

### whitelist

Query-Zugangskontrolle.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| whitelist_id | BIGSERIAL | Primärschlüssel |
| pattern | TEXT | Muster (UNIQUE) |
| match_type | VARCHAR(10) | `exact`, `prefix` oder `regex` |

### routing_versions

Versionierte Routing-Konfigurationen als JSONB. Nur eine Version kann gleichzeitig aktiv sein (erzwungen durch `idx_routing_one_active` — Partial Unique Index auf `is_active = TRUE`).

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| version_id | BIGSERIAL | Primärschlüssel |
| version_tag | VARCHAR(32) | Versions-Bezeichner (UNIQUE) |
| config_json | JSONB | Routing-Konfiguration |
| is_active | BOOLEAN | Aktiv-Flag |
| deployed_at | TIMESTAMPTZ | Deployment-Zeitpunkt |
| deployed_by | VARCHAR(64) | Deployer |
| checksum | INT8 | Automatisch generierter Hash |

Die `config_json`-Struktur enthält ein `routes`-Array, wobei jede Route folgende Felder hat: `route_id`, `name`, `endpoint`, `bibliothek_id_range` (Array mit [start, end]), `priority`, `confidence_threshold`, `timeout_ms`, `max_retries`, `retry_backoff_ms`, `fail_fast_ms` und `tags`.

---

## Pipeline-Tabellen (01_finish_db.sql)

### pipeline_jobs

Zentrale Job-Tracking-Tabelle für die RAG-Pipeline.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| job_id | UUID | Primärschlüssel (auto-generiert) |
| trace_id | VARCHAR(64) | Tracing-Korrelations-ID |
| query_text | TEXT | Originaler Query-Text |
| state_vec | INT2[7] | 7D-State-Vector |
| expected_routes | INT[] | Route-IDs, die Ergebnisse liefern sollen |
| completed_routes | INT[] | Route-IDs, die bereits geliefert haben |
| status | VARCHAR(20) | pending / ready / assembled / failed / cancelled |
| deadline_at | TIMESTAMPTZ | Timeout (NOW + 5 Sekunden) |
| retry_count | SMALLINT | Anzahl Retries |
| max_retries | SMALLINT | Maximum Retries (Standard: 3) |
| last_error | TEXT | Letzte Fehlermeldung |
| next_retry_at | TIMESTAMPTZ | Nächster Retry-Zeitpunkt |

### calc_results

Inference-Ergebnisse der einzelnen Calc-Services.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| result_id | UUID | Primärschlüssel |
| job_id | UUID | FK → pipeline_jobs (CASCADE) |
| route_id | INT | Route-Identifier |
| route_name | VARCHAR(32) | Route-Name |
| bausteine | JSONB | Array von Bausteinen (Fakten, Code) |
| source_seite_ids | BIGINT[] | Quell-Seiten-IDs |
| duration_ms | INT | Inference-Dauer |
| model_version | VARCHAR(64) | Verwendetes Modell |

Unique Constraint: `(job_id, route_id)` mit UPSERT-Semantik.

Die `bausteine`-JSONB-Struktur enthält ein Array von Objekten mit `type` (fact/code), `content`, `confidence`, `entity_id` und optional `source_seite_id` und `meta`.

### final_answers

Assemblierte Endantworten.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| answer_id | UUID | Primärschlüssel |
| job_id | UUID | FK → pipeline_jobs (UNIQUE, CASCADE) |
| answer_text | TEXT | Assemblierter Antworttext |
| low_confidence_sections | JSONB | Unsichere Abschnitte (< 0.70) |
| sources | JSONB | Quellen-Informationen |
| assembly_quality_score | REAL | Durchschnittliche Konfidenz |
| timing | JSONB | Assembly-Timing-Daten |

### trace_log

Performance-Tracing für alle Pipeline-Phasen.

| Spalte | Typ | Beschreibung |
|--------|-----|-------------|
| log_id | BIGSERIAL | Primärschlüssel |
| trace_id | VARCHAR(64) | Korrelations-ID |
| stage | VARCHAR(32) | Phase (embedding, cascade, routing, inference, assembly) |
| duration_ms | INT | Dauer in Millisekunden |
| gpu_device | VARCHAR(16) | GPU-Bezeichnung (z.B. cuda:1) |
| model | VARCHAR(64) | Modellname |
| logged_at | TIMESTAMPTZ | Zeitstempel |

---

## Indizes

| Index | Tabelle | Spalten / Bedingung | Typ |
|-------|---------|---------------------|-----|
| idx_vektoren_hnsw | vektoren | dims (int2_cosine_ops) | HNSW (m=16, ef=128) |
| idx_vektoren_bib_cascade | vektoren | (bib_id, cascade_level) | B-tree |
| idx_chunks_lookup | chunks | (bib_id, seite_id, chunk_index) | B-tree |
| idx_routing_one_active | routing_versions | is_active WHERE TRUE | Partial Unique |
| idx_pipeline_jobs_status_created | pipeline_jobs | (status, created_at DESC) | B-tree |
| idx_pipeline_jobs_retry | pipeline_jobs | next_retry_at WHERE status='failed' | Partial B-tree |
| idx_pipeline_jobs_query_trgm | pipeline_jobs | query_text | GIN (gin_trgm_ops) |
| idx_calc_results_job_id | calc_results | job_id | B-tree |
| idx_trace_log_trace_time | trace_log | (trace_id, logged_at DESC) | B-tree |

---

## Trigger und Funktionen

### bruce_after_calc_result()

Wird nach jedem INSERT auf `calc_results` ausgelöst. Aktualisiert `pipeline_jobs.completed_routes` durch ARRAY-Merge. Wenn alle `expected_routes` in `completed_routes` enthalten sind (geprüft via `<@`-Operator), setzt der Trigger den Status auf `ready` und sendet `pg_notify('assembly_ready', job_id::text)`.

### notify_routing_updated()

Wird nach INSERT oder UPDATE auf `routing_versions` ausgelöst und sendet eine `routing_updated`-Notification mit version_tag, is_active und deployed_at als JSON.

### notify_whitelist_changed()

Wird nach INSERT, UPDATE oder DELETE auf `whitelist` ausgelöst und sendet eine leere `whitelist_changed`-Notification.

---

## Connection Pooling

Die Python-Services verwenden `psycopg2.pool.ThreadedConnectionPool` mit 5 minimalen und 50 maximalen Verbindungen. Alle Datenbankoperationen laufen über den `get_conn()`-Kontextmanager, der Verbindungen aus dem Pool bezieht und nach Gebrauch zurückgibt. Bei Fehlern wird automatisch ein Rollback durchgeführt.

Der Assembler-Service verwendet eine dedizierte Verbindung im Autocommit-Modus für den LISTEN/NOTIFY-Loop mit `select.select()` für nicht-blockierendes Warten.
