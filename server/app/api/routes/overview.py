from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DatabaseDep

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview")
def overview(user: CurrentUser, db: DatabaseDep) -> dict:
    return db.overview(user["id"])
