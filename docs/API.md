# API-Referenz

**BRUCE RAG REST API v1.1** · Base-URL: `http://localhost:9998`

---

## Übersicht

Die BRUCE RAG API folgt einem asynchronen Submit-and-Poll-Muster: Queries werden über `POST /api/v1/queries` eingereicht und erhalten sofort eine `query_id`. Der Client pollt anschließend `GET /api/v1/queries/{query_id}`, bis der Status `assembled` erreicht ist und das Ergebnis vorliegt.

Zusätzlich bietet die API Health-, Library- und Debug-Endpunkte.

---

## Authentifizierung und Whitelist

Die API verwendet kein Token-basiertes Auth, sondern ein Whitelist-System auf Datenbankebene. Jede eingehende Query wird gegen die `whitelist`-Tabelle geprüft. Im Entwicklungsmodus enthält die Whitelist den Eintrag `__ALLOW_ALL__`, der alle Queries durchlässt. In Produktion können Patterns vom Typ `exact`, `prefix` oder `regex` definiert werden. Wird eine Query nicht zugelassen, antwortet die API mit HTTP 403.

---

## Endpunkte

### POST /api/v1/queries

Sendet eine neue Anfrage in die RAG-Pipeline.

**Request Body:**

```json
{
  "query": "Wie funktioniert der Bruce Router?",
  "language": "de",
  "max_tokens": 512
}
```

| Feld | Typ | Pflicht | Standard | Beschreibung |
|------|-----|---------|----------|-------------|
| `query` | string | ja | — | Fragetext (min. 1 Zeichen) |
| `language` | string | nein | `"de"` | Sprache der Antwort (`de`, `en`) |
| `max_tokens` | integer | nein | `512` | Maximale Antwortlänge in Tokens |

**Response (202 Accepted):**

```json
{
  "query_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "trace_id": "trace_abc123def456",
  "status": "queued"
}
```

**Fehler:**

| Status | Beschreibung |
|--------|-------------|
| 403 | Query ist nicht in der Whitelist |
| 422 | Ungültiger Request Body (leerer Query, falscher Typ) |

**Interner Ablauf:** Die API erzeugt ein Embedding über den Embedding-Service, berechnet den 7D-State-Vector, wählt bis zu 2 Routen via Intent-basiertem Scoring, ruft Context-Chunks aus der Datenbank ab (Trigram + pgvector), und dispatcht die Inference-Requests asynchron an die Calc-Services.

---

### GET /api/v1/queries/{query_id}

Ruft den aktuellen Status und ggf. das Ergebnis einer Query ab.

**Path-Parameter:**

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `query_id` | string (UUID) | ID aus der Submit-Response |

**Response — Pending:**

```json
{
  "query_id": "a1b2c3d4-...",
  "trace_id": "trace_abc123def456",
  "status": "pending",
  "created_at": "2025-01-15T10:30:00Z",
  "completed_at": null
}
```

**Response — Assembled (Ergebnis liegt vor):**

```json
{
  "query_id": "a1b2c3d4-...",
  "trace_id": "trace_abc123def456",
  "status": "assembled",
  "created_at": "2025-01-15T10:30:00Z",
  "completed_at": "2025-01-15T10:30:01Z",
  "result": {
    "text": "Der Bruce Router verwendet eine hierarchische ...",
    "low_confidence_sections": [
      {
        "type": "fact",
        "content": "Unsichere Information...",
        "confidence": 0.55,
        "entity_id": "chunk:42",
        "route_name": "BRUCE"
      }
    ],
    "sources": [
      {
        "route_id": 3,
        "route_name": "BRUCE",
        "source_seite_ids": [101, 102, 103]
      }
    ],
    "quality": 0.847,
    "timing": {
      "assembly_ms": 12
    },
    "created_at": "2025-01-15T10:30:01Z"
  }
}
```

**Statuswerte:**

| Status | Bedeutung |
|--------|----------|
| `pending` | Query ist in Bearbeitung, Calc-Services arbeiten noch |
| `ready` | Alle erwarteten Calc-Results eingetroffen, Assembly steht bevor |
| `assembled` | Final Answer wurde assembliert, Ergebnis verfügbar |
| `failed` | Verarbeitung fehlgeschlagen |
| `cancelled` | Query wurde abgebrochen |

**Polling-Empfehlung:** Adaptive Intervalle verwenden — die ersten 5 Polls alle 10 ms, danach alle 50 ms, nach 20 Polls alle 200 ms. Typische End-to-End-Latenz liegt unter 100 ms bei lokalem Betrieb.

**Fehler:**

| Status | Beschreibung |
|--------|-------------|
| 404 | Query-ID nicht gefunden |

---

### GET /api/v1/health

Gibt den Systemstatus zurück.

**Response:**

```json
{
  "status": "ready",
  "database": true
}
```

Das Feld `status` ist `"ready"` wenn die Datenbankverbindung steht, ansonsten `"degraded"`. Das Feld `database` ist ein Boolean für den Datenbankstatus.

---

### GET /api/v1/libraries

Listet alle registrierten Bibliotheken (Wissensbereiche) der Knowledge-DB.

**Response:**

```json
[
  { "bib_id": 1, "name": "CODE", "language": "multi" },
  { "bib_id": 1000, "name": "DOCS-DE", "language": "de" },
  { "bib_id": 2000, "name": "BRUCE", "language": "multi" },
  { "bib_id": 3000, "name": "DOCS-EN", "language": "en" },
  { "bib_id": 4000, "name": "MATH", "language": "multi" }
]
```

