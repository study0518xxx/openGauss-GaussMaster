# 第二步面试 QA：RAG 问答链 + 安全检测 + LLM 模型层

> 面试场景：打开 `data_transformer.py` / `prompt_util.py` / `BaseLLM.py`，面试官边看边问。

---

## 问题索引

| # | 问题 | 关联模块 |
|---|------|---------|
| 1 | RAG 问答链从头到尾怎么走的？画一下流程 | `data_transformer.py` |
| 2 | 安全检测怎么做的？DFA 和 XLNet 各管什么？ | 安全模块 |
| 3 | reranker 和 embedding 检索有什么区别？score < 0 过滤怎么理解？ | `OnlineReranker` |
| 4 | HyDE 降级是什么？为什么能提升召回？ | `data_transformer.py` |
| 5 | 查询改写和 HyDE 的区别？什么时候用哪个？ | `data_transformer.py` |
| 6 | 提示模板体系怎么设计的？有哪几个模板？ | `prompt_util.py` |
| 7 | 为什么支持 6 种模型？模型包装器怎么做的？ | `BaseLLM.py` + `llm_registry` |
| 8 | DeepSeek 和盘古走的是同一条调用路径吗？ | 通用 HTTP 路径 vs LLM 类路径 |
| 9 | 和 LangChain RAG 的核心差异是什么？ | 整体对比 |
| 10 | SSE 流式输出怎么实现的？和普通返回有什么区别？ | `data_transformer.py:generate_answer()` |
| 11 | RAG 和 Agent 怎么切换？意图路由在哪一层？ | 路由逻辑 |
| 12 | 怎么评估 RAG 回答质量？怎么知道回答好不好？ | 落地数据 |

---

## Q1：RAG 问答链从头到尾怎么走？

**答**：RAG 管道入口是 `/v1/api/ask_gauss`，和 Agent 管道是两个独立端点，不做自动路由。

```
用户点 "知识问答" → /v1/api/ask_gauss
  │
  ▼
① 安全检测
  ├─ DFA Trie 树扫描 → 无障碍词 ✓
  └─ XLNet 分类 → 非高风险 ✓
  │
  ▼
② 混合检索
  ├─ 向量检索: L2 距离 TOP-10
  └─ BM25 全文: 关键词匹配 TOP-10
  │
  ▼
③ 合并去重 → BGE-reranker 交叉打分
  ├─ score ≥ 0 → 保留
  └─ score < 0 → 丢弃
  │
  ▼
④ 有结果吗？
  ├─ 有 → 跳⑥
  └─ 无 ↓
  │
  ▼
⑤ 降级策略
  ├─ HyDE: LLM 生成假设答案 → 用假设答案重新检索
  └─ 查询改写: 拆成 3 个子问题 → 分别检索
  │
  ▼
⑥ 拼接 prompt（系统提示 + 参考资料 + 对话历史 + 用户问题）
  │
  ▼
⑦ LLM 生成答案（SSE 流式输出）
  │
  ▼
⑧ 输出安全检测（XLNet 再次检查）
  │
  ▼
返回给用户
```

**为什么是 7 步，不是简单的"检索 + 生成"**：每一步都在解决一个具体问题——安全检测防攻击、混合检索防漏、reranker 防噪声、HyDE 防空结果、输出检测防 jailbreak。银行场景容错率极低，每一步都不能省。

> Agent 管道（`/v1/api/app/intelligent-interaction`）是独立入口，不走这个流程，详见 step3。

---

## Q2：安全检测怎么做的？DFA 和 XLNet 各管什么？

**答**：两层，输入输出两端都过。

**第一层：DFA（显式检测）**

| 项目 | 详情 |
|------|------|
| 数据结构 | Trie 树 |
| 词库规模 | 2 万+ 条敏感词/危险命令 |
| 时间复杂度 | O(n)，输入长度线性 |
| 覆盖 | "DROP TABLE"、"rm -rf"、"shutdown"、"DELETE FROM ... WHERE" 等 |

