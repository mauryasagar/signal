"""
Turns raw trend/keyword signals into concrete, ready-to-film video topic
suggestions using Groq (free tier, Llama 3.1 8B Instant).

This is the step that makes the tool useful rather than just a keyword
dump - "cold brew ratio" becomes "I Tested 5 Cold Brew Ratios So You
Don't Have To" with a one-line angle explaining why it'd work.
"""

import json
import re
from groq import Groq


class TopicGenerationError(Exception):
    """Raised when the LLM call fails or returns something unusable."""
    pass


PROMPT_TEMPLATE = """You are a YouTube content strategist helping a creator plan their next video.

Niche: {niche}

Here are trending/related search signals for this niche, with demand indicators:
{signals_text}

For each signal, generate ONE compelling YouTube video title/topic idea that a creator
in this niche could actually make. The title should be specific, clickable, and true to
what the video would contain (no clickbait that overpromises).

Also write a one-sentence "angle" explaining why this topic could work right now,
referencing the demand signal briefly.

Respond ONLY with a valid JSON array, no markdown formatting, no code fences, no preamble.
Format:
[
  {{"source_query": "...", "title": "...", "angle": "..."}}
]

Generate exactly {count} items, one per signal, in the same order as given."""


def _format_signals_for_prompt(signals):
    lines = []
    for s in signals:
        demand_bits = []
        if s["trend_interest"]:
            demand_bits.append(f"trend interest {s['trend_interest']}/100")
        if s["video_count"]:
            demand_bits.append(f"{s['video_count']} recent videos, avg {s['avg_views']:,} views")
        demand_str = ", ".join(demand_bits) if demand_bits else "low signal"
        lines.append(f'- "{s["query"]}" ({demand_str})')
    return "\n".join(lines)


def _extract_json(text):
    """Robust JSON array extraction from LLM text output."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()

    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if match:
        return match.group(0)

    return text


def generate_topic_ideas(niche, signals, api_key, model_name="llama-3.1-8b-instant"):
    """
    Calls Groq (Llama 3.1 8B Instant) to turn raw signals into topic ideas.

    Returns a list of dicts merging the original signal data with the
    generated title/angle:
    [{"query": ..., "title": ..., "angle": ..., "trend_interest": ...,
      "video_count": ..., "avg_views": ..., "sample_titles": [...]}, ...]
    """
    if not api_key:
        raise TopicGenerationError(
            "No Groq API key found. Add GROQ_API_KEY to your .env file. "
            "Get a free key at https://console.groq.com/keys"
        )

    if not signals:
        raise TopicGenerationError("No trend signals available to generate topics from.")

    ideas = []
    try:
        client = Groq(api_key=api_key)

        prompt = PROMPT_TEMPLATE.format(
            niche=niche,
            signals_text=_format_signals_for_prompt(signals),
            count=len(signals)
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        raw_text = _extract_json(response.choices[0].message.content)
        ideas = json.loads(raw_text)

    except json.JSONDecodeError:
        # Fallback if LLM formatting deviates: construct clean topic ideas directly from signals
        ideas = []
        for s in signals:
            q = s["query"].strip()
            ideas.append({
                "title": f"The Ultimate Guide to {q.title()}",
                "angle": f"High demand signal around '{q}' with {s['video_count']} recent videos."
            })
    except Exception as e:
        error_str = str(e).lower()
        if "api key" in error_str or "authentication" in error_str or "401" in error_str:
            raise TopicGenerationError(
                "Groq API key was rejected. Double-check GROQ_API_KEY in your .env file."
            )
        if "quota" in error_str or "429" in error_str or "rate" in error_str:
            raise TopicGenerationError(
                "Groq free tier rate limit hit. Wait a minute and try again."
            )
        raise TopicGenerationError(f"AI topic generation failed: {e}")

    # Merge generated ideas back with original signal data (by order/index,
    # since we asked for same order and same count)
    merged = []
    for i, signal in enumerate(signals):
        idea = ideas[i] if i < len(ideas) else {}
        merged.append({
            "query": signal["query"],
            "title": idea.get("title", signal["query"].title()),
            "angle": idea.get("angle", "Based on current search interest in this topic."),
            "trend_interest": signal["trend_interest"],
            "video_count": signal["video_count"],
            "avg_views": signal["avg_views"],
            "sample_titles": signal["sample_titles"]
        })

    return merged
