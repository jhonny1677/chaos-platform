"""Results API — read-only access to experiment results."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.result import ResultList, ResultResponse
from app.database.connection import get_db
from app.database.repositories.result_repo import ResultRepository

router = APIRouter(prefix="/results", tags=["results"])


@router.get("", response_model=ResultList)
async def list_results(db: AsyncSession = Depends(get_db)):
    repo = ResultRepository(db)
    results = await repo.list_all()
    return ResultList(results=results, count=len(results))


@router.get("/experiment/{experiment_id}", response_model=ResultResponse)
async def get_result_for_experiment(experiment_id: str, db: AsyncSession = Depends(get_db)):
    repo = ResultRepository(db)
    result = await repo.get_by_experiment(experiment_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for experiment {experiment_id!r}",
        )
    return result


@router.get("/{result_id}", response_model=ResultResponse)
async def get_result(result_id: str, db: AsyncSession = Depends(get_db)):
    repo = ResultRepository(db)
    result = await repo.get(result_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Result {result_id!r} not found")
    return result
