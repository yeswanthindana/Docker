from fastapi import APIRouter
from app.api.endpoints import local, remote

api_router = APIRouter()

api_router.include_router(local.router, prefix="/api", tags=["Local Docker"])
api_router.include_router(remote.router, prefix="/api/remote", tags=["Remote Docker"])
