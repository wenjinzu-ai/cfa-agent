from __future__ import annotations

import math
from datetime import datetime, timezone

from src.models.memory import RetrievalResult, MemoryEntry
from src.memory.sqlite_store import SQLiteStore


class MemoryRetriever:
    def __init__(self, store: SQLiteStore):
        self._store = store

    async def keyword_search(self, query: str, limit: int = 20) -> list[dict]:
        return await self._store.search_memories_fts(query, limit)

    async def temporal_search(
        self,
        category: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        return await self._store.search_memories_recent(category, session_id, limit)

    async def tag_search(self, tags: list[str], limit: int = 20) -> list[dict]:
        return await self._store.search_memories_by_tags(tags, limit)

    async def combined_search(
        self,
        query: str,
        tags: list[str] | None = None,
        weight_keyword: float = 0.5,
        weight_temporal: float = 0.3,
        weight_tag: float = 0.2,
        limit: int = 20,
    ) -> list[RetrievalResult]:
        results_map: dict[int, dict] = {}

        keyword_results = await self.keyword_search(query, limit * 3)
        for r in keyword_results:
            rid = r["id"]
            if rid not in results_map:
                results_map[rid] = {"entry": r, "scores": {}}
            results_map[rid]["scores"]["keyword"] = self._normalize_fts_rank(r.get("rank", 999))

        temporal_results = await self.temporal_search(limit=limit * 3)
        for r in temporal_results:
            rid = r["id"]
            if rid not in results_map:
                results_map[rid] = {"entry": r, "scores": {}}
            hours_ago = self._hours_since(r["created_at"])
            results_map[rid]["scores"]["temporal"] = self._temporal_decay(hours_ago)

        if tags:
            tag_results = await self.tag_search(tags, limit=limit * 3)
            for r in tag_results:
                rid = r["id"]
                if rid not in results_map:
                    results_map[rid] = {"entry": r, "scores": {}}
                matched_tags_str = r.get("matched_tags", "")
                matched_tags_list = matched_tags_str.split(",") if matched_tags_str else []
                results_map[rid]["scores"]["tag"] = len(
                    [t for t in tags if t in matched_tags_list]
                )

        all_ids = list(results_map.keys())
        tags_by_id = await self._batch_load_tags(all_ids)

        scored = []
        for rid, data in results_map.items():
            s = data["scores"]
            kw_score = s.get("keyword", 0.0)
            tmp_score = s.get("temporal", 0.0)
            tg_score = s.get("tag", 0.0) / max(len(tags), 1) if tags else 0.0

            total_weight = weight_keyword + weight_temporal + weight_tag
            final_score = (
                kw_score * weight_keyword
                + tmp_score * weight_temporal
                + tg_score * weight_tag
            ) / total_weight

            entry_tags = tags_by_id.get(rid, [])
            matched_by = [k for k, v in s.items() if v > 0]

            scored.append(
                RetrievalResult(
                    entry=MemoryEntry.from_db_row(data["entry"], tags=entry_tags),
                    score=round(final_score, 4),
                    matched_by=matched_by,
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]

    async def _batch_load_tags(self, memory_ids: list[int]) -> dict[int, list[str]]:
        if not memory_ids:
            return {}
        result: dict[int, list[str]] = {mid: [] for mid in memory_ids}
        placeholders = ", ".join(["?"] * len(memory_ids))
        rows = await self._store.execute_sql(
            f"SELECT memory_id, tag FROM memory_tags WHERE memory_id IN ({placeholders})",
            tuple(memory_ids),
        )
        for row in rows:
            result[row["memory_id"]].append(row["tag"])
        return result

    @staticmethod
    def _normalize_fts_rank(rank: float) -> float:
        return 1.0 / (1.0 + abs(rank))

    @staticmethod
    def _temporal_decay(hours_ago: float, lambda_decay: float = 0.01) -> float:
        return math.exp(-lambda_decay * hours_ago)

    @staticmethod
    def _hours_since(iso_timestamp: str) -> float:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600