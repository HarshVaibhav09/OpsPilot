import re

import edge_tts

from app.core.config import settings
from app.core.llm_client import llm_client
from app.core.prompts import VOICE_SUMMARY_PROMPT

# Citations read terribly out loud -- "(Source: incident_log.pdf, page 12)"
# becomes a mouthful of punctuation and file extensions. They stay in the
# text answer on screen; the spoken version drops them.
CITATION_PATTERN = re.compile(
    r"\(\s*Source:.*?\)",
    flags=re.IGNORECASE | re.DOTALL,
)

# Markdown bullets and list markers at the start of a line. Replaced with
# a sentence break so the voice pauses between items instead of running
# them together.
BULLET_PATTERN = re.compile(
    r"^\s*(?:[-*•]|\d+\.)\s+",
    flags=re.MULTILINE,
)

MARKDOWN_PATTERN = re.compile(r"[*_#`>]+")

# Filenames survive citation stripping when the LLM mentions them inline.
# "incident_log.pdf" is read letter-by-letter by most engines.
FILENAME_PATTERN = re.compile(
    r"\b[\w\-]+\.(?:pdf|docx?|txt|csv|xlsx?)\b",
    flags=re.IGNORECASE,
)

WHITESPACE_PATTERN = re.compile(r"\s+")

SYMBOL_REPLACEMENTS = {
    "%": " percent",
    "&": " and",
    "@": " at ",
    "=": " equals ",
    "+": " plus ",
    "~": " approximately ",
    "/": " ",
}

# Below this length an answer is already speakable, so the summarizing
# LLM call is skipped -- it would cost a full round-trip to shorten
# something that is short already.
SUMMARY_THRESHOLD_CHARS = 500
_speech_cache = {}

def _normalize_symbols(text: str) -> str:
    for symbol, spoken in SYMBOL_REPLACEMENTS.items():
        text = text.replace(symbol, spoken)
    return text


def clean_for_speech(text: str) -> str:
    """Strip citations and markdown, normalize symbols, cap length.

    This is the fallback path. It is used directly for short answers and
    whenever the summarizing LLM call fails.
    """

    spoken = CITATION_PATTERN.sub(" ", text)
    spoken = FILENAME_PATTERN.sub("the document", spoken)
    spoken = BULLET_PATTERN.sub(". ", spoken)
    spoken = MARKDOWN_PATTERN.sub("", spoken)
    spoken = _normalize_symbols(spoken)

    # Collapse the punctuation pile-ups the substitutions leave behind,
    # e.g. ". ." from a bullet that already ended in a full stop.
    spoken = re.sub(r"\.\s*\.", ".", spoken)
    spoken = WHITESPACE_PATTERN.sub(" ", spoken).strip()

    if len(spoken) <= settings.tts_max_chars:
        return spoken

    # Cut at the last sentence boundary inside the budget so the audio
    # doesn't stop mid-word, then flag that detail was left on screen.
    truncated = spoken[: settings.tts_max_chars]
    last_stop = max(
        truncated.rfind("."),
        truncated.rfind("?"),
        truncated.rfind("!"),
    )

    if last_stop > 0:
        return (
            truncated[: last_stop + 1]
            + " The full answer is on screen."
        )

    return truncated.rstrip() + ". The full answer is on screen."


def summarize_for_speech(text: str) -> str:
    """Rewrite a written answer as a short spoken sentence.

    Falls back to regex cleaning if the LLM call fails or returns
    something unusable -- voice mode should degrade, not break.
    """

    cleaned = clean_for_speech(text)

    if len(cleaned) <= SUMMARY_THRESHOLD_CHARS:
        return cleaned

    try:
        spoken = llm_client.generate(
            system_prompt=VOICE_SUMMARY_PROMPT,
            user_message=text,
            temperature=0.1,
            model=settings.tts_summary_model,
        )

    except RuntimeError:
        return cleaned

    spoken = spoken.strip().strip('"')

    # Guard against a model that ignores the instructions and returns
    # something longer than what we started with.
    if not spoken or len(spoken) > settings.tts_max_chars:
        return cleaned

    return spoken


async def synthesize_speech(text: str) -> bytes:
    """Convert text to MP3 audio bytes using Microsoft Edge neural voices."""

    spoken = summarize_for_speech(text)

    if not spoken:
        raise ValueError("No speakable text remained after cleaning.")

    communicate = edge_tts.Communicate(
        text=spoken,
        voice=settings.tts_voice,
    )

    audio = bytearray()

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])

    if not audio:
        raise RuntimeError("TTS engine returned no audio.")

    return bytes(audio)