# Phase 1 Production Spec 鈥?Memory Admission System (v2.0)

Date: 2026-06-06

> 鏈枃妗ｆ弿杩板綋鍓?*瀹為檯瀹炵幇**鐨勫畬鏁村鐞嗛摼璺紝鍩轰簬浠ｇ爜鑰岄潪璁捐鏂囨。銆?
---

# 馃幆 绯荤粺鎬绘灦鏋勶細鍙岄樁娈佃蹇嗙閬?
鏁翠釜绯荤粺鍒嗕负 **涓や釜闃舵** 澶勭悊璁板繂锛?
| 闃舵 | 鍚嶇О | 鍚屾/寮傛 | 璺緞 | 鍐欏叆绫诲瀷 |
|------|------|-----------|------|----------|
| **闃舵 0** | 鍚屾璁板繂閫氶亾 | 鍚屾锛堣姹傝矾寰勫唴锛?| HTTP 鈫?LLM 鈫?Qdrant | `type=memory` |
| **闃舵 1** | 寮傛璁板繂绠￠亾 | 寮傛锛堝悗鍙扮嚎绋嬶級 | SQLite Queue 鈫?SLM 鈫?Qdrant | `type=memory_unit` |

---

# 闃舵 0 鈥?鍚屾閾捐矾锛堣姹傝矾寰勶級

## 鏁版嵁娴佹€昏

```
POST /v1/chat/completions
  鈹?  鈹溾攢 [S0-1]  API 鍏ュ彛瑙ｆ瀽                    api/chat.py:73
  鈹?  鈹溾攢 [S0-2]  浼氳瘽 ID 鎺ㄥ                    core/memory.py:58
  鈹?  鈹溾攢 [S0-3]  鐢ㄦ埛娑堟伅鍚戦噺鍖?                  services/embedding.py:7
  鈹?  鈹溾攢 [S0-4]  涓夐噸璁板繂妫€绱?                    services/qdrant_store.py
  鈹?  鈹溾攢 [S0-5]  璁板繂鍚堝苟鍘婚噸                     core/memory.py:39
  鈹?  鈹溾攢 [S0-6]  鎽樿妫€绱?+ 鏂囨。妫€绱?              services/qdrant_store.py
  鈹?  鈹溾攢 [S0-7]  鏍稿績鍐欏叆瑙﹀彂锛堝彲閫夛級              core/memory.py:107
  鈹?  鈹溾攢 [S0-8]  鏋勫缓 RAG 鎻愮ず                    core/prompt.py:6
  鈹?  鈹溾攢 [S0-9]  LLM 璋冪敤                         core/llm.py
  鈹?  鈹溾攢 [S0-10] 鍚屾鍐欏叆锛氱敤鎴锋秷鎭?鈫?Qdrant      core/memory.py:143
  鈹?  鈹溾攢 [S0-11] 鍚屾鍐欏叆锛欰I鍝嶅簲 鈫?Qdrant        core/memory.py:151
  鈹?  鈹溾攢 [S0-12] 鎻愪氦寮傛绠￠亾浠诲姟                  memory_pipeline.py:53
  鈹?  鈹溾攢 [S0-13] 鏉′欢鎬ф憳瑕佺敓鎴?                   core/memory.py:164
  鈹?  鈹斺攢 HTTP 200
```

## 鍚勬楠よ瑙?
### [S0-1] API 鍏ュ彛瑙ｆ瀽 鈥?`api/chat.py:73`

**鍑芥暟锛?* `chat_completions()`

- 鎺ユ敹 `POST /v1/chat/completions` 璇锋眰锛岃В鏋?`ChatCompletionRequest`
- 瑙ｆ瀽 `model` 瀛楁纭畾瑙掕壊灞傦紙`story` / `general` / `core`锛夛細
  - `model: "story"` 鈫?璁剧疆娲昏穬瑙掕壊涓?`story`
  - `model: "core"` 鈫?寮€鍚牳蹇冨啓鍏ユā寮忥紙Core Write Mode锛?  - `model: "deepseek-v4-flash:story"` 鈫?鍚屾椂璁剧疆妯″瀷鍜岃鑹?- 璋冪敤 `MemoryManager.process_request()` 杩涜鏍稿績澶勭悊
