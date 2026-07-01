from infrastructure.config.config import Config

DEFAULT_SYSTEM_PROMPT = Config.SYSTEM_PROMPT


def build_prompt(
    request_messages: list[dict],
    overall_summary: str | None = None,
    related_memories: list[dict] | None = None,
    document_chunks: list[dict] | None = None,
    user_profile: dict | None = None,
) -> list[dict]:
    """
    [S0-8] 构建 RAG 提示

    主要工作流：
    1. 从请求消息中提取系统提示（如果有），否则使用默认系统提示
    2. 调用 _build_system_content 将对话摘要、相关记忆、文档片段附加到系统提示中
    3. 将其他用户/助手消息按原样添加到最终消息列表中
    4. 返回完整的消息列表供 LLM 调用
    """
    system_msg = None
    other_messages = []
    for m in request_messages:
        if m["role"] == "system" and system_msg is None:
            system_msg = m["content"]
        else:
            other_messages.append(m)

    system_content = system_msg or DEFAULT_SYSTEM_PROMPT

    final_messages = [
        {"role": "system", "content": _build_system_content(system_content, overall_summary, related_memories, document_chunks, user_profile)}
    ]

    final_messages.extend(other_messages)
    return final_messages


def _build_system_content(base: str, overall_summary: str | None, related_memories: list[dict] | None, document_chunks: list[dict] | None = None, user_profile: dict | None = None) -> str:
    parts = [base]

    if overall_summary:
        parts.append(f"\n\n[当前对话摘要]\n{overall_summary}")

    if related_memories:
        memory_lines = []
        for m in related_memories:
            label = "用户" if m["role"] == "user" else "AI助手"
            memory_lines.append(f"[{label}]: {m['content'][:500]}")
        parts.append("\n\n[相关历史记忆]\n" + "\n".join(memory_lines))

    if user_profile:
        profile_lines = []
        categories = user_profile.get("categories", {}) if isinstance(user_profile, dict) else {}
        for category, items in categories.items():
            if not items:
                continue
            label = category
            item_lines = []
            for item in items[:4]:
                content = item.get("content", "")
                confidence = item.get("confidence", 0.0)
                item_lines.append(f"- {content[:200]} (confidence={confidence:.2f})")
            profile_lines.append(f"[{label}]\n" + "\n".join(item_lines))
        if profile_lines:
            parts.append("\n\n[用户画像]\n" + "\n\n".join(profile_lines))

    # 只包含相似度足够高的文档片段（score ≥ 0.65）
    relevant_docs = [d for d in (document_chunks or []) if d.get("score", 0) >= 0.65]
    if relevant_docs:
        doc_lines = []
        for d in relevant_docs:
            doc_lines.append(f"[来自《{d['doc_title']}》第{d['chapter']}章 {d['title']}]: {d['content'][:800]}")
        parts.append("\n\n[文档参考]\n" + "\n".join(doc_lines))

    return "\n".join(parts)