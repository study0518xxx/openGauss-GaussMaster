# Controller / 核心层面试题

## 一、基础问题

### Q1: Controller 层的职责是什么？和 Service 层怎么划分？

**回答要点**：
- **Controller 层**（`controllers/core.py`）：负责 API 接口定义、参数校验、调用业务层、返回响应
- **Service 层**（`server/web/data_transformer.py`）：负责具体业务逻辑实现，如检索、推理、知识库管理
- **划分原则**：
  - Controller 只处理 HTTP 相关（路由、参数、响应格式）
  - Service 处理纯业务逻辑，不感知 HTTP 细节
  - 这样 Service 可以被其他入口复用（如 CLI、定时任务）

---

### Q2: 参数校验是怎么做的？为什么不用 FastAPI 自带的校验？

**回答要点**：
- 使用 `ParameterChecker` 类（`common/utils/checking.py`）定义校验规则
- 装饰器方式：`@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)`
- 校验规则包括：`NAME`、`STRING`、`IP_WITH_PORT`、`PINT32`、`TIMESTAMP` 等
- 和 FastAPI 自带校验的关系：
  - FastAPI + Pydantic 做基础类型校验（int、str、必填等）
  - `ParameterChecker` 做业务级校验（如 IP:Port 格式、时间范围、枚举值）
  - 两者互补，Pydantic 保证类型安全，`ParameterChecker` 保证业务合法

---

### Q3: `data_transformer.py` 里有哪些核心功能？

**回答要点**：
| 功能 | 函数 | 说明 |
|:---|:---|:---|
| 知识检索 | `search()` | 向量检索 + 文本检索 + 重排序 |
| 模型推理 | `infer()` | 直接调用 LLM 生成答案 |
| 端到端问答 | `ask_gauss()` | 检索 → 判断 → 生成，完整 QA 流程 |
| 查询优化 | `query_opt_process()` | HyDE + 查询改写，无结果时二次检索 |
| LLM 生成 | `llm_generation()` | 构造 Prompt，流式调用 LLM |
| 历史记录 | `get_history_chat()` | 从向量库获取历史问答 |
| 知识库管理 | `add_knowledge()` | 创建知识库、解析文件、入库 |
| 反馈管理 | `update_like_info()` | 点赞、点踩、反馈、报告 |

---

## 二、进阶问题

### Q4: `ask_gauss` 的完整流程是怎样的？

**回答要点**：
```
用户提问
    │
    ▼
1. 敏感词检测（DFA）→ 命中则拒答
    │
    ▼
2. 直接检索（向量+文本）
    │
    ├── 有结果 → 3. LLM 生成答案
    │
    └── 无结果 → 4. 查询优化流程
                    │
                    ├── HyDE（假设性文档扩展）
                    ├── 查询改写（生成多个变体 query）
                    ├── 二次检索
                    └── LLM 生成答案
```

**流式输出**：每个阶段都 yield 进度消息，前端实时看到"检索中..."、"生成中..."

---

### Q5: `infer()` 和 `ask_gauss()` 有什么区别？

**回答要点**：
| 特性 | `infer()` | `ask_gauss()` |
|:---|:---|:---|
| 是否需要检索 | 不需要，直接传 `search_res` | 需要，内部做检索 |
| 适用场景 | 前端已做检索，只调生成 | 完整端到端流程 |
| 参数 | question + search_res | question + 检索参数 |
| 复杂度 | 简单 | 复杂，包含查询优化 |

---

### Q6: 查询优化（Query Optimization）是怎么做的？

**回答要点**：
当首轮检索无结果时，触发三阶段优化：

1. **HyDE（Hypothetical Document Embeddings）**：
   - 让 LLM 根据问题生成一段假设性的回答文档
   - 用这段文档做向量检索，扩展语义覆盖

2. **查询改写（Query Transformation）**：
   - 让 LLM 将原问题改写为多个相关查询（带序号列表）
   - 对每个改写 query 分别检索

3. **合并去重**：
   - 合并所有检索结果，按相似度排序
   - 取 TopK 交给 LLM 生成最终答案

---

### Q7: 上下文管理器（`context_manager.py`）是做什么的？

**回答要点**：
- 使用 `contextvars` 实现**线程/协程安全的全局变量**
- 核心变量：
  - `current_instance`：当前用户选择的 DBMind 集群实例
  - `current_llm`：当前会话使用的大模型
- 为什么不用 `global_vars`：
  - `global_vars` 是进程级全局，多用户并发时会互相覆盖
  - `contextvars` 每个协程独立，适合异步并发场景

---

## 三、深挖问题

### Q8: `data_transformer.infer()` 为什么用 `yield` 而不是 `return`？

**回答要点**：
- `infer()` 是**异步生成器函数**（`async def + yield`）
- 原因：
  1. LLM 生成是流式的，每收到一个 token 就要推给前端
  2. 如果用 `return`，只能等全部生成完再返回，用户体验差（白屏等待）
  3. 用 `yield` 可以边生成边输出，前端实时看到文字逐字出现
- 配合 `@standardized_event_stream_output` 装饰器，将生成器包装为 SSE 响应

---

### Q9: 如果 LLM 服务响应超时或挂了，系统怎么处理？

**回答要点**：
1. **预检**：`check_url_connectivity()` 在调用前检查 LLM 服务是否可达
2. **超时**：`create_requests_session(timeout=...)` 设置请求超时
3. **重试**：HTTP 层自动重试 3 次
4. **异常捕获**：`standardized_event_stream_output` 捕获异常，yield 错误消息
5. **降级**：如果某个 LLM 不可用，可以切换到其他模型（`switch_llm()`）

---

### Q10: 知识库文件上传是怎么处理的？

**回答要点**：
```python
async def add_knowledge(name, user_id, file, kb_type, ...):
    # 1. 参数校验：文件数量 <= 10，大小 <= 限制
    # 2. 逐文件读取：分块读取（1MB/块），防止内存溢出
    # 3. 文件类型校验：只允许特定后缀
    # 4. 调用 gaussdb_vector.add_knowledge()：
    #    - 插入知识库元信息
    #    - 解析文件内容
    #    - 分块、Embedding、入库
```

**安全考虑**：
- 限制文件大小和数量，防止 DoS
- 校验文件后缀，防止上传可执行文件
- 分块读取，避免大文件占满内存

---

## 四、手写代码题

### 题目：实现一个带进度反馈的异步生成器

```python
async def process_with_progress(data_list):
    total = len(data_list)
    for i, item in enumerate(data_list):
        # 模拟处理
        await asyncio.sleep(0.1)
        result = f"processed_{item}"
        
        # 返回进度 + 结果
        yield {
            'type': 'progress',
            'data': f'Processing {i+1}/{total}'
        }
        yield {
            'type': 'result',
            'data': result
        }
    
    yield {
        'type': 'complete',
        'data': {'total': total}
    }
```
