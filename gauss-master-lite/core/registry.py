"""
工具注册中心 —— 装饰器模式
对标 GaussMaster 的 GaussMaster/common/plugins/registry.py
"""

import inspect
import logging
from typing import Callable, Optional


class ToolRegistry(dict):
    """
    可调用、可迭代的工具注册表。
    
    用法:
        tools = ToolRegistry()

        @tools.register(
            name="get_instance_status",
            description="查询当前数据库实例运行状态",
        )
        def get_instance_status():
            return {"status": "running"}
    """

    def __init__(self):
        super().__init__()
        self._tools: dict[str, Callable] = {}

    def register(
        self,
        name: str,
        description: str,
        params: Optional[list[dict]] = None,
    ):
        """装饰器：将函数注册为工具"""
        if params is None:
            params = []

        def decorator(func: Callable):
            # 用 inspect 获取函数签名来校验参数
            sig = inspect.signature(func)
            func_params = []
            for p_name, p_param in sig.parameters.items():
                is_optional = p_param.default is not inspect.Parameter.empty
                func_params.append({
                    "name": p_name,
                    "required": not is_optional,
                    "type": str(p_param.annotation) if p_param.annotation is not inspect.Parameter.empty else "str",
                })

            # 挂载元数据到函数上
            func.__tool_name__ = name
            func.__tool_description__ = description
            func.__tool_params__ = func_params
            func.__tool_params_declared__ = params or func_params

            # 生成给 LLM 看的工具描述
            func.__tool_detail__ = _build_tool_detail(name, description, func_params)

            if name in self._tools:
                logging.warning(f"工具 '{name}' 重复注册，将被覆盖")

            self._tools[name] = func
            self[name] = func

            return func

        return decorator

    def get(self, name: str, default=None):
        return self._tools.get(name, default)

    def all_tools(self) -> dict[str, Callable]:
        return dict(self._tools)

    def list_details(self) -> list[str]:
        """返回所有工具的描述列表（给 LLM prompt 用）"""
        return [t.__tool_detail__ for t in self._tools.values()]

    def get_detail(self, name: str) -> Optional[str]:
        tool = self._tools.get(name)
        if tool:
            return tool.__tool_detail__
        return None

    def validate_params(self, tool_name: str, params: dict) -> tuple[bool, dict, dict]:
        """
        校验参数完整性
        返回: (is_complete, valid_params, missing_params)
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return False, {}, {"_error": f"工具 {tool_name} 不存在"}

        missing = {}
        valid = {}
        for p in tool.__tool_params__:
            if p["name"] in params:
                valid[p["name"]] = params[p["name"]]
            elif p["required"]:
                missing[p["name"]] = f"缺少必填参数: {p['name']}"

        if missing:
            return False, valid, missing
        return True, valid, {}


def _build_tool_detail(name: str, description: str, params: list[dict]) -> str:
    """构建工具描述字符串"""
    parts = [f"{name}: {description}"]
    if params:
        param_strs = []
        for p in params:
            opt = "(必填)" if p["required"] else "(可选)"
            param_strs.append(f"{p['name']}{opt}")
        parts.append(f"  参数: {', '.join(param_strs)}")
    return "\n".join(parts)