- 鏋勫缓 `ChatCompletionResponse` 杩斿洖锛堟敮鎸佹祦寮?闈炴祦寮忥級

### [S0-2] 浼氳瘽 ID 鎺ㄥ 鈥?`core/memory.py:58`

**鍑芥暟锛?* `_derive_session_id()`

- 濡傛灉璇锋眰鏈惡甯?`session_id`锛屼粠绗竴鏉＄敤鎴锋秷鎭唴瀹硅绠?MD5 鍝堝笇
- 鏍煎紡锛歚"s-" + md5(content)[:16]`
- 淇濊瘉鍚屼竴鐢ㄦ埛鐨勫悓涓€杞璇濅骇鐢熺ǔ瀹?ID

### [S0-3] 鐢ㄦ埛娑堟伅鍚戦噺鍖?鈥?`services/embedding.py:7`

**鍑芥暟锛?* `EmbeddingService.embed()`

- 鍙栧嚭鏈€鍚庝竴鏉＄敤鎴锋秷鎭紝璋冪敤 Ollama `/api/embed` 鎺ュ彛
- 妯″瀷锛歚nomic-embed-text`锛岃緭鍑?768 缁村悜閲?- 杩欐潯 embedding 灏嗙敤浜庡悗缁墍鏈夊悜閲忔绱?
### [S0-4] 涓夐噸璁板繂妫€绱?鈥?`services/qdrant_store.py`

绯荤粺鍦?LLM 璋冪敤鍓嶆墽琛?**涓夌骞惰鏌ヨ**锛?
| 鏌ヨ | 鍑芥暟 | 琛屽彿 | 鍙傛暟 |
|------|------|------|------|
| 浼氳瘽璁板繂 | `search_memories()` | 73 | 浠呭綋鍓?`session_id`锛宍type=memory`锛宼op_k=8 |
| 鍏ㄥ眬璁板繂 | `search_global_memories()` | 100 | 鎸?`layer IN [core, active_role]` 杩囨护锛宼op_k=6锛宑ore 灞?脳1.05 |
| 杩戞湡璺ㄤ細璇?| `get_recent_global_memories()` | 127 | **浠呮柊浼氳瘽瑙﹀彂**锛屾帓闄ゅ綋鍓?`session_id`锛屾瘡瑙掕壊灞傛渶澶?2 鏉?|

**鎼滅储灞傦紙layer锛夌瓥鐣ワ細**
- 濮嬬粓鍖呭惈 `core` 灞傦紙鏍稿績璁板繂濮嬬粓鍙绱級
- 鍔犱笂褰撳墠娲昏穬瑙掕壊灞傦紙`story` / `general` 绛夛級
- 濡傛灉娲昏穬灞備篃鏄?`core`锛屼笉閲嶅娣诲姞

### [S0-5] 璁板繂鍚堝苟鍘婚噸 鈥?`core/memory.py:39`

**鍑芥暟锛?* `_merge_memories()`

- 鍚堝苟涓夋妫€绱㈢粨鏋滐紙浼氳瘽璁板繂 + 鍏ㄥ眬璁板繂 + 璺ㄤ細璇濊蹇嗭級
- 鎸夊唴瀹瑰墠 100 瀛楃鍘婚噸锛坄seen` set锛?- 鎴彇鏈€澶?**12 鏉?*璁板繂閫佸叆 prompt

### [S0-6] 鎽樿妫€绱?+ 鏂囨。妫€绱?鈥?`services/qdrant_store.py`

**鎽樿妫€绱細** `get_summary()` (琛?191)
- 婊氬姩鏌ヨ `type=summary` 鐨勬渶鏂拌褰?- 杩斿洖褰撳墠涓栫晫瑙傛憳瑕佹枃鏈垨 None

**鏂囨。妫€绱細** `search_documents()` (琛?166)
- 鑾峰彇褰撳墠娲昏穬鏂囨。 ID 鍒楄〃锛堥€氳繃 `/documents/active` 绔偣璁剧疆锛?- 鍦?`documents` 闆嗗悎涓悳绱紝浠呴檺娲昏穬 `doc_id`
- top_k=4锛屽垎鏁伴槇鍊?0.65

### [S0-7] 鏍稿績鍐欏叆瑙﹀彂锛堝彲閫夛級鈥?`core/memory.py:107`

