"""
Turns raw trend/keyword signals into concrete, ready-to-film video topic
suggestions using Groq (free tier, Qwen 3.6 27B).

This is the step that makes the tool useful rather than just a keyword
dump - "cold brew ratio" becomes "I Tested 5 Cold Brew Ratios So You
Don't Have To" with a one-line angle explaining why it'd work.
"""

import json
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

Make sure to:
1. Use VARIED title formats — not the same structure for every topic (no repeating "The Ultimate Guide to..." for multiple titles)
2. Mix formats like: how-to titles, question titles, list titles ("5 Reasons..."), story/hook titles ("Why I Switched to..."), controversy titles ("The Problem With...")
3. Make each title sound distinct and natural, like a real YouTube creator wrote it
4. Keep titles punchy and under 70 characters where possible

Each title must use a DIFFERENT format from the others. Avoid starting multiple titles with the same word or phrase.

Also write a one-sentence "angle" explaining why this topic could work right now,
referencing the demand signal briefly.

Respond ONLY with a valid JSON object. Do not include markdown formatting, code fences, or extra text.
Format:
{{
  "topics": [
    {{"source_query": "...", "title": "...", "angle": "..."}}
  ]
}}

Generate exactly {count} items in the "topics" array, one per signal, in the same order as given."""


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
    """Strip any <think>...</think> tags Qwen may prepend, then extract JSON object."""
    if not text:
        return ""
    # Remove Qwen thinking blocks entirely
    import re
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Find outermost { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text.strip()


def generate_topic_ideas(niche, signals, api_key, model_name="qwen/qwen3.6-27b"):
    """
    Calls Groq (Qwen 3.6 27B) to turn raw signals into topic ideas.

    Returns a list of dicts merging the original signal data with the
    generated title/angle.
    """
    if not api_key:
        raise TopicGenerationError(
            "No Groq API key found. Add GROQ_API_KEY to your .env file. "
            "Get a free key at https://console.groq.com/keys"
        )

    if not signals:
        raise TopicGenerationError("No trend signals available to generate topics from.")

    try:
        client = Groq(api_key=api_key)

        prompt = PROMPT_TEMPLATE.format(
            niche=niche,
            signals_text=_format_signals_for_prompt(signals),
            count=len(signals),
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            response_format={"type": "json_object"},
        )

        raw_text = _extract_json(response.choices[0].message.content)
        parsed = json.loads(raw_text)
        ideas = parsed.get("topics", [])

    except json.JSONDecodeError as e:
        raise TopicGenerationError(
            "AI returned a malformed response. Please try again."
        ) from e

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

    # Merge generated ideas with original signal data (same order, same count)
    merged = []
    for i, signal in enumerate(signals):
        idea = ideas[i] if i < len(ideas) else {}
        merged.append({
            "query":          signal["query"],
            "title":          idea.get("title", signal["query"].title()),
            "angle":          idea.get("angle", "Based on current search interest in this topic."),
            "trend_interest": signal["trend_interest"],
            "video_count":    signal["video_count"],
            "avg_views":      signal["avg_views"],
            "sample_titles":  signal["sample_titles"],
        })

    return merged