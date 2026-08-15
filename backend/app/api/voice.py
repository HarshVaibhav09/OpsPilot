from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models.schemas import VoiceSpeakRequest
from app.services.voice_service import synthesize_speech

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
        audio = await synthesize_speech(request.text)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Speech synthesis failed: {e}",
        )

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
        },
    )