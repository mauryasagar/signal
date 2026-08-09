"""
Orchestrates the full pipeline: niche -> trend signals -> topic ideas -> ranked report.

build_report_context() returns a plain Python dict so the same logic can
power both the Flask route and a CLI (python report.py "coffee brewing").

Zerops Valkey cache integration:
  - Caches the raw signals (Google Trends + YouTube data) by niche for 1 hour.
  - Cache hit: skips both external API calls, drops response time from ~25s to <1s.
  - Cache miss or no cache configured: full live fetch, then store for next request.
"""

import os
import sys
import math
from dotenv import load_dotenv

from fetch_trends import fetch_all_signals, TrendFetchError
from generate_topics import generate_topic_ideas, TopicGenerationError
from cache import get_cached_signals, set_cached_signals

load_dotenv()  # no-op when called from app.py (already loaded), safe as CLI entrypoint


def _compute_demand_score(item):
    """
    Combines trend interest (0-100) and YouTube activity into a single
    0-100 demand score for ranking. Directional estimate only — no free
    source provides exact search volume.

    Weighting: trend interest (60%), video count (25%), avg views log-scaled (15%).
    """
    trend_component = item["trend_interest"] * 0.6
    video_count_component = min(item["video_count"] / 5 * 100, 100) * 0.25

    if item["avg_views"] > 0:
        views_component = min(math.log10(item["avg_views"] + 1) / 7 * 100, 100) * 0.15
    else:
        views_component = 0

    return round(min(trend_component + video_count_component + views_component, 100))


def build_report_context(niche, cache_client=None):
    """
    Main entry point. Returns a dict ready for the report template.

    Keys: niche, topics, top_topic, generated_count, cache_hit
    Each topic: query, title, angle, demand_score, trend_interest,
                video_count, avg_views, sample_titles

    Raises TrendFetchError or TopicGenerationError with human-readable
    messages — the Flask route shows these on the landing page.
    """
    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    groq_api_key    = os.getenv("GROQ_API_KEY")

    if not youtube_api_key:
        raise TrendFetchError(
            "No YouTube API key found. Add YOUTUBE_API_KEY to your environment."
        )

    # ── Try cache first ─────────────────────────────────────────────────────
    cache_hit = False
    cached_payload = get_cached_signals(niche, cache_client)

    if cached_payload is not None and isinstance(cached_payload, dict) and "topics" in cached_payload:
        cache_hit = True
        topics = cached_payload["topics"]
    else:
        # Live fetch — Google Trends + YouTube API
        if isinstance(cached_payload, list):
            signals = cached_payload
        else:
            signals = fetch_all_signals(niche, youtube_api_key)

        # LLM topic generation
        topics = generate_topic_ideas(niche, signals, groq_api_key)
        for topic in topics:
            topic["demand_score"] = _compute_demand_score(topic)

        topics.sort(key=lambda t: t["demand_score"], reverse=True)

        # Store full payload for 1 hour TTL
        set_cached_signals(niche, {"signals": signals, "topics": topics}, cache_client)

    return {
        "niche":           niche,
        "topics":          topics,
        "top_topic":       topics[0] if topics else None,
        "generated_count": len(topics),
        "cache_hit":       cache_hit,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python report.py "<niche>"')
        sys.exit(1)

    niche_arg = " ".join(sys.argv[1:])

    try:
        context = build_report_context(niche_arg)
        print(f"\nTop video topic ideas for: {context['niche']}\n")
        for i, t in enumerate(context["topics"], 1):
            print(f"{i}. [{t['demand_score']}/100] {t['title']}")
            print(f"   From: \"{t['query']}\" | {t['angle']}")
            print()
    except (TrendFetchError, TopicGenerationError) as e:
        print(f"Error: {e}")
        sys.exit(1)