为什么用 Trie 不是正则：2 万条正则逐条匹配是 O(n×m)，Trie 是 O(n)。输入 200 字的用户问题，Trie 扫描 0.1ms 以内。

**第二层：XLNet（隐式检测）**

| 项目 | 详情 |
|------|------|
| 模型 | XLNet 微调版 |
| 任务 | 文本风险二分类（safe / risky） |
| 推理时间 | < 500ms |
| 覆盖 | 不含敏感词但意图危险的输入 |

**为什么需要第二层**：用户说"帮我把生产库的数据清掉重新建一下"——这句话不含任何敏感词，DFA 完全检测不到，但意图明显危险。XLNet 能理解语义，判定为高风险。

**输入输出两端都过**：输入防止恶意提问，输出防止 LLM 被 jailbreak 后生成危险内容（比如诱导 LLM 输出 `DELETE` 语句）。

---

## Q3：reranker 和 embedding 检索有什么区别？

**答**：本质区别是**各看各的 vs 一起看**。

---

### 先看一个具体例子

假设知识库里有 3 个文档块：

```
块A: "CPU 使用率过高时，首先检查慢 SQL。通过 pg_stat_activity
      可以查看当前正在执行的查询。（后接 200 字排查指南）"

块B: "连接数过多也会导致 CPU 资源争抢。当活跃连接超过
      max_connections 的 80% 时，大量连接抢占 CPU 时间片。
      （后接 150 字连接池优化指南）"

块C: "GaussDB 的 shared_buffers 参数建议设置为物理内存的 25%。
      过大会导致操作系统缓存不足，过小会导致频繁磁盘读取。
      （后接 100 字参数调优说明）"
```

用户问：**"CPU 使用率过高怎么办"**

---

### embedding 检索怎么打分

**第 1 步**：把 3 个块分别转成向量（各 1024 个数字）。

```
块A → [0.12, -0.34, 0.56, 0.03, ...]  ← 1024 个 float32
块B → [-0.08, 0.45, 0.22, -0.67, ...]
块C → [0.31, -0.12, -0.43, 0.55, ...]
```

**第 2 步**：用户问题也转成向量。

```
问题 "CPU 使用率过高怎么办" → [0.10, -0.31, 0.53, 0.01, ...]
```

**第 3 步**：逐一算距离，每个块各算各的。

```
问题向量 vs 块A向量:
  [0.10, -0.31, 0.53, 0.01, ...]   ← 问题
  [0.12, -0.34, 0.56, 0.03, ...]   ← 块A
           ↓
  距离 = 0.22  ✅ 很近！排第 2

问题向量 vs 块B向量:
  [0.10, -0.31, 0.53, 0.01, ...]   ← 问题
  [-0.08, 0.45, 0.22, -0.67, ...]  ← 块B
           ↓
  距离 = 0.19  ✅ 居然最近！排第 1

问题向量 vs 块C向量:
  [0.10, -0.31, 0.53, 0.01, ...]   ← 问题
  [0.31, -0.12, -0.43, 0.55, ...]  ← 块C
           ↓
  距离 = 0.68  ❌ 比较远，排第 3
```

**embedding 的排序结果**：

```
第 1 名: 块B（连接数过多导致 CPU 争抢）— 距离 0.19
第 2 名: 块A（CPU 使用率过高排查指南）  — 距离 0.22
第 3 名: 块C（shared_buffers 参数）     — 距离 0.68
```

**出问题了**：块 B 排在块 A 前面。为什么？因为块 B 的文字里大量出现了 "CPU"、"资源"、"争抢"、"连接"——和问题里的 "CPU"、"过高" 在 1024 维空间里碰巧离得近。embedding 只看两个向量像不像，不看内容逻辑——它不知道块 B 是在讲连接数，不是在讲 CPU 排查。

