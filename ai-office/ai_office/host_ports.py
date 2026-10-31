# -*- coding: utf-8 -*-
"""host_ports —— 引擎取用宿主能力的唯一端口（2026-11-01 融合区预解）。

宿主实现由 backend/app/services/engine_wiring.py 在启动时注册（wire_engine）；
引擎模块只写 `hp.module_port("assistant_hub")` / `hp.fn_port("plan_builder.build_plan")`
这样的惰性代理，运行时才解析——引擎树零宿主 import，位置法可见。

未接线即红：端口没注册时调用会抛 PortNotWired（宿主接线缺失当场暴露，不静默降级）。
新增端口 = 宿主 engine_wiring 的 MODULE_ATTRS 表加一行 + 引擎侧把 import 换成代理。
"""
from __future__ import annotations

# 首次接线时的默认实现快照：mock.patch 的还原走 delattr，代理据此恢复接线默认值
_DEFAULTS: dict = {}
_PORTS: dict = {}


class PortNotWired(RuntimeError):
    """端口未注册（宿主接线缺失）。"""


def register_port(name: str, impl) -> None:
    """宿主接线入口（engine_wiring 专用；幂等覆盖）。

    impl = **零参取值器**（返回当前目标）——接线器存的是动态解析器，端口每次
    取用都现取宿主模块属性：monkeypatch/热替换当场生效。首次注册记为默认值
    （测试 patch 完 delattr 还原时的锚点）。"""
    key = str(name or "").strip()
    if key:
        if key not in _PORTS:
            _DEFAULTS[key] = impl
        _PORTS[key] = impl


def port(name: str):
    """按名取宿主实现（返回取值器的当前结果，非解析器本身）。"""
    try:
        getter = _PORTS[name]
    except KeyError:
        raise PortNotWired(f"引擎端口未注册：{name}（宿主接线缺失，见 engine_wiring.py）") from None
    return getter()


def wired_names() -> list:
    return sorted(_PORTS)


class _FnPort:
    """可调用端口代理：调用时才解析宿主实现（惰性，免 import 序问题）。"""
    __slots__ = ("_name",)

    def __init__(self, name: str):
        self._name = name

    def __call__(self, *args, **kwargs):
        return port(self._name)(*args, **kwargs)


class _ModulePort:
    """宿主模块/对象代理：属性访问时才解析（assistant_hub.broadcast 这类）。

    支持 setattr：测试 monkeypatch 代理属性 = 覆盖对应端口（还原时写回旧值），
    同名端口的所有代理一并生效。"""
    __slots__ = ("_name",)

    def __init__(self, name: str):
        object.__setattr__(self, "_name", name)

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(self._name)
        return port(f"{self._name}.{attr}")

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            object.__setattr__(self, attr, value)
            return
        register_port(f"{self._name}.{attr}", lambda v=value: v)

    def __delattr__(self, attr):
        if attr.startswith("_"):
            object.__delattr__(self, attr)
            return
        key = f"{self._name}.{attr}"
        default = _DEFAULTS.get(key)
        if default is None:
            _PORTS.pop(key, None)
        else:
            _PORTS[key] = default


def fn_port(name: str) -> _FnPort:
    """宿主函数端口（from X import fn 形态的替身）。"""
    return _FnPort(name)


def module_port(name: str) -> _ModulePort:
    """宿主模块/单例对象端口（from X import obj 形态的替身）。"""
    return _ModulePort(name)
