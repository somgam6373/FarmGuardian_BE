from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.catalog.presentation.router import router as catalog_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.farm.presentation.router import router as farm_router
from app.identity.presentation.router import router as identity_router
from app.inventory.presentation.router import router as inventory_router
from app.judgment.presentation.router import router as judgment_router
from app.spraying.presentation.router import router as spraying_router

app = FastAPI(title="FarmGuardian")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
# 일괄 프리뷰는 약마다 판정 한 벌이 붙어 크다 (약 274개까지)
app.add_middleware(GZipMiddleware, minimum_size=1000)
install_error_handlers(app)
app.include_router(farm_router)
app.include_router(identity_router)
app.include_router(catalog_router)
app.include_router(judgment_router)
app.include_router(spraying_router)
app.include_router(inventory_router)


@app.get("/health")
def health():
    return {"status": "ok"}
