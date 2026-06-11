# GaussMaster 部署配置详解

## 1. 前置依赖服务

| 服务 | 作用 | 说明 |
|------|------|------|
| **DBMind** | 数据库管理 | openGauss 的运维服务 |
| **向量数据库** | 存储知识片段 | 如 Milvus、Pinecone 等 |
| **Embedding 服务** | 文本向量化 | 将用户提问转为向量 |
| **Reranking 服务** | 结果排序 | 对检索到的知识排序 |
| **大模型推理服务** | 智能决策 | 支持盘古、Chatglm3、Baichuan2、Llama3、Qwen、DeepSeek |

---

## 2. 配置文件

### 2.1 首先生成配置文件

```bash
python startup.py service setup -c conf
```

### 2.2 编辑 `conf/gauss_master.conf`

```ini
[VECTOR]
# 向量数据库地址、数据库名、用户名、密码

[DBMIND]
# DBMind 服务地址（当前仅支持 HTTP）

[WEB-SERVICE]
# GaussMaster Web 服务地址
ssl = false
```

### 2.3 编辑 `conf/model_config.yaml`

```yaml
# default llm
model_name: pangu_sigma_unify_plugin_71b

# 大模型配置
online_llm:
  pangu_sigma_unify_plugin_71b:
    enable: True
    model_name: pangu_sigma_unify_plugin_71b
    api_type: Pangu
    api_url: http://*.*.*.*:*/chat/completions
    recommended_config:
      temperature: 0.7
      top_p: 1.0

# embedding model
embedding_model:
  api_url: xxx
  model_path: xxx
```

---

## 3. 初始化并启动

### 3.1 初始化（加密密码 + 向量化知识库）

```bash
echo '{"VECTOR_password": "x", "DBMIND_password": "x"}' | \
python startup.py service setup -c conf --initialize --initialize_meta_db
```

### 3.2 启动服务

```bash
python startup.py service start -c conf
```

---

## 4. 前台 UI 部署（可选）

### 4.1 配置后台地址

**文件：** `ui.env.development`
```bash
VITE_BASE_PROXY_URL = http://x.x.x.x:x
```

### 4.2 配置前台 IP/Host

**文件：** `ui/vite.config.ts`

### 4.3 启动前台

```bash
cd ui
npm install
npm run dev
```

---

## 5. 快速验证

调用智能问答接口测试：

```bash
curl -X 'POST' "<gaussmaster_endpoint>/v1/api/ask_gauss" \
  -H 'accept: text/event-stream' \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "123",
    "session_id": "123",
    "model_name": "pangu_cloud_sigma_unify_plugin_38b",
    "lang": "zh",
    "history_len": 3
  }'
```

---

## 6. 总结：必须配置的核心项

| 优先级 | 组件 | 说明 |
|--------|------|------|
| 1 | **DBMind 服务地址** | 数据库运维接口 |
| 2 | **向量数据库连接** | 存储和检索知识 |
| 3 | **大模型 API** | 盘古/Chatglm 等 |
| 4 | **Embedding 模型** | 文本向量化 |
| 5 | **Reranking 模型**（可选） | 结果排序 |

---

## 7. 成本估算

### 轻量级（学习/测试用）

| 组件 | 推荐方案 | 成本 |
|------|----------|------|
| **openGauss** | 本地安装 | ¥0 |
| **向量数据库** | Docker Milvus | ¥0 |
| **大模型 API** | 硅基流动 / DeepSeek | ¥50-200/月 |
| **总成本** | | **¥50-200/月** |

### 生产级

| 组件 | 推荐方案 | 成本 |
|------|----------|------|
| **openGauss** | 云厂商托管 | ¥300-2000/月 |
| **向量数据库** | 阿里云 Milvus | ¥200-1000/月 |
| **大模型 API** | 华为盘古 / DeepSeek | ¥200-2000/月 |
| **总成本** | | **¥1000-5000/月** |
