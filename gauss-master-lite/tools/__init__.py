"""
工具模块入口 —— 导入即注册所有工具
对标 GaussMaster 的 tools/__init__.py
"""

from .diagnostics import tools

# 导出全局工具注册表
tool_registry = tools
