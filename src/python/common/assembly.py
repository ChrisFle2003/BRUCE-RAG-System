from __future__ import annotations

from typing import Any

LOW_CONFIDENCE_THRESHOLD = 0.70


def _score(item: dict[str, Any]) -> float:
    return float(item.get("confidence", 0.0))


def _is_code(item: dict[str, Any]) -> bool:
    return str(item.get("type", "")).lower() == "code"


def _deduplicate_conflicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_entity: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []

    for item in items:
        entity_id = item.get("entity_id")
        if not entity_id:
            passthrough.append(item)
            continue

        current = by_entity.get(entity_id)
        if current is None:
            by_entity[entity_id] = item
            continue

        current_score = _score(current)
        new_score = _score(item)
        delta = abs(new_score - current_score)
        if new_score > current_score:
            by_entity[entity_id] = item
            continue

        if delta < 0.05:
            current_src = int(current.get("source_seite_id", -1))
            new_src = int(item.get("source_seite_id", -1))
            if new_src > current_src:
                by_entity[entity_id] = item

    return passthrough + list(by_entity.values())


def assemble(calc_rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_items: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    for row in calc_rows:
        route_name = row.get("route_name", "unknown")
        route_id = int(row.get("route_id", 0))
        source_ids = row.get("source_seite_ids") or []

        bausteine = row.get("bausteine") or []
        if isinstance(bausteine, dict):
            bausteine = bausteine.get("items", [])

        for item in bausteine:
            if not isinstance(item, dict):
                continue
            enriched = dict(item)
            enriched["route_name"] = route_name
            enriched["route_id"] = route_id
            all_items.append(enriched)

        sources.append(
            {
                "route_id": route_id,
                "route_name": route_name,
                "source_seite_ids": source_ids,
            }
        )

    deduped = _deduplicate_conflicts(all_items)
    deduped.sort(key=_score, reverse=True)

    main_sections: list[str] = []
    low_conf_sections: list[dict[str, Any]] = []

    for item in deduped:
        content = str(item.get("content", "")).strip()
        if not content:
            continue

        confidence = _score(item)
        if _is_code(item):
            main_sections.append(content)
            continue

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            low_conf_sections.append(item)
            continue

        main_sections.append(content)

    answer_text = "\n\n".join(main_sections).strip() or "No high-confidence content available."
    quality = 0.0
    if deduped:
        quality = sum(_score(item) for item in deduped) / float(len(deduped))

    return {
        "answer_text": answer_text,
        "low_confidence_sections": low_conf_sections,
        "sources": sources,
        "assembly_quality_score": round(quality, 4),
    }
