from fastapi import APIRouter, HTTPException

from app.api.dependencies import DatabaseDep

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DatabaseDep) -> dict[str, str]:
    try:
        with db.connect() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ok"}
