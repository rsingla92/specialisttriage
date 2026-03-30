"""LLM-assisted referral classification using Claude Haiku.

Called as a fallback when keyword-based classification returns "other".
Cost: ~$0.01 per call. Only invoked for ~10-20% of referrals.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMClassification:
    category: str
    confidence: float
    reasoning: str
    model: str = "claude-haiku-4-5-20251001"


def is_llm_enabled() -> bool:
    """Check if LLM classification is configured."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def classify_with_llm(
    referral_text: str,
    categories: list[dict],
    specialty_name: str = "Urology",
) -> LLMClassification | None:
    """Classify a referral using Claude Haiku when keyword matching fails.

    Args:
        referral_text: Combined text from chief_complaint, clinical_notes, investigations.
        categories: List of dicts with "slug" and "display_name" keys.
        specialty_name: The specialty for context.

    Returns:
        LLMClassification with category, confidence (0-1), and reasoning.
        Returns None on error or if LLM is not configured.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    category_list = "\n".join(
        f"- {cat['slug']}: {cat['display_name']}"
        for cat in categories
    )

    prompt = f"""You are a medical referral classifier for a {specialty_name} clinic.

Given the following referral text, classify it into one of these categories:
{category_list}
- other: Does not match any category above

Referral text:
{referral_text}

Respond with ONLY valid JSON (no markdown, no explanation outside JSON):
{{"category": "slug", "confidence": 0.0, "reasoning": "one sentence"}}

Rules:
- confidence is 0.0 to 1.0 (1.0 = certain, 0.5 = uncertain)
- If the referral clearly doesn't match any category, use "other" with high confidence
- Use the exact slug from the category list above"""

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Parse JSON response
        result = json.loads(text)

        valid_slugs = {cat["slug"] for cat in categories} | {"other"}
        category = result.get("category", "other")
        if category not in valid_slugs:
            category = "other"

        return LLMClassification(
            category=category,
            confidence=min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
            reasoning=result.get("reasoning", ""),
            model="claude-haiku-4-5-20251001",
        )

    except json.JSONDecodeError as e:
        logger.warning("LLM classifier returned invalid JSON: %s", e)
        return None
    except Exception as e:
        logger.error("LLM classifier error: %s", e)
        return None
