import sys

# Windows 控制台默认 GBK 编码，含 emoji 的 print（如 startup.py 的 ✅/🧹）会触发
# UnicodeEncodeError 导致 FastAPI lifespan 启动崩溃。强制 stdout/stderr 为 UTF-8，
# 使任意终端、任意启动方式（uvicorn / .bat）下日志输出都一致且不崩。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.exception_handlers import (
    business_error_handler,
    validation_error_handler,
    generic_exception_handler
)
from app.api import quote
from app.api import opportunities
from app.api import admin
from app.api import rules
from app.api import comments
from app.api import dashboard
from app.api import quotations
from app.api import univer_templates
from app.api import l6_chassis
from app.api import fields as fields_api
from app.api import system_config as system_config_api
from app.core.startup import init_rules_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_rules_db()
    yield
    # Shutdown (if needed)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="CPQ Platform API (Quotation Automation)",
    lifespan=lifespan
)

# Register exception handlers
app.add_exception_handler(BusinessError, business_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(quote.router)
app.include_router(opportunities.router)
app.include_router(admin.router)
app.include_router(rules.router)
app.include_router(comments.router)
app.include_router(dashboard.router)
app.include_router(quotations.router)
app.include_router(univer_templates.router)
app.include_router(l6_chassis.router)
app.include_router(fields_api.router)
app.include_router(system_config_api.router)

@app.get("/")
def root():
    return {"message": f"Welcome to CPQ Platform API v{settings.APP_VERSION}", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
