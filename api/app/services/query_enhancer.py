from re import split, sub

from api.app.schemas.retrieval import EnhancementInfo, RetrievalEnhancements


def enhance_query(query: str, enhancements: RetrievalEnhancements) -> EnhancementInfo:
    """Generate deterministic query enhancements without coupling to generation frameworks."""

    rewritten_query = rewrite_query(query) if enhancements.query_rewrite else None
    sub_queries = (
        decompose_query(rewritten_query or query, enhancements.max_sub_queries)
        if enhancements.decompose
        else []
    )
    hyde_doc = generate_hyde_doc(rewritten_query or query) if enhancements.hyde else None
    return EnhancementInfo(
        rewritten_query=rewritten_query,
        sub_queries=sub_queries,
        hyde_doc=hyde_doc,
    )


def rewrite_query(query: str) -> str:
    """Normalize a user query into a retrieval-friendly phrase."""

    normalized = sub(r"\s+", " ", query).strip()
    normalized = normalized.rstrip("?？。.!！")
    return normalized


def decompose_query(query: str, max_sub_queries: int) -> list[str]:
    """Split a complex query into smaller retrieval queries."""

    parts = [
        part.strip()
        for part in split(r"\s*(?:\band\b|,|，|;|；|\?|？)\s*", query)
        if part.strip()
    ]
    if len(parts) <= 1:
        return [query]
    return parts[:max_sub_queries]


def generate_hyde_doc(query: str) -> str:
    """Create a hypothetical document used only as an additional retrieval query."""

    return (
        "This hypothetical reference document answers the query: "
        f"{query}. It contains the key terms, entities, and context needed for retrieval."
    )