---

### reranker 怎么打分

reranker 不是先转成向量再算距离。它把问题和文档**拼成一段话**，直接塞给一个模型，让模型判断 "这段话是不是在回答这个问题"。

**第 1 步**：拼接。

```
输入 1: [CLS] CPU 使用率过高怎么办 [SEP] CPU 使用率过高时，首先检查慢 SQL。
         通过 pg_stat_activity 可以查看当前正在执行的查询... [SEP]

输入 2: [CLS] CPU 使用率过高怎么办 [SEP] 连接数过多也会导致 CPU 资源争抢。
         当活跃连接超过 max_connections 的 80% 时... [SEP]

输入 3: [CLS] CPU 使用率过高怎么办 [SEP] GaussDB 的 shared_buffers 参数
         建议设置为物理内存的 25%... [SEP]
```

**第 2 步**：模型同时看到问题和文档，逐字阅读，然后输出一个分数。

```
输入 1 → 模型读: "问题在问CPU过高怎么办，文档在说CPU排查步骤、慢SQL、pg_stat_activity
                 ——对的，文档就是在回答这个问题"
         → 输出: 0.91  ✅ 高分

输入 2 → 模型读: "问题在问CPU过高怎么办，文档在说连接数、连接池……等一下，
                 虽然提到了CPU，但核心话题是连接数管理，不是CPU排查"
         → 输出: 0.12  ⚠️ 低分，不相关

输入 3 → 模型读: "问题在问CPU过高怎么办，文档在说shared_buffers内存参数……
                 完全不搭"
         → 输出: -0.35 ❌ 负分，强烈不相关
```

**reranker 的排序结果**：

```
第 1 名: 块A（CPU 排查指南） — 0.91 ✅
第 2 名: 块B（连接数争抢）   — 0.12 ⚠️
第 3 名: 块C（内存参数）     — -0.35 ❌ → 丢弃
```

---

### 两种打分对比

```
                       embedding 排序        reranker 排序
                       ─────────────        ────────────
第 1 名                 块B (0.19)           块A (0.91)  ← 纠正了
第 2 名                 块A (0.22)           块B (0.12)
第 3 名                 块C (0.68)           块C (-0.35) ← 丢弃
```

embedding 把块 B 排第一是错的。reranker 把块 A 纠正到第一，并且发现块 C 是负分直接丢掉。

---

### 为什么 embedding 会排错，而 reranker 能排对

| | embedding | reranker |
|---|---|---|
| 看到了什么 | 每个文档**单独转**成一个向量，然后和问题向量比角度 | 问题和文档**拼在一起**，同时看 |
| 能判断什么 | 这段文字和问题 "用词像不像" | 这段文字 "是不是在回答这个问题" |
| 为什么块B排错了 | 块B 大量出现 "CPU"、"资源"、"争抢"，向量方向和问题向量接近 | reranker 读完全文发现块B 的核心是 "连接数管理" 不是 "CPU排查" |

**一句话**：embedding 看的是 "长得像不像"，reranker 看的是 "是不是在回答"。

---

### 为什么要两步都做，而不是只用 reranker

因为慢。

| | embedding 检索 | reranker 打分 |
|---|---|---|
| 处理量 | 全库 100 万个块 | 只处理候选的 15 个块 |
| 速度 | 毫秒级（GSDiskANN 索引） | 每个对几百毫秒 |
| 为什么 | 只算一次向量距离 | 每次都要跑一遍模型 |

如果把 100 万个块全部送 reranker 打分 → 100 万 × 0.5 秒 = 几天。所以流程是：

```
100 万块 → embedding 粗筛 → 15 个候选 → reranker 精排 → 3 个送 LLM
           ↑ 毫秒级               ↑ 只在 15 个上跑
```

---

### 面试一句话版

> embedding 是粗筛——全库海选，只看用词像不像，快但会漏会错。reranker 是精排——把候选块和问题拼在一起让模型读，看是不是真的在回答这个问题，慢但准。两步各取所长。

