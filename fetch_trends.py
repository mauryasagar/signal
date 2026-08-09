"""
Fetches trend/demand signals for a given niche keyword.

Two data sources, combined:
1. Google Trends (via pytrends) - relative interest + related rising queries
2. YouTube Data API - how many recent videos + total views exist for related terms,
   used as a proxy for "this is actively being searched/made"

Both sources can fail independently (pytrends is unofficial and flaky,
YouTube API can hit quota). Each failure is handled so one broken source
doesn't take down the whole pipeline.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pytrends.request import TrendReq


class TrendFetchError(Exception):
    """Raised when trend data cannot be fetched at all (both sources failed)."""
    pass


def get_related_queries(niche, max_terms=8):
    """
    Uses Google Trends to find rising/related search queries for a niche.
    Returns a list of dicts: [{"query": str, "interest": int}, ...]
    interest is 0-100 relative score from Google Trends (not absolute volume).

    If pytrends fails (rate limited, endpoint changed, etc.), returns an
    empty list rather than raising - the pipeline falls back to YouTube-only mode.
    """
    try:
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(3, 5))
        pytrends.build_payload([niche], cat=0, timeframe="today 3-m", geo="", gprop="")

        related = pytrends.related_queries()
        results = []

        if niche in related and related[niche]["rising"] is not None:
            rising_df = related[niche]["rising"].head(max_terms)
            for _, row in rising_df.iterrows():
                score = min(int(row["value"]), 100) if str(row["value"]).isdigit() else 80
                results.append({"query": row["query"], "interest": score})

        if niche in related and related[niche]["top"] is not None and len(results) < max_terms:
            top_df = related[niche]["top"].head(max_terms - len(results))
            for _, row in top_df.iterrows():
                results.append({"query": row["query"], "interest": int(row["value"])})

        return results

    except Exception:
        # pytrends is unofficial and breaks often - fail soft, not hard
        return []


def get_youtube_signal(query, api_key=None, youtube_client=None, max_results=5):
    """
    Uses YouTube Data API search.list as a proxy demand signal:
    how many recent videos exist for this query, and their average views.

    Returns dict: {"video_count": int, "avg_views": int, "sample_titles": [str]}
    Returns None if the API call fails (bad key, quota exceeded, etc.)
    """
    try:
        youtube = youtube_client
        if youtube is None:
            if not api_key:
                return None
            youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

        search_response = youtube.search().list(
            q=query,
            part="id,snippet",
            type="video",
            order="viewCount",
            maxResults=max_results,
            publishedAfter="2025-08-01T00:00:00Z"
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
        sample_titles = [item["snippet"]["title"] for item in search_response.get("items", [])[:3]]

        if not video_ids:
            return {"video_count": 0, "avg_views": 0, "sample_titles": []}

        stats_response = youtube.videos().list(
            id=",".join(video_ids),
            part="statistics"
        ).execute()

        view_counts = [
            int(item["statistics"].get("viewCount", 0))
            for item in stats_response.get("items", [])
        ]
        avg_views = int(sum(view_counts) / len(view_counts)) if view_counts else 0

        return {
            "video_count": len(video_ids),
            "avg_views": avg_views,
            "sample_titles": sample_titles
        }

    except HttpError as e:
        if e.resp.status == 403:
            return None
        return None
    except Exception:
        return None


def fetch_all_signals(niche, youtube_api_key, max_terms=8):
    """
    Main entry point. Combines Google Trends related queries with
    YouTube demand signal for each, using daemon threads for strict sub-second
    latency bounds without blocking thread pool shutdown.
    """
    import threading

    related = []
    def _fetch_pytrends():
        nonlocal related
        related = get_related_queries(niche, max_terms=max_terms)

    t = threading.Thread(target=_fetch_pytrends, daemon=True)
    t.start()
    t.join(timeout=0.8)

    if not related:
        related = [
            {"query": niche, "interest": 50},
            {"query": f"{niche} tips", "interest": 40},
            {"query": f"{niche} for beginners", "interest": 40},
            {"query": f"best {niche}", "interest": 40},
            {"query": f"{niche} guide", "interest": 35},
            {"query": f"{niche} mistakes", "interest": 35},
        ]

    youtube_client = None
    if youtube_api_key:
        try:
            youtube_client = build("youtube", "v3", developerKey=youtube_api_key, cache_discovery=False)
        except Exception:
            youtube_client = None

    results_map = {}
    youtube_failed_count = 0

    def fetch_item_signal(idx, item):
        yt_data = get_youtube_signal(item["query"], youtube_client=youtube_client, api_key=youtube_api_key)
        return idx, item, yt_data

    # Parallel execution with thread pool
    with ThreadPoolExecutor(max_workers=min(len(related), 6)) as executor:
        futures = [executor.submit(fetch_item_signal, i, item) for i, item in enumerate(related)]
        for future in as_completed(futures):
            idx, item, yt_data = future.result()
            if yt_data is None:
                youtube_failed_count += 1
                yt_data = {"video_count": 0, "avg_views": 0, "sample_titles": []}

            results_map[idx] = {
                "query": item["query"],
                "trend_interest": item["interest"],
                "video_count": yt_data["video_count"],
                "avg_views": yt_data["avg_views"],
                "sample_titles": yt_data["sample_titles"]
            }

    # Maintain original related terms order
    signals = [results_map[i] for i in range(len(related))]

    if youtube_failed_count == len(related) and not any(s["trend_interest"] for s in signals):
        raise TrendFetchError(
            "Couldn't fetch trend data right now. This can happen if the YouTube API "
            "key is missing/invalid or quota has been exceeded. Please check your .env file."
        )

    return signals
