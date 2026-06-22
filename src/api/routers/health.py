from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "ok"}

@router.get("/health/ready")
async def readiness() -> dict:
    return {"status": "ok"}
