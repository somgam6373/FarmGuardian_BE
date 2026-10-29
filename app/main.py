from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.catalog.presentation.router import router as catalog_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.farm.presentation.router import router as farm_router

app = FastAPI(title="FarmGuardian")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)
app.include_router(farm_router)
app.include_router(catalog_router)


@app.get("/health")
def health():
    return {"status": "ok"}
