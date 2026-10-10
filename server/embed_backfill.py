# embed_backfill.py — 存量笔记一次性向量回填（向量 RAG 切片）
#
# 用途：切换到向量检索后，为 knowledge.json 里已有的笔记补建向量。
#
# 设计要点：
#   1. 走 embeddings 的 sha1 缓存 —— 重复执行不重复计费（幂等）；
#   2. 只补「向量库里没有的笔记」：先查向量库已有 note_id 集合，
#      避免每次回填都全量重算（除非 --force）；
#   3. chromadb 未装 / 无 key 时明确报错退出（这是显式运维命令，
#      不像导入接口那样静默降级）；
#   4. 零副作用核对：默认 --dry-run 只打印将回填多少条，--apply 才落库。
#
# 用法（仓库根目录）：
#     python server/embed_backfill.py            # 预览
#     python server/embed_backfill.py --apply    # 实际回填
#     python server/embed_backfill.py --apply --force   # 忽略缓存全量重算

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "vendor", "study-liu"))
sys.path.insert(0, HERE)


def existing_vector_ids(vector_store):
    """向量库里已有哪些 note_id（用于增量回填）。"""
    coll = vector_store._collection()
    if coll is None:
        return set()
    try:
        got = coll.get(include=["metadatas"])
        return {int(m.get("note_id", 0)) for m in (got.get("metadatas") or [])}
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser(description="存量笔记向量回填")
    ap.add_argument("--apply", action="store_true", help="实际写入（默认只预览）")
    ap.add_argument("--force", action="store_true",
                    help="忽略向量库已有记录，全量重算（仍走 embed 缓存）")
    args = ap.parse_args()

    import embeddings
    import vector_store
    from tools.knowledge_store import KnowledgeStore

    if not vector_store.AVAILABLE:
        print("[x] chromadb 未安装（pip3 install chromadb），回填中止")
        return 2
    if not embeddings._api_key():
        print("[x] 未配置 API Key（settings.json / LLM_API_KEY），回填中止")
        return 2

    store = KnowledgeStore()
    notes = store.list_all()
    if not notes:
        print("[!] 知识库为空，无需回填")
        return 0

    have = set() if args.force else existing_vector_ids(vector_store)
    todo = [n for n in notes if int(n.get("id", 0)) not in have]
    print("知识库 %d 条；向量库已有 %d 条；待回填 %d 条%s" % (
        len(notes), len(have), len(todo), "（--force 全量）" if args.force else ""))
    if not todo:
        print("[ok] 全部已有向量，无需回填")
        return 0
    for n in todo[:10]:
        print("  · #%d %s" % (n.get("id"), n.get("title")))
    if len(todo) > 10:
        print("  … 其余 %d 条略" % (len(todo) - 10))

    if not args.apply:
        print("[预览] 加 --apply 实际写入。"
              "首次执行会调百炼 embedding（免费额度内），缓存后重复执行不计费。")
        return 0

    done = failed = 0
    # 每批 10 条（百炼单请求上限），批间无重叠
    BATCH = 10
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        texts = ["%s\n%s" % (n.get("title") or "", n.get("content") or "")
                 for n in batch]
        vecs = embeddings.embed_texts(texts)
        if vecs is None:
            print("[x] 第 %d 批向量化失败（无 key / 断网 / 余额不足），中止。" % (i // BATCH + 1))
            break
        for n, vec in zip(batch, vecs):
            if not vec:
                failed += 1
                continue
            okw = vector_store.upsert_chunk(
                int(n["id"]), 0, n.get("title", ""), vec,
                owner=str(n.get("owner") or ""),
                scope=n.get("scope") or "public",
                category=str(n.get("category") or ""))
            done += 1 if okw else 0
            failed += 0 if okw else 1
        print("  批 %d/%d 完成" % (i // BATCH + 1, (len(todo) + BATCH - 1) // BATCH))

    print("[done] 成功 %d 条，失败 %d 条" % (done, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
