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
import hashlib
import os
from logging.handlers import RotatingFileHandler

# app.* 日志同时落文件：bat/cmd 窗口启动的服务排障时窗口内容不可得（2026-10-22 实锤），
# 文件是唯一可靠的现场。5MB 轮转 ×3。
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "app.log"), maxBytes=5_000_000, backupCount=3, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
logging.getLogger().addHandler(_file_handler)


def _source_stamp(root: str) -> str:
    """源码指纹：app/**/*.py 的 相对路径|mtime|size 哈希。import 时算一次
    （=本进程正在运行的代码状态）；/build-stale 按请求现算磁盘状态。
    两者不一致 = 有源码在本进程启动后变过（--reload 静默失效/僵尸进程——
    2026-10-22 实锤 5+ 次的"改了没生效"，一键启动脚本体检用）。"""
    h = hashlib.sha256()
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            h.update(f"{os.path.relpath(p, root)}|{st.st_mtime_ns}|{st.st_size};".encode("utf-8", "ignore"))
    return h.hexdigest()[:16]


APP_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_STAMP = _source_stamp(APP_DIR)

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
from app.api import artifact_share
from app.api import admin
from app.api import rules
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
app.include_router(artifact_share.router)
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
    return {"status": "ok", "build": BUILD_STAMP}


@app.get("/build-stale")
def build_stale():
    """运行中代码 vs 磁盘代码（一键启动脚本体检用）。stale=true = 有 .py 在本进程
    启动后变过——当前服务的是旧代码，重启后端即可对齐。"""
    disk = _source_stamp(APP_DIR)
    return {"running": BUILD_STAMP, "disk": disk, "stale": disk != BUILD_STAMP}
