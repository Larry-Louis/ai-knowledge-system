DEFAULT_SYSTEM_PROMPT = """你是一个长期世界构建AI（小说/游戏设计助手）。
你必须保证设定一致性，维护世界观、角色和剧情的连贯性。
每次回答都要基于已有的世界观信息，并自然地延续设定。"""


def build_prompt(
    request_messages: list[dict],
    world_summary: str | None = None,
    related_memories: list[dict] | None = None,
    document_chunks: list[dict] | None = None,
) -> list[dict]:
    system_msg = None
    other_messages = []
    for m in request_messages:
        if m["role"] == "system" and system_msg is None:
            system_msg = m["content"]
        else:
            other_messages.append(m)

    system_content = system_msg or DEFAULT_SYSTEM_PROMPT

    final_messages = [
        {"role": "system", "content": _build_system_content(system_content, world_summary, related_memories, document_chunks)}
    ]

    final_messages.extend(other_messages)
    return final_messages


def _build_system_content(base: str, world_summary: str | None, related_memories: list[dict] | None, document_chunks: list[dict] | None = None) -> str:
    parts = [base]

    if world_summary:
        parts.append(f"\n\n[当前世界观摘要]\n{world_summary}")

    if related_memories:
        memory_lines = []
        for m in related_memories:
            label = "用户" if m["role"] == "user" else "AI助手"
            memory_lines.append(f"[{label}]: {m['content']}")
        parts.append("\n\n[相关历史记忆]\n" + "\n".join(memory_lines))

    if document_chunks:
        doc_lines = []
        for d in document_chunks:
            doc_lines.append(f"[来自《{d['doc_title']}》第{d['chapter']}章 {d['title']}]: {d['content'][:800]}")
        parts.append("\n\n[文档参考]\n" + "\n".join(doc_lines))

    return "\n".join(parts)