浠呭湪 **Core Write Mode** 寮€鍚椂瑙﹀彂锛?- 妫€鏌ョ敤鎴锋秷鎭槸鍚﹀寘鍚?`CORE_TRIGGERS`锛坄"璁颁綇锛?` / `"瑕佽寰楋細"` / `"鍐欏叆鏍稿績锛?`锛?- 鍖归厤鍚庢彁鍙栬Е鍙戣瘝鍚庣殑鏂囨湰锛屽悜閲忓寲锛岀洿鎺ヤ互 `layer=core` 鍐欏叆 Qdrant
- 杩欐槸鐢ㄦ埛鏄惧紡鎺у埗闀挎湡璁板繂鐨勬満鍒?
### [S0-8] 鏋勫缓 RAG 鎻愮ず 鈥?`core/prompt.py:6`

**鍑芥暟锛?* `build_prompt()`

灏嗘绱㈠埌鐨勪笂涓嬫枃娉ㄥ叆绯荤粺娑堟伅锛岀粨鏋勪负锛?
```
[鍩虹绯荤粺鎻愮ず]
  + [褰撳墠涓栫晫瑙傛憳瑕乚      鈫?鏉ヨ嚜 S0-6
  + [鐩稿叧鍘嗗彶璁板繂]        鈫?鏉ヨ嚜 S0-5锛屾渶澶?12 鏉?  + [鏂囨。鍙傝€僝           鈫?鏉ヨ嚜 S0-6锛宻core 鈮?0.65
```

鏈€缁堜繚鐣欏師濮嬭姹備腑鐨勭敤鎴?鍔╂墜娑堟伅椤哄簭涓嶅彉銆?
### [S0-9] LLM 璋冪敤 鈥?`core/llm.py`

**鍑芥暟锛?* `LLMFactory.get().chat()`

- 鏍规嵁 `Config.LLM_PROVIDER` 閫夋嫨瀹㈡埛绔細Ollama / DeepSeek / OpenAI
- DeepSeek 瀹㈡埛绔澶栨彁鍙?reasoning_content 鍒?`last_reasoning` 瀛楁
- 杩斿洖 LLM 鐢熸垚鐨勬枃鏈搷搴?
### [S0-10] [S0-11] 鍚屾鍐欏叆 Qdrant 鈥?`core/memory.py:143,151`

LLM 杩斿洖鍚庯紝绔嬪嵆鍚屾鍐欏叆涓ゆ潯鍘熷璁板綍锛?
| 鏃跺簭 | 鍐呭 | type | 瑙掕壊灞?|
|------|------|------|--------|
| LLM 涔嬪悗 | 鐢ㄦ埛鏈€鍚庝竴鏉℃秷鎭?| `memory` | 褰撳墠娲昏穬瑙掕壊灞?|
| LLM 涔嬪悗 | AI 瀹屾暣鍝嶅簲 | `memory` | 褰撳墠娲昏穬瑙掕壊灞?|

**杩囨护锛?* `_is_auto_task()` (琛?10) 妫€娴?Open WebUI 鑷姩鐢熸垚鐨勪换鍔℃秷鎭苟璺宠繃
- 鐗瑰緛锛歚"### Task:"` 鍓嶇紑銆乣<chat_history>` 鏍囪銆佷粎鍚?`tags/title/follow_ups` 鐨?JSON

### [S0-12] 鎻愪氦寮傛绠￠亾浠诲姟 鈥?`memory_pipeline.py:53`

**鍑芥暟锛?* `submit_turn()`

- 鍒涘缓 `MemoryEvent`锛堢敤鎴锋秷鎭?+ 鍔╂墜娑堟伅 + session_id + 瑙掕壊灞傦級
- 璋冪敤 `PersistentQueue.enqueue()` 鍐欏叆 SQLite 琛?- **涓嶉樆濉?HTTP 鍝嶅簲杩斿洖**锛屽悗鍙板伐浣滅嚎绋嬫秷璐?
### [S0-13] 鏉′欢鎬ф憳瑕佺敓鎴?鈥?`core/memory.py:164`

**鍑芥暟锛?* `_generate_summary()`

- 瑙﹀彂鏉′欢锛氳浼氳瘽娑堟伅鎬绘暟鑳借 `(SUMMARY_INTERVAL 脳 2)` 鏁撮櫎
- 榛樿 `SUMMARY_INTERVAL=30` 鈫?姣?**60 鏉℃秷鎭?* 瑙﹀彂涓€娆?- 杩囩▼锛氭彁鍙栬繎鏈熸秷鎭?鈫?LLM 鍚堟垚鎽樿 鈫?鍚戦噺鍖?鈫?`save_summary()`
- `save_summary()` 鍏堝垹闄ゆ棫鎽樿鍐嶅啓鍏ユ柊鎽樿锛堝彧鏈変竴涓椿璺冩憳瑕侊級

---

## 闃舵 1 鈥?寮傛閾捐矾锛堝悗鍙扮閬擄級

### 鏁版嵁娴佹€昏

```
_worker() 瀹堟姢绾跨▼
  鈹? (妯″潡瀵煎叆鏃跺惎鍔? memory_pipeline.py:191)
  鈹?  鈹溾攢 [S1-1]  宕╂簝鎭㈠: recover_stale(30s)
  鈹?  鈹溾攢 [S1-2]  姣?0鍒嗛挓: cleanup(86400s)
  鈹?  鈹斺攢 杞寰幆 (姣?绉?
       鈹?       鈹溾攢 [S1-3]  PersistentQueue.dequeue(batch=1)
       鈹?    鈫?浠?SQLite 鍙栧嚭鏈€鏃╀竴鏉?pending 璁板綍
       鈹?    鈫?鏍囪涓?processing
       鈹?       鈹溾攢 [S1-4]  _process_turn(turn_data)
       鈹?       鈹溾攢 [S1-4a] 鎷兼帴瀵硅瘽鏂囨湰 "鐢ㄦ埛: ...\nAI鍔╂墜: ..."
       鈹?       鈹溾攢 [S1-4b] slm_validate(瀵硅瘽鏂囨湰)
       鈹?    鈫?璋冪敤 DeepSeek API锛圫LM 瑙掕壊锛?       鈹?    鈫?杈撳嚭缁撴瀯鍖?JSON: keep/importance/confidence/tier/type/tag/summaries
       鈹?    鈫?榛樿鎷掔粷绛栫暐锛氭棤鐢ㄦ埛浜嬪疄 鈫?keep=false
       鈹?       鈹溾攢 [S1-4c] DecisionMaker.classify_mu(SLM 缁撴灉)
       鈹?    鈫?鍐崇瓥鐭╅樀锛坕mportance 脳 confidence锛?       鈹?    鈫?杈撳嚭 store_priority: golden / review / low / drop
       鈹?       鈹溾攢 [S1-4d] 鍥為€€: extract_mus() 鈥?褰?SLM 鏃犳憳瑕佹椂
       鈹?    鈫?鍩轰簬瑙勫垯锛氭寜涓枃杩炶瘝/鏍囩偣鍒嗗壊
       鈹?       鈹斺攢 [S1-4e] _store_mu(姣忎釜鎽樿) 鈫?鏈€澶?3 涓?杞
             鈹溾攢 normalize() 鈫?鏈鏍囧噯鍖?             鈹溾攢 is_duplicate() 鈫?浣欏鸡鐩镐技搴?鈮?0.90 璺宠繃
             鈹溾攢 detect_polarity() 鈫?鏋佹€у啿绐?鈫?鏃ц鐩?             鈹斺攢 Qdrant.upsert() 鈫?type=memory_unit, 鍚畬鏁村厓鏁版嵁
       鈹?       鈹溾攢 mark_done() / mark_failed()
       鈹?       鈹斺攢 缁х画杞
```

## 鍚勬楠よ瑙?
### [S1-0] 鍚庡彴绾跨▼鍚姩 鈥?`memory_pipeline.py:191`

```python
_worker_thread = threading.Thread(target=_worker, daemon=True, name="memory-pipeline")
_worker_thread.start()
```

- 鍦ㄦā鍧楀鍏ユ椂鑷姩鍚姩锛坄from core.memory_pipeline import ...` 鍗宠Е鍙戯級
- **daemon=True**锛氫笉闃绘杩涚▼閫€鍑?- 鐙珛杩愯浜庝富 HTTP 璇锋眰绾跨▼涔嬪

### [S1-1] 宕╂簝鎭㈠ 鈥?`persistent_queue.py:109`

**鍑芥暟锛?* `recover_stale(timeout=30)`

- 鍚姩鏃惰嚜鍔ㄦ墽琛屼竴娆?- 鏌ユ壘 `status='processing'` 涓?`updated_at < now - 30s` 鐨勮褰?- 灏嗗叾閲嶇疆涓?`pending`锛屼娇瀹冧滑鑳借閲嶆柊娑堣垂
- 瑙ｅ喅鏈嶅姟宕╂簝鏃跺崱浣忕殑鍗婂鐞嗛」

### [S1-2] 瀹氭湡娓呯悊 鈥?`persistent_queue.py:127`

**鍑芥暟锛?* `cleanup(max_age=86400)`

- 姣?10 鍒嗛挓鎵ц涓€娆?- 鍒犻櫎 `status IN ('done', 'dead')` 涓旇秴杩?24 灏忔椂鐨勮褰?- 闃叉 SQLite 鏃犻檺澧為暱

### [S1-3] 鍑洪槦 鈥?`persistent_queue.py:65`

**鍑芥暟锛?* `dequeue(batch_size=1)`

- 鎸?`created_at ASC` 鍙栨渶鏃╃殑涓€鏉?`pending` 璁板綍
- 鍘熷瓙鎬у湴鏇存柊涓?`processing` 鐘舵€侊紙闃查噸澶嶆秷璐癸級
- 杩斿洖 `{id, data (dict), retries}`

### [S1-4] 鏍稿績澶勭悊 鈥?`memory_pipeline.py:160`

**鍑芥暟锛?* `_process_turn()`

杩欐槸鏁翠釜绠￠亾鏈€鍏抽敭鐨勭紪鎺掑嚱鏁般€備緷娆℃墽琛屼互涓嬪瓙姝ラ锛?
---

### [S1-4a] 鎷兼帴杞鏂囨湰

```python
turn_text = f"鐢ㄦ埛: {turn_data.get('user','')}\nAI鍔╂墜: {turn_data.get('assistant','')}"
```

- 灏嗘暣杞璇濓紙鐢ㄦ埛 + 鍔╂墜锛夋嫾鎺ヤ负涓€涓瓧绗︿覆
- 浜ょ敱 SLM 璇勪及鏄惁鍊煎緱璁板繂

---

### [S1-4b] SLM 楠岃瘉 鈥?`core/text_utils.py:68`

**鍑芥暟锛?* `slm_validate()`

杩欐槸绠￠亾鐨?*璇箟闂ㄦ帶**锛?
- 浣跨敤 DeepSeek 鎵紨 SLM锛圫mall Language Model锛夎鑹?- 璋冪敤 `SLM_PROMPT v3.0`锛坧rompt 绾?180 琛岋級
- 鍙傛暟锛歚temperature=0.1`锛堜綆闅忔満鎬э級锛宍max_tokens=300`

**SLM 杈撳嚭鏍煎紡锛?*

```json
{
  "keep": true,
  "importance": 0.85,
  "confidence": 0.75,
  "tier": "LONG",
  "type": "ENTITY",
  "tag": "identity",
  "summaries": ["鐢ㄦ埛浠庝簨AI寮€鍙?, "鐢ㄦ埛鎶€鏈爤鏄疨ython"]
}
```

**鏍稿績绛栫暐锛氶粯璁ゆ嫆缁濓紙Default Reject锛?*
- 闄ら潪鏄庣‘璇嗗埆鍑虹敤鎴疯韩浠?鍋忓ソ/椤圭洰/浠诲姟/缁忛獙
- AI 鐨勯€氱敤鐭ヨ瘑鍥炵瓟涓嶈繘鍏ラ暱鏈熻蹇?- 鐢ㄦ埛閮ㄥ垎鏉冮噸 1.0锛孉I 閮ㄥ垎鏉冮噸 0.6~0.8

**杈撳嚭瑙ｆ瀽锛?* `_safe_parse_json()` (琛?306)
- 鏀寔澶氱瀹归敊瑙ｆ瀽锛氱函 JSON銆乵arkdown fence 鍖呰９銆佹鍒欐彁鍙栥€佸叧閿瘝鍏滃簳

---

### [S1-4c] 鍐崇瓥鐭╅樀 鈥?`core/decision_maker.py:17`

**鍑芥暟锛?* `DecisionMaker.classify_mu()`

| 鏉′欢 | store_priority | 鍚箟 |
|------|---------------|------|
| importance 鈮?0.7 AND confidence 鈮?0.7 | `golden` | 榛勯噾璁板繂锛岀洿鎺ュ叆搴?|
| importance 鈮?0.7 AND confidence < 0.7 | `review` | 楂樹环鍊间絾浣庣疆淇★紝闇€澶嶆牳 |
| importance 鈮?0.4 AND < 0.7 | `low` | 浣庝紭鍏堢骇锛屽瓨浣嗕笉淇濊瘉鍙洖 |
| importance < 0.4 | `drop` | 涓㈠純 |

鍚屾椂鏄犲皠锛?- `type` 鈫?`mu_type`锛圗NTITY / RELATION / EVENT / TASK锛?- `tag` 鈫?`mu_tag`锛坕dentity / preference / project / fact / task / knowledge / noise锛?- `type` 鈫?`layer_type`锛圗NTITY/RELATION 鈫?semantic, EVENT/TASK 鈫?episodic锛?
---

### [S1-4d] 鍥為€€鎻愬彇 鈥?`core/text_utils.py:53`

**鍑芥暟锛?* `extract_mus()`

褰?SLM 鏈繑鍥?summaries 鏃剁殑鍏滃簳鏂规锛?- 鎸変腑鏂囪繛璇?鏍囩偣鍒嗗壊鐢ㄦ埛娑堟伅
- 妯″紡锛歚r'(?:骞朵笖|鑰屼笖|杩榺浠ュ強|鍚屾椂|锛寍銆倈锛泑銆?'`
- 鍙栧墠 5 涓€欓€夌墖娈碉紙闀垮害 > 4 瀛楃锛?
---

### [S1-4e] 瀛樺偍 Memory Unit 鈥?`memory_pipeline.py:90`

**鍑芥暟锛?* `_store_mu()`

姣忎釜鎽樿鏈€缁堥€氳繃鍥涙娓呮礂鍚庡啓鍏?Qdrant锛?
**鈶?鏍囧噯鍖栵細** `normalize()` (琛?362)
- 涓昏缁熶竴锛歚"鎴?` 鈫?`"鐢ㄦ埛"`锛宍"鎴戜滑"` 鈫?`"鐢ㄦ埛"`
- 鏈鏍囧噯鍖栵細澶у皬鍐欑粺涓€锛坅utosar鈫扐UTOSAR, rag鈫扲AG, python鈫扨ython 绛夛級
- 15 涓缃妧鏈悕璇嶆槧灏?
**鈶?鍘婚噸锛?* `is_duplicate()` (琛?410)
- 瀵瑰唴瀹瑰仛 embedding锛堣皟鐢?Ollama锛?- 鍦?Qdrant `memory_unit` 绫诲瀷涓悳绱?Top 5
- **浣欏鸡鐩镐技搴?鈮?0.90 鈫?瑙嗕负閲嶅锛岃烦杩囧瓨鍌?*

**鈶?鏋佹€у啿绐佹娴嬩笌瑙ｅ喅锛?* `detect_polarity()` (琛?392)
- 鍩轰簬鍏抽敭璇嶈鏁板垽鏂瀬鎬э細
  - 姝ｉ潰璇嶏細鍠滄銆佺埍銆佹敮鎸併€佹帹鑽?..
  - 璐熼潰璇嶏細涓嶅枩娆€佽鍘屻€佹嫆缁濄€佹棤娉?..
- 濡傛灉鏂板唴瀹规瀬鎬ч潪涓€э紝涓斿瓨鍦ㄨ涔夌浉浼硷紙score 鈮?0.80锛夌殑鏃х偣浣嗘瀬鎬х浉鍙?- **绛栫暐锛氭柊鏁版嵁瑕嗙洊鏃ф暟鎹?*锛堝垹闄ゆ棫鐐?+ 鍐欏叆鏂扮偣锛?
**鈶?鍐欏叆 Qdrant锛?* `PointStruct` 鍖呭惈瀹屾暣杞借嵎锛?
```json
{
  "id": "uuid",
  "vector": [768缁?embedding],
  "payload": {
    "content": "鐢ㄦ埛浠庝簨AI寮€鍙?,
    "type": "memory_unit",
    "mu_type": "ENTITY",
    "mu_tag": "identity",
    "layer_type": "semantic",
    "slm_version": "v3.0",
    "importance": 0.85,
    "confidence": 0.75,
    "store_priority": "golden",
    "layer": "story",
    "session_id": "s-abc123",
    "turn_id": "a1b2c3d4e5f6",
    "source_user": "鍘熺敤鎴锋秷鎭?鎴柇200瀛?",
    "source_assistant": "鍘烝I鍝嶅簲(鎴柇200瀛?",
    "timestamp": 1712345678.0
  }
}
```

### [S1-5] 鏍囪瀹屾垚/澶辫触 鈥?`persistent_queue.py:83,92`

- **鎴愬姛锛?* `mark_done()` 鈫?鐘舵€佹敼涓?`done`
- **澶辫触锛?* `mark_failed()` 鈫?`retries++`锛岃秴 3 娆″悗鐘舵€佸彉 `dead`锛屽惁鍒欓噸缃负 `pending` 绛夊緟閲嶈瘯

---

# 馃搳 涓や釜闃舵鐨勬暟鎹姣?
| 缁村害 | 闃舵 0锛堝悓姝ワ級 | 闃舵 1锛堝紓姝ワ級 |
|------|---------------|---------------|
| **Qdrant `type`** | `memory` | `memory_unit` |
| **鍐呭** | 鍘熷瀵硅瘽锛堝畬鏁达級 | 鎻愮偧鎽樿锛堢粨鏋勫寲锛?|
| **鍏冩暟鎹?* | layer, role, session_id | mu_type, mu_tag, layer_type, importance, confidence, slm_version, store_priority |
| **寤惰繜瑕佹眰** | 蹇呴』鍦?HTTP 鍝嶅簲鍐呭畬鎴?| 鍙欢杩熸暟绉掑埌鏁板垎閽?|
| **澶辫触褰卞搷** | 鐢ㄦ埛鍙锛堣蹇嗕涪澶憋級 | 鐢ㄦ埛鏃犳劅鐭ワ紙鑷姩閲嶈瘯锛?|
| **鍘婚噸** | 鉂?涓嶅仛 | 鉁?浣欏鸡鐩镐技搴?鈮?0.90 |
| **鍐茬獊瑙ｅ喅** | 鉂?涓嶅仛 | 鉁?鏋佹€ф娴?+ 瑕嗙洊 |
| **鏍囧噯鍖?* | 鉂?涓嶅仛 | 鉁?鏈缁熶竴 + 涓昏褰掍竴 |
| **璐ㄩ噺鎺у埗** | 鉂?鍏ㄤ繚瀛?| 鉁?SLM 璇勪及 + 鍐崇瓥鐭╅樀 |
| **鎵归噺澶勭悊** | 姣忚姹?1 娆?| 鍚庡彴鎵归噺娑堣垂 |

---

# 馃椇锔?鍏抽敭鏂囦欢绱㈠紩

| 鏂囦欢 | 鑱岃矗 |
|------|------|
# 🗺️ 关键文件索引

| 文件 | 职责 |
|------|------|
| `api/chat.py` | HTTP 入口，解析请求，构建响应 |
| `core/memory.py` | MemoryManager：阶段 0 的核心编排 |
| `core/memory_pipeline.py` | 阶段 1 的编排入口（worker、_store_mu） |
| `core/prompt_factory.py` | SLM Prompt 模板（v3.0，约 180 行） |
| `core/decision_maker.py` | 决策矩阵（importance x confidence 分类） |
| `core/text_utils.py` | 文本处理（标准化/去重/极性检测/SLM 验证） |
| `core/prompt.py` | RAG 提示构建 |
| `core/llm.py` | LLM 客户端工厂 |
| `core/config.py` | 全局配置 |
| `core/state.py` | 运行时状态（活跃角色、核心写模式、活跃文档） |
| `services/embedding.py` | 向量化服务（Ollama nomic-embed-text） |
| `services/qdrant_store.py` | Qdrant 数据访问层 |
| `services/session_store.py` | 内存会话存储 |
| `services/persistent_queue.py` | SQLite 持久队列 |

