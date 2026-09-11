from __future__ import annotations


def chunk_for_batch(items: list[dict], chunk_size: int) -> list[list[dict]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)] or [[]]