---

### 完整的三段过滤流程

所以 "Top-3" 不是直接从全库取 3 个——中间有 reranker 做纠错：

```
向量检索                    BM25 检索
Top-10                     Top-10
┌──────┐                  ┌──────┐
│ 块A  │                  │ 块A  │ ← 两路都命中，去重
│ 块B  │                  │ 块F  │
│ 块C  │                  │ 块G  │
│ 块D  │                  │ 块H  │
│  ... │                  │  ... │
└──────┘                  └──────┘
     │                        │
     └──────────┬─────────────┘
                ▼
         合并去重 → 15~18 个候选
                │
                ▼
         reranker 逐一打分
         (每个候选都和问题拼一起，模型独立判分)
                │
                ▼
         按新分重排，score < 0 丢弃
                │
                ▼
         Top-3 送 LLM
```

reranker 不受 embedding 排序影响——embedding 排第 4 的块如果内容真的相关，reranker 会给它高分把它拉到前 3。你担心 embedding 漏掉的，reranker 负责捞回来。

---

### 还有一道保险：相邻块拼接

GaussMaster 每一块都存了 `prev_uuid` 和 `next_uuid`——前后块的 ID。reranker 选出 Top-3 后，系统自动把每块的前一块和后一块也拽出来拼上：

```
reranker 选中 Top-3:
  块D（第3名）         ← reranker 选的
  块A（第1名）         ← reranker 选的
  块F（第2名）         ← reranker 选的

相邻块拼接后送给 LLM 的实际内容:
  ┌──────────────────────────────────────┐
  │ 块D-1: CPU 排查第 2 步...             │ ← 自动补
  │ 块D:   第 3 步，使用 EXPLAIN ANALYZE...│ ← reranker 选的
  │ 块D+1: 第 4 步，检查统计信息...        │ ← 自动补
  │──────────────────────────────────────│
  │ 块A:   CPU 使用率过高诊断指南...        │
  │──────────────────────────────────────│
  │ 块F-1: 慢 SQL 优化建议...              │
  │ 块F:   索引优化实战...                  │
  │ 块F+1: 执行计划分析...                  │
  └──────────────────────────────────────┘

表面 Top-3 → LLM 实际收到 5~9 个块，上下文更完整
```

---

### 为什么不直接取 Top-10 送 LLM

三个原因：

1. **上下文窗口**：10 个块 ≈ 5000 字 + prompt 模板 + 对话历史 + 安全提示 ≈ 8000 字。DeepSeek 扛得住，但 LLM 对长文本中间的信息容易 "失焦"——靠后的块权重远低于靠前的。

2. **噪音问题**：未过滤的 10 个块里可能 7 个是弱相关或噪声。LLM 看到一堆不太相关的参考资料，更容易编造答案（"参考资料没有但我猜……"）。3 个高质量块 > 10 个混杂块。

3. **reranker 已经过滤过了**：15~18 个候选经过 reranker 后，score < 0 的已丢弃，剩 3~5 个高分块。取前 3 个 + 相邻扩展，质量已经足够。

## Q4：HyDE 降级是什么？为什么能提升召回？

**答**：HyDE（Hypothetical Document Embeddings，假设文档嵌入）——让 LLM 编一个答案，用这个假答案去检索。

```
场景: 用户问 "备机重建失败怎么处理"
  → 向量+BM25 检索 → 无结果

HyDE 流程:
① 给 LLM 一个 prompt: "请生成一段关于备机重建失败处理方法的说明"
② LLM 输出: "备机重建失败可能由于网络中断、WAL 日志不连续、
   或者 gs_ctl build 命令参数错误。排查步骤包括：检查网络连通性、
   查看 WAL 发送状态、确认 build 命令参数正确……"
③ 用这段假设答案做向量化
④ 重新检索 → 命中 "gs_ctl build 参数说明" 等文档
```

