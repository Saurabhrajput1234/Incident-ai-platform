from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import logger
from app.core.middleware import register_middlewares
from app.core.lifecycle import lifespan
from app.common.exceptions.handlers import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-ready AI Incident Management Platform.\n\n"
        "## Features\n"
        "- Incident lifecycle management (create, update, resolve, close)\n"
        "- Pagination, filtering, sorting and keyword search\n"
        "- Clean Architecture: API → Service → Repository → Database\n"
        "- PostgreSQL backend — replaceable with ServiceNow via repository swap\n\n"
        "## API Versioning\n"
        "All endpoints are prefixed with `/v1`."
    ),
    contact={
        "name": "Incident AI Platform Team",
        "email": "support@incidentai.internal",
    },
    license_info={
        "name": "Internal Use Only",
    },
    openapi_tags=[
        {"name": "health", "description": "Application liveness checks"},
        {"name": "database", "description": "Database connectivity checks"},
        {"name": "incidents", "description": "Incident management operations"},
    ],
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Middlewares
register_middlewares(app)

# Exception Handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Routers
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# WebSocket routes
from app.api.ws.incidents import router as ws_router
app.include_router(ws_router)
