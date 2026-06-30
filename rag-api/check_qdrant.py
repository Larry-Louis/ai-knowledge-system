from infrastructure.vector.qdrant_store import QdrantStore
q = QdrantStore()
info = q.client.get_collection(q.collection)
print("Total points:", info.points_count)
r = q.client.scroll(q.collection, limit=20, with_payload=True)
for p in r[0]:
    pl = p.payload
    print(f"  [{pl['type']}] session={str(pl['session_id'])[:12]} {pl['content'][:60]}")
