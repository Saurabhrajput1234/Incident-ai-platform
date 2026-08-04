from fastapi import APIRouter
from app.api.v1 import health, db_health, incidents

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(db_health.router, tags=["database"])
api_router.include_router(incidents.router)
