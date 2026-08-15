import re

import edge_tts

from app.core.config import settings

# Citations read terribly out loud -- "(Source: incident_log.pdf, page 12)"
# becomes a mouthful of punctuation and file extensions. They stay in the
# text answer on screen; the spoken version drops them.
CITATION_PATTERN = re.compile(
    r"\(\s*Source:.*?\)",
    flags=re.IGNORECASE | re.DOTALL,
)

MARKDOWN_PATTERN = re.compile(r"[*_#`]+")

WHITESPACE_PATTERN = re.compile(r"\s+")


def clean_for_speech(text: str) -> str:
    """Strip citations and markdown, then cap length for the TTS engine."""

    spoken = CITATION_PATTERN.sub(" ", text)
    spoken = MARKDOWN_PATTERN.sub("", spoken)
    spoken = WHITESPACE_PATTERN.sub(" ", spoken).strip()

    if len(spoken) <= settings.tts_max_chars:
        return spoken

    # Cut at the last sentence boundary inside the budget so the audio
    # doesn't stop mid-word.
    truncated = spoken[: settings.tts_max_chars]
    last_stop = max(
        truncated.rfind("."),
        truncated.rfind("?"),
        truncated.rfind("!"),
    )

    if last_stop > 0:
        return truncated[: last_stop + 1]

    return truncated.rstrip() + "..."


async def synthesize_speech(text: str) -> bytes:
    """Convert text to MP3 audio bytes using Microsoft Edge neural voices."""

    spoken = clean_for_speech(text)

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