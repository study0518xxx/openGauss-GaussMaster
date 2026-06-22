"""
tools/registry.py — 工具注册表
对应 GaussMaster: common/plugins/registry.py + common/plugins/param.py

核心设计：
1. Param 类 — 定义工具参数（名、类型、是否必填）
2. ToolRegistry 类 — 注册、校验、执行工具的注册表
3. 装饰器模式 — @registry.register() 一行注册

和 GaussMaster 的双格式设计一致：
- get_tools_desc() → 阶段一（选工具）：文本列表给 LLM
- get_tool_schema() → 阶段二（填参数）：单个工具详细 schema 给 LLM
- validate_params() → 模拟 inspect.signature 的确定性校验
"""


class Param:
    """工具参数定义 — 对应 GaussMaster 的 common/plugins/param.py"""
    def __init__(self, name: str, description: str, param_type: str = "str", required: bool = True):
        self.name = name
        self.description = description
        self.type = param_type
        self.required = required

    def __repr__(self):
        req = "必填" if self.required else "可选"
        return f"{self.name}({self.type}, {req})"


class ToolRegistry:
    """
    工具注册表 — 对应 GaussMaster 的 common/plugins/registry.py
    
    GaussMaster 用 Registry(dict) 作为装饰器，Demo 用 dict 简化
    """
    def __init__(self):
        self._tools = {}  # {tool_name: {"name":..., "desc":..., "params":..., "func":...}}

    def register(self, name: str, description: str, params: list[Param]):
        """装饰器，注册工具 — 对应 @base_tools(...)"""
        def decorator(func):
            self._tools[name] = {
                "name": name,
                "description": description,
                "params": params,
                "func": func,
            }
            print(f"  [registry] 注册工具: {name} ({len(params)} 个参数)")
            return func
        return decorator

    def get_tools_desc(self) -> str:
        """
        阶段一用：生成"工具名 + 描述"列表
        对应 GaussMaster 的 detail_without_param_str_list
        
        返回示例:
          get_cpu_usage: 获取数据库实例 CPU 使用率
          get_slow_queries: 获取慢 SQL 列表
          get_connections: 获取连接数信息
        """
        lines = []
        for tool in self._tools.values():
            lines.append(f"{tool['name']}: {tool['description']}")
        return '\n'.join(lines)

    def get_tool_schema(self, tool_name: str) -> str:
        """
        阶段二用：单个工具的详细 schema（含参数详情）
        对应 GaussMaster 的 detail_with_param_str
        
        返回示例:
          get_cpu_usage: 获取数据库实例 CPU 使用率
          参数:
          - instance(str)[必填]: 数据库实例名称，如 db_001
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return f"工具 {tool_name} 不存在"

        lines = [f"{tool['name']}: {tool['description']}"]
        lines.append("参数：")
        if not tool["params"]:
            lines.append("  (无参数，直接调用)")
        else:
            for p in tool["params"]:
                req = "必填" if p.required else "可选"
                lines.append(f"  - {p.name}({p.type})[{req}]: {p.description}")
        return '\n'.join(lines)

    def validate_params(self, tool_name: str, params: dict) -> tuple:
        """
        参数校验 — 对应 GaussMaster 的 has_correct_params() + inspect.signature
        
        规则：
        1. LLM 多给的参数 → 丢弃（防止注入）
        2. 缺失的必填参数 → 返回 False + 缺失列表
        3. 参数完整 → 返回 True
        
        返回: (是否通过, 清洗后的参数, 缺失参数列表)
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return False, {}, ["工具不存在"]

        # 只保留工具定义中存在的参数（多余的丢弃）
        valid_params = {}
        for k, v in params.items():
            if k in [p.name for p in tool["params"]]:
                valid_params[k] = v
            else:
                print(f"  [registry] 丢弃多余参数: {k}={v}")

        # 检查必填参数是否齐全
        missing = [p.name for p in tool["params"] if p.required and p.name not in valid_params]
        if missing:
            return False, valid_params, missing

        return True, valid_params, []

    def execute(self, tool_name: str, params: dict):
        """
        执行工具 — 对应 GaussMaster 的 call_tool()
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return {"error": f"工具 {tool_name} 不存在"}
        return tool["func"](**params)

    def is_no_param(self, tool_name: str) -> bool:
        """判断是否无参数工具 — 对应 GaussMaster 的 check_is_no_param_tool()"""
        tool = self._tools.get(tool_name)
        return tool is not None and len(tool["params"]) == 0
