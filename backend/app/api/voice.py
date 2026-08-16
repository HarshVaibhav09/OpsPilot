from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models.schemas import VoiceSpeakRequest
from app.services.voice_service import (
    summarize_for_speech,
    synthesize_speech,
)

router = APIRouter(
    prefix="/voice",
    tags=["voice"],
)


@router.post("/speak")
async def speak(request: VoiceSpeakRequest):

    if not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text is required.",
        )

    try:
        audio, spoken = await synthesize_speech(request.text)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:
        # Hand the cleaned text back so the client can fall back to
        # browser speech rather than reading raw markdown aloud.
        try:
            fallback_text = summarize_for_speech(request.text)
        except Exception:
            fallback_text = ""

        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Speech synthesis failed: {e}",
                "spoken_text": fallback_text,
            },
        )

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Expose-Headers": "X-Spoken-Text",
            "X-Spoken-Text": spoken.encode("ascii", "ignore").decode(),
        },
    )