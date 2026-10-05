"""HTTP routes. Thin: validate, delegate to the service, map errors."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from .. import MODEL_VERSION
from ..core import classic
from ..core.scenarios import PRESETS
from ..services.open_meteo import ProviderError, ProviderUnavailable
from ..services.simulation import LotusService
from .schemas import (
    CompareRequest,
    CompareResponse,
    PuzzleResponse,
    SensitivityRequest,
    SensitivityResponse,
    SimulationRequest,
    SimulationResponse,
)

router = APIRouter(prefix="/api/v1")
JSON = "application/json"


def service(request: Request) -> LotusService:
    return request.app.state.service


async def _guard(coro):
    try:
        return await coro
    except ProviderError as exc:
        raise HTTPException(status_code=422, detail=f"weather request rejected: {exc}") from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{exc}. Retry later, or use source='synthetic' for clearly labelled demo weather.",
        ) from exc


@router.get("/health")
async def health(request: Request) -> dict:
    return {"status": "ok", "model_version": MODEL_VERSION, "caches": service(request).stats()}


@router.get("/scenarios")
async def scenarios() -> dict:
    return {name: {"description": desc, **s.as_dict()} for name, (desc, s) in PRESETS.items()}


@router.post("/simulations", response_model=SimulationResponse, responses={200: {"content": {JSON: {}}}})
async def create_simulation(body: SimulationRequest, request: Request) -> Response:
    data, headers = await _guard(service(request).simulate(body))
    headers["Vary"] = "Accept-Encoding"
    if "gzip" in request.headers.get("accept-encoding", ""):
        headers["Content-Encoding"] = "gzip"  # pre-compressed; GZipMiddleware passes it through
        return Response(content=data.gz, media_type=JSON, headers=headers)
    return Response(content=data.raw, media_type=JSON, headers=headers)


@router.post("/simulations/compare", response_model=CompareResponse)
async def compare(body: CompareRequest, request: Request) -> Response:
    return Response(content=await _guard(service(request).compare(body)), media_type=JSON)


@router.post("/simulations/sensitivity", response_model=SensitivityResponse)
async def sensitivity(body: SensitivityRequest, request: Request) -> Response:
    return Response(content=await _guard(service(request).sensitivity(body)), media_type=JSON)


@router.get("/puzzle", response_model=PuzzleResponse)
async def puzzle(
    initial: float = Query(2.0**-30, gt=0, allow_inf_nan=False),
    multiplier: float = Query(2.0, gt=1, le=100, allow_inf_nan=False),
    capacity: float = Query(1.0, gt=0, allow_inf_nan=False),
    days: int = Query(30, ge=1, le=1000),
) -> PuzzleResponse:
    return PuzzleResponse(
        initial=initial,
        multiplier=multiplier,
        capacity=capacity,
        days_to_fill=classic.days_to_fill(initial, multiplier, capacity),
        half_full_day=classic.day_at_fraction(0.5, initial, multiplier, capacity),
        series=classic.series(initial, multiplier, capacity, days),
    )
