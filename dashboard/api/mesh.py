"""API router exposing aggregated mesh status."""

from fastapi import APIRouter

from dashboard.services.mesh import get_mesh_status

router = APIRouter(tags=["mesh"])


@router.get("/mesh")
async def api_mesh():
    return get_mesh_status()