---

### POST /api/v1/debug/retrieval

Debug-Endpunkt, der den Retrieval-Prozess transparent macht, ohne eine Inference auszulösen. Ideal für Entwicklung und Qualitätsanalyse.

**Request Body:**

```json
{
  "query": "Was ist pgvector?",
  "language": "de",
  "limit": 6
}
```

| Feld | Typ | Pflicht | Standard | Beschreibung |
|------|-----|---------|----------|-------------|
| `query` | string | ja | — | Suchtext |
| `language` | string | nein | `"de"` | Sprache |
| `limit` | integer | nein | `6` | Max. Chunks pro Route |

**Response:**

```json
{
  "query": "Was ist pgvector?",
  "routes": [
    {
      "route_id": 3,
      "route_name": "BRUCE",
      "range": [2000, 2999],
      "chunks": [
        {
          "seite_id": 42,
          "content": "pgvector ist eine PostgreSQL-Extension...",
          "similarity": 0.847,
          "full_path": "bib:2000-to-2999/seite:42/chunk:0/level:0"
        }
      ]
    }
  ],
  "merged_chunks": [...]
}
```

---

## Interne Service-APIs

### Calc Model Service

Jeder Calc-Service (BRUCE, DOCS_DE, etc.) exponiert drei Endpunkte:

**GET /health** gibt den Modell-Status zurück:

```json
{
  "status": "ready",
  "model": "granite4-350m-q8@http://localhost:8080",
  "hf_fallback": "hf-api:google/flan-t5-base"
}
```

**POST /warmup** dient dem Cold-Start-Warming und gibt `{"status": "ok"}` zurück.

**POST /calc** nimmt einen Inference-Request entgegen:

```json
{
  "request_id": "uuid",
  "trace_id": "trace_xxx",
  "job_id": "uuid",
  "route_id": 3,
  "route_name": "BRUCE",
  "state_vec": [13, 5, 22, 8, 17, 3, 11],
  "context": {
    "query_text": "Wie funktioniert der Router?",
    "chunks": [...],
    "balanced_chunks": [...],
    "total_chunks": 6
  },
  "task": {
    "type": "extract_facts",
    "language": "de",
    "max_tokens": 512
  }
}
```

Die Response enthält `request_id`, `status`, `route_name` und `duration_ms`. Das Ergebnis (Bausteine) wird direkt in die Datenbank geschrieben.

### Embedding Service

**GET /health** gibt den Modell-Status und das verwendete Backend (`sentence-transformers` oder `hash-fallback`) zurück.

**POST /embed** erzeugt ein int16-Embedding und den State-Vector:

```json
// Request
{ "text": "Beispieltext" }

// Response
{
  "embedding": [1234, -5678, ...],
  "state_vec": [13, 5, 22, 8, 17, 3, 11],
  "model": "sentence-transformers/all-MiniLM-L6-v2"
}
```

### Assembler Service

**GET /health** gibt den Listener-Status zurück. Das Feld `status` ist `"listening"` wenn der PG LISTEN/NOTIFY-Thread aktiv ist, ansonsten `"degraded"`.

**GET /health/listener-check?token=\<token\>** prüft, ob ein bestimmtes NOTIFY-Token empfangen wurde.

---

## Scoring und Ranking

### Chunk-Scoring-Formel

Jeder Chunk wird anhand folgender gewichteter Formel gescored:

```
Score = (0.40 × Token-Overlap) + (0.20 × Anchor-Overlap) + (0.25 × Cosine-Norm) + (0.15 × Trigram)
```

Dabei beschreibt Token-Overlap den weichen Abgleich zwischen Query-Tokens und Chunk-Tokens (Substring-Match für Tokens ≥ 4 Zeichen), Anchor-Overlap den Abgleich mit route-spezifischen Ankertokens, Cosine-Norm die normalisierte Cosine-Similarity aus pgvector, und Trigram den PostgreSQL pg_trgm Similarity-Wert.

Ist der Token-Overlap bei Queries mit ≥ 4 Tokens kleiner als 0.40, wird der Score um Faktor 0.55 reduziert.

### Route-Intent-Scoring

Routen werden anhand von Keyword-Überlappung und Domain-Tags selektiert. Die API wählt maximal 2 Routen aus, wobei die zweite Route nur beibehalten wird, wenn ihr Score ≥ 0.15 beträgt und der Abstand zur Top-Route ≤ 0.25 ist.

### Konfidenz-Schwellwerte

Der Assembly-Prozess verwendet einen Low-Confidence-Threshold von 0.70. Fakten unterhalb dieses Schwellwerts werden in die `low_confidence_sections` ausgelagert statt in den Haupttext aufgenommen. Code-Blöcke werden unabhängig von ihrer Konfidenz immer übernommen.

---

## Fehlerbehandlung

Die API nutzt Standard-HTTP-Statuscodes: 200 für erfolgreiche Abfragen, 403 für Whitelist-Blockierung, 404 für nicht gefundene Queries, und 422 für Validierungsfehler. Bei Calc-Service-Ausfällen greift das interne Retry- und Fail-Fast-System, sodass die API selbst weiterhin erreichbar bleibt und Fallback-Ergebnisse liefert.