**为什么有效**：

- 用户问题短（15 字）、用词可能不规范
- LLM 生成的假设答案长（200+ 字）、术语规范
- 向量检索对长篇规范文本的匹配效果远好于短篇口语化文本

本质是**用 LLM 的生成能力弥补检索的匹配能力**。检索擅长找"长得像"的文本，HyDE 先把问题"变长变规范"，再去匹配。

**追问：HyDE 不会编错答案导致检索到错误文档吗？**  
会，但比没结果好。LLM 编的答案即使不完美，关键词（"gs_ctl build"、"WAL"、"网络"）大概率是对的——这些词足够让向量检索命中正确的文档区域。

---

## Q5：查询改写和 HyDE 的区别？什么时候用哪个？

**答**：

| | HyDE | 查询改写 |
|---|---|---|
| 策略 | LLM 编一个答案 → 单次重检索 | LLM 拆 3 个子问题 → 分别检索 → 合并 |
| 适用 | 问题太短、术语不规范 | 问题太宽泛、隐含多个子问题 |
| 举例 | "备机重建失败怎么办" → 编答案 | "数据库性能下降" → 拆成 "慢 SQL 怎么查" + "连接数正常吗" + "缓存命中率多少" |
| 代价 | 多一次 LLM 调用 + 多一次检索 | 多一次 LLM 调用 + 三次检索 |

**执行顺序**：先 HyDE，HyDE 也不行才查询改写。因为 HyDE 成本更低（一次检索），查询改写是最后手段（三次检索）。

```python
# data_transformer.py 的降级逻辑
retriever_results = await search(query)  # 混合检索

if not retriever_results:
    hyde_results = await hyde_search(query)  # HyDE 降级
    if not hyde_results:
        query_transform_results = await query_transform_search(query)  # 查询改写降级
```

---

## Q6：提示模板体系怎么设计的？有哪些模板？

**答**：所有模板在 `utils/prompt_util.py`，中英文双语，按场景分 6 类：

| 模板 | 用途 | 核心指令 |
|------|------|---------|
| `INFER_SYSTEM_TMPL` | 主 QA 回答 | "判断参考资料是否相关 → 如果相关，基于资料回答 → 如果不相关，说明无法回答" |
| `HYDE_SYSTEM_TMPL` | 假设文档生成 | "请生成一段可能包含答案的说明文字" |
| `QUERY_TRANSFORM_SYSTEM_TMPL` | 查询改写 | "将原始问题拆分为 3 个独立的子问题" |
| `MULTI_QUERY_SYSTEM_TMPL` | 多视角查询 | "从不同角度表述同一个问题" |
| `QUERY_ROUTER_SYSTEM_TMPL` | 意图分类 | "判断问题是 GaussDB 相关、敏感内容、还是无关问题" |
| `DOCUMENT_COMPRESS_SYSTEM_TMPL` | 文档压缩 | "提取文档中与问题相关的关键信息" |

**设计原则**：
1. **双语**：根据 `Accept-Language` 请求头自动切换中英文模板
2. **约束明确**：每个模板都明确告诉 LLM "什么该做、什么不该做"
3. **防幻觉**：主模板明确要求 "如果资料不能回答，就说不能回答"——防止 LLM 自由发挥

---

## Q7：为什么支持 6 种模型？包装器怎么做的？

**答**：银行客户有各自的模型采购策略，不能只绑一个模型。

**架构**：

```
                    ┌─────────────────┐
                    │   BaseLLM (ABC)  │
                    │  invoke(prompt)  │
                    └────────┬────────┘
                             │
        ┌────────┬───────────┼───────────┬──────────┐
        ▼        ▼           ▼           ▼          ▼
    ┌──────┐ ┌──────┐ ┌─────────┐ ┌──────┐ ┌──────────┐
    │Pangu │ │Pangu │ │ChatGLM3 │ │Baich │ │Llama3    │
    │      │ │Cloud │ │         │ │uan   │ │          │
    └──────┘ └──────┘ └─────────┘ └──────┘ └──────────┘

    盘古/盘古云走 LLM 类路径（有 function_call）
    DeepSeek/Qwen 走通用 HTTP 路径（无 function_call，用提示工程）
```

