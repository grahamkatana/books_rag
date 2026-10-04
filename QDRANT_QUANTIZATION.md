# Qdrant search performance — scalar quantization

Why the book/paper vectors are int8-quantized, and how to re-apply it if the
search latency ever regresses.

## The problem

Search latency was 20–30 s per query, which surfaced in the UI as
"something went wrong" / streamed answers that never persisted.

## Root cause

`on_disk=False` on a Qdrant vector config does **not** force the vectors into
RAM — it mmaps them. The Qdrant pod is memory-capped (2 Gi) on a node already
~78% full, and the corpus's float vectors are ~800 MB (book 688 MB + paper
114 MB), so the OS evicted those pages and every search re-read them from slow
disk. Qdrant's RSS stayed around a few hundred MiB the whole time, so moving
vectors "off disk" (the re-home) did not actually make them resident.

## The fix: int8 scalar quantization

Shrinks each vector 4× (book 688 MB → 172 MB), which genuinely fits in RAM.
Applied **in place** — Qdrant re-quantizes existing points in the background,
so there is no re-embedding and no collection swap:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
)

client = QdrantClient(url=..., api_key=...)  # read from env / the k8s secret, never hardcode
client.update_collection(
    "book_library",
    quantization_config=ScalarQuantization(
        scalar=ScalarQuantizationConfig(type=ScalarType.INT8, always_ram=True)
    ),
)
```

Run the same call for `paper_library`. `always_ram=True` is the part that pins
the quantized vectors in RAM.

## Result

| Collection | Before | After |
|---|---|---|
| book_library | ~30,000 ms | ~50–90 ms |
| paper_library | ~12,000 ms | ~25 ms |

## Gotchas

- The quantization config is read from the collection's **top-level**
  `config.quantization_config`. `config.params.vectors.quantization_config` is
  `None` in qdrant-client 1.19.1 — don't read that field to check whether
  quantization is on, it will mislead you into thinking it didn't apply.
- `rescore` is a **query-time** parameter (`QuantizationSearchParams`), not a
  config field. Int8 recall is >99% for RAG, so we skip it. Add
  `search_params=QuantizationSearchParams(rescore=True)` to `query_points` if
  exact recall ever matters.
- The first query after re-quantization is cold (the index warms into RAM on
  demand); run a few queries before judging the new latency.
- Do **not** "clean up" payloads by re-upserting every point in place — that
  churns the HNSW index and causes search timeouts. The NUL-byte issue is
  handled at the persistence boundary in `save_turn` instead, not by rewriting
  the corpus.
