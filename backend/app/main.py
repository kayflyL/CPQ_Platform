import sys

# Windows 控制台默认 GBK 编码，含 emoji 的 print（如 startup.py 的 ✅/🧹）会触发
# UnicodeEncodeError 导致 FastAPI lifespan 启动崩溃。强制 stdout/stderr 为 UTF-8，
# 使任意终端、任意启动方式（uvicorn / .bat）下日志输出都一致且不崩。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# uvicorn 只给 uvicorn.* 配日志 handler，app.* 的 logger.exception/info 不落任何输出，
# 出错不留痕（2026-08-29「消息被静默吞掉」排障最大障碍）。接通根 handler 使应用日志可见。
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

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
from app.api import parts as parts_api
from app.api import server_catalog as server_catalog_api
from app.api import base_configs as base_configs_api
from app.api import fields as fields_api
from app.api import system_config as system_config_api
from app.api import ai_colleagues as ai_colleagues_api
from app.api import office as office_api
from app.api import kp_config as kp_config_api
from app.api import bom_templates as bom_templates_api
from app.api import spec_templates as spec_templates_api
from app.api import feed as feed_api
from app.api import assistant as assistant_api
from app.api import strategies as strategies_api
from app.api import solutions as solutions_api
from app.api import gpu_sizing_api  # AI 推理配置器（显存门禁计算）
from app.api import bom_cases as bom_cases_api
from app.api import reasoning_flow as reasoning_flow_api
from app.api import compatibility_rules as compatibility_rules_api
from app.api import auth as auth_api
from app.api import roles as roles_api
from app.api import portal as portal_api
from app.api import notifications as notifications_api
from app.api import artifact_templates as artifact_templates_api
from app.core.startup import init_rules_db
from app.services.office_clock import office_clock

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_rules_db()
    await office_clock.start()
    try:
        yield
    finally:
        await office_clock.stop()


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
app.include_router(parts_api.router)
app.include_router(server_catalog_api.router)
app.include_router(base_configs_api.router)
app.include_router(fields_api.router)
app.include_router(system_config_api.router)
app.include_router(ai_colleagues_api.router)
app.include_router(office_api.router)
app.include_router(kp_config_api.router)
app.include_router(bom_templates_api.router)
app.include_router(spec_templates_api.router)
app.include_router(feed_api.router)
app.include_router(assistant_api.router)
app.include_router(strategies_api.router)
app.include_router(solutions_api.router)
app.include_router(gpu_sizing_api.router)
app.include_router(bom_cases_api.router)
app.include_router(reasoning_flow_api.router)
app.include_router(compatibility_rules_api.router)
app.include_router(auth_api.router)
app.include_router(roles_api.router)
app.include_router(portal_api.router)
app.include_router(notifications_api.router)
app.include_router(artifact_templates_api.router)

# 注册后面板配置 API
from app.api import rear_io
app.include_router(rear_io.router)

@app.get("/")
def root():
    return {"message": f"Welcome to CPQ Platform API v{settings.APP_VERSION}", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