**两类调用路径**：

| 路径 | 场景 | 模型 | 怎么用 |
|------|------|------|--------|
| LLM 类路径 `llm.invoke()` | 工具调用（需要 function_call 字段） | 盘古、盘古云、ChatGLM3、百川、Llama3 | 通过 `llm_registry.get(model_type)` 实例化适配器 |
| 通用 HTTP 路径 `generate_answer()` | RAG 问答（只需要文本） | DeepSeek、Qwen | 直接 POST 到 `/chat/completions` |

**为什么分两条路径**：工具调用阶段需要 LLM 输出结构化的工具名和参数。盘古原生支持 `function_call` 字段，直接解析。ChatGLM3/百川/Llama3 不支持——但通过提示工程约束输出格式（"请只输出工具名"），也能达到同样效果。DeepSeek/Qwen 的 API 是 OpenAI 兼容的，走通用 HTTP 路径更简单。

**面试必背**：6 种模型通过 Registry 模式统一管理，换模型只需改配置文件的 `api_type` 字段，不改业务代码。

---

## Q8：DeepSeek 和盘古走的是同一条调用路径吗？

**答**：不是。

```
盘古（工具调用场景）:
  llm_registry.get('Pangu') → Pangu.invoke(prompt)
    → POST 盘古 API
    → 解析响应中的 function_call 字段
    → 返回 (content, function_call_dict)

DeepSeek（RAG 场景）:
  generate_answer(messages, model_name)
    → POST https://api.deepseek.com/chat/completions
    → SSE 流式解析
    → yield chunk by chunk
```

盘古走 LLM 注册表 + 适配器类，因为需要解析盘古专有的 `function_call` 返回格式。DeepSeek 的 API 是标准 OpenAI 格式，不需要专有适配器——直接 HTTP POST + SSE 解析就够了。

**为什么不做统一抽象**：一开始只有盘古，做了 BaseLLM + Registry。后来加 DeepSeek 时发现它的 API 和盘古完全不同——盘古有独立的 function_call 字段，DeepSeek 没有；盘古返回格式不同。强行统一反而增加适配复杂度。两条路径各管各的，清晰简单。

---

## Q9：和 LangChain RAG 的核心差异是什么？

**答**：

| | LangChain | GaussMaster |
|---|---|---|
| 检索器 | `EnsembleRetriever` + RRF（多路融合，需独立部署各引擎） | 自研 `BaseRetriever`（openGauss 单表双路，不跨系统） |
| 向量存储 | Chroma / Pinecone / Milvus（独立部署） | openGauss（GSDiskANN，和 BM25 同表） |
| 嵌入 | OpenAI / HuggingFace | 自研 `OnlineEmbedding` HTTP 服务 |
| 分块 | `RecursiveCharacterTextSplitter`（固定 500） | 自研 DNN 语义分块（变长、保护代码/表格） |
| 重排序 | `ContextualCompressionRetriever` | 自研 `OnlineReranker` + score < 0 过滤 |
| 降级 | `MultiQueryRetriever`（多角度查询） | HyDE + 查询改写（两级） |
| 安全 | 无 | DFA + XLNet 双层 |
| 代码量 | 20 行配置搞定 | 全部自研，全程可控 |

**核心差异一句话**：LangChain 是通用框架，做混合检索用 EnsembleRetriever 没问题。但 GaussMaster 的场景不是在框架上搭积木——检索的底层存储是 openGauss 自身，向量和 BM25 同表、同操作符 `<->` 和 `###`。一旦用了这些原生能力，LangChain 的抽象层反而变成负担，不如自研直接调 psycopg2 来得干净。

