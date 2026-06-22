"""
RAG 问答引擎
对标 GaussMaster 的 ask_gauss 流程
"""

import logging
from typing import AsyncGenerator, Optional

from core.memory import MemoryManager, QARecord
from knowledge.vector_store import kb_store
from llms.base import BaseLLM
from prompts.rag import QA_SYSTEM_PROMPT_ZH, QA_PROMPT_ZH


class RAGEngine:
    """
    RAG 问答引擎

    流程:
    1. 接收用户问题
    2. 向量检索知识库
    3. 构建 Prompt（上下文 + 历史 + 问题）
    4. LLM 生成回答
    5. 保存到记忆
    """

    def __init__(
        self,
        llm: BaseLLM,
        embedder=None,
        memory_mgr: Optional[MemoryManager] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
    ):
        self.llm = llm
        self.embedder = embedder  # 嵌入模型（可为 None，不传则跳过向量检索）
        self.memory_mgr = memory_mgr
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold

    async def ask(
        self,
        question: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> AsyncGenerator[dict, None]:
        """
        执行 RAG 问答
        yield 格式: {"type": "progress"|"result"|"error", "content": ...}
        """
        yield {"type": "progress", "content": "正在检索知识库..."}

        # ── Step 1: 向量检索 ──
        context_docs = self._retrieve(question)

        context = ""
        if context_docs:
            context = "\n\n".join([
                f"[相关{document.get('score', 0):.2f}] {doc['text']}"
                for doc in context_docs
            ])
            yield {"type": "progress", "content": f"检索到 {len(context_docs)} 条相关文档"}
        else:
            yield {"type": "progress", "content": "知识库中未检索到相关文档，将直接回答"}

        # ── Step 2: 构建历史 ──
        history = ""
        if self.memory_mgr:
            session = self.memory_mgr.get_session(user_id, session_id)
            history = session.build_context()

        # ── Step 3: 构建 Prompt 并调用 LLM ──
        yield {"type": "progress", "content": "正在生成回答..."}

        system_prompt = QA_SYSTEM_PROMPT_ZH.format(
            context=context if context else "（暂无相关参考文档）",
            history=history if history else "（暂无历史对话）",
        )
        user_prompt = QA_PROMPT_ZH.format(question=question)

        answer = await self.llm.chat_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # ── Step 4: 保存到记忆 ──
        if self.memory_mgr:
            session = self.memory_mgr.get_session(user_id, session_id)
            session.add_record(QARecord(question=question, answer=answer))

        yield {
            "type": "result",
            "content": answer,
            "source_docs": context_docs if context_docs else [],
        }

    def _retrieve(self, question: str) -> list[dict]:
        """检索知识库"""
        if kb_store.count() == 0:
            logging.warning("知识库为空，无法检索")
            return []

        embedding = None
        if self.embedder:
            try:
                embedding = self.embedder(question)
            except Exception as e:
                logging.error(f"嵌入计算失败: {e}")
                return []

        if embedding is not None:
            return kb_store.search(
                query_embedding=embedding,
                top_k=self.top_k,
                threshold=self.similarity_threshold,
            )

        # 没有嵌入模型，走简单关键词匹配（仅当知识库较小时可用）
        results = []
        question_lower = question.lower()
        for doc in kb_store.documents:
            score = self._keyword_score(question_lower, doc["text"].lower())
            if score > 0:
                results.append({
                    "text": doc["text"],
                    "metadata": doc["metadata"],
                    "score": score,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:self.top_k]

    @staticmethod
    def _keyword_score(query: str, text: str) -> float:
        """简单关键词匹配得分"""
        words = set(query.split())
        if not words:
            return 0.0
        matches = sum(1 for w in words if w in text)
        return matches / len(words)