---

## Q10：SSE 流式输出怎么实现的？

**答**：两层 stream。

```
LLM API 层（后端 ← LLM）:
  POST /chat/completions
  headers: { stream: true }
  → 逐 token 收

HTTP 传输层（后端 → 浏览器）:
  FastAPI StreamingResponse
  media_type="text/event-stream"
  headers: "Cache-Control: no-cache", "Connection: keep-alive"
  → 逐 chunk 推
```

**为什么两层缺一不可**：
- 只有 LLM 的 `stream=true` 而不用 `StreamingResponse` → FastAPI 等全部 token 收完才一次返回，用户等 5 秒看到空白
- 只有 `StreamingResponse` 而 LLM 不设 `stream=true` → 传输层能推，但 LLM 一次给完，没有 token 可推

**对应代码**：

```python
# data_transformer.py
async def generate_answer(messages, model_name):
    url = global_vars.llm_config.get(model_name).get('api_url')
    params = {'messages': messages, 'stream': True}
    
    llm_generator = await thread_request_from_llm(url, headers, params)
    for chunk in llm_generator:
        yield chunk  # 每个 token 立即 yield，不攒
```

---

## Q11：RAG 和 Agent 怎么切换？意图路由在哪一层？

**答**：**不做自动路由。** 这是和 Demo 最大的区别。

原项目暴露两个独立端点：

```
POST /v1/api/ask_gauss                   → ask_gauss() → RAG 管道
POST /v1/api/app/intelligent-interaction → DBA.interact_with_tool() → Agent 管道
```

```
前端 UI:
┌─────────────────────────────────────┐
│  GaussMaster                        │
│                                     │
│  [知识问答] → /v1/api/ask_gauss     │  ← 用户点这个就走 RAG
│  [故障诊断] → /v1/api/app/          │  ← 用户点这个就走 Agent
│              intelligent-interaction │
└─────────────────────────────────────┘
```

**为什么不做自动路由**：

银行场景下，操作者必须自己明确意图。"CPU 过高怎么办" 可能是想问知识（查文档），也可能是想诊断（调工具）——后端猜错了会调错管道。前端 UI 已经区分了 "问答" 和 "诊断" 两个入口，让操作者自己选，后端不猜。

**QUERY_ROUTER_SYSTEM_TMPL 不是路由用的**：

那个模板的职责是**安全/相关性分类**，只在 RAG 管道内部用：

```
QUERY_ROUTER 分类:
  → "GaussDB 相关"  → 放行
  → "敏感内容"      → 拦截
  → "无关问题"      → 提示超出范围
```

它管的是 "该不该回答"，不管 "走哪条管道"。Agent 管道根本不经过这个模板。

**Demo 为什么加了自动路由**：

Demo 没有前端 UI，只有一个 curl 入口，用户所有问题都打 `/ask`。所以我在 `main.py` 里用关键词 `is_tool_query()` 做了自动分发——这是 Demo 的妥协方案，生产环境靠前端分开入口比后端猜意图更可靠。

---

## Q12：怎么评估 RAG 回答质量？

**答**：三个维度，银行真实数据验证。

**1. 检索质量**：
- Recall@3：正确答案在前 3 个检索结果中的比例 → 目标 85%+
- MRR：正确答案的平均排名倒数

**2. 回答质量**：
- 银行提供 400+ 标注 QA 对，人工评为"高质量 / 可接受 / 低质量"
- 高质量率 = 85.23%（高质量 + 可接受 / 总数）

**3. 安全指标**：
- 误拦截率：正常问题被安全模块挡住的比例 → 目标 < 1%
- 漏拦截率：危险问题穿透安全模块的比例 → 目标 0%

**落地效果**：34 个运维场景覆盖，零人工干预，银行 DBA 从 3-6 个月上手周期缩短到即问即答。
