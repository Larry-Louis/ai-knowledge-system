## Plan: GLiNER 信息丰富度原型接入

在不改动现有评分入口的前提下，先新增独立 GLiNER 原型模块，按 Information Richness Analyzer 的证据维度输出信息丰富度结果，并通过烟雾测试验证可用性、性能与稳定性，再决定是否替换现有第二维逻辑。

**Steps**
1. Phase A: 原型骨架与依赖准备
1. 在 rag-api/infrastructure 下新增 nlp 子目录与模块文件（建议文件名 gliner_information_density.py），实现延迟加载模型、统一异常处理、可配置阈值与标签集合。
1. 更新 [rag-api/requirements.txt](rag-api/requirements.txt) 增加 GLiNER 运行依赖，并记录与当前 Python 版本兼容的最小可用版本。
1. 约束边界：本阶段不修改 [rag-api/domain/memory/rule_evaluator.py](rag-api/domain/memory/rule_evaluator.py) 与 [rag-api/application/memory_pipeline_service.py](rag-api/application/memory_pipeline_service.py)。

1. Phase B: 信息丰富度实现（遵循文档规范）
1. 在原型模块实现 InformationRichnessResult 数据结构，输出 score 与 evidence（named_objects、noun_phrases、numbers、relations、attributes、structure）。
1. 实现证据提取流水：
1. 命名对象：基于 GLiNER 的实体识别结果计数与去重。
1. 名词短语与属性：优先规则法（轻量分词/模式）补充实体盲区。
1. 数字信息：正则提取时间、日期、百分比、数量、金额等。
1. 关系与结构：规则识别我的/我们的/负责/属于等关系表达与并列/因果/举例结构。
1. 实现可解释打分函数：证据归一化 + 加权汇总（0 到 1），并保留每项中间值用于日志调试。

1. Phase C: 初步测试与结果汇报
1. 新增独立 smoke test 脚本（建议放在 rag-api 下，名称如 gliner_smoke_test.py），直接调用原型模块，不依赖主流程。
1. 设计最小样本集：
1. 高信息密度技术语句（含实体、版本、数字、关系）。
1. 中等密度语句（少量实体，结构简单）。
1. 低密度语句（泛化表达、撤回表达）。
1. 执行测试并输出：实体识别命中、证据统计、最终分数、单条耗时与加载耗时。
1. 形成采用建议：准确性观察、误检漏检模式、运行成本、是否建议进入 rule_evaluator 的 detect_information_density 替换方案。

1. Phase D: 为后续接入预留（仅设计，不实施）
1. 预留适配函数签名，使未来 detect_information_density 可以切换为调用该原型（通过特性开关或配置注入）。
1. 预留降级路径：GLiNER 不可用时回退到当前关键词逻辑，避免线上不可用风险。

**Relevant files**
- [rag-api/domain/memory/rule_evaluator.py](rag-api/domain/memory/rule_evaluator.py) — 现有第二维入口与未来接入点（本次不改）。
- [rag-api/domain/memory/rule_config.py](rag-api/domain/memory/rule_config.py) — 现有词表策略参考，可复用阈值配置风格。
- [rag-api/application/memory_pipeline_service.py](rag-api/application/memory_pipeline_service.py) — 当前评分调用链路确认（本次不改）。
- [rag-api/requirements.txt](rag-api/requirements.txt) — 新增 GLiNER 依赖。
- 新建: rag-api/infrastructure/nlp/gliner_information_density.py — GLiNER 信息丰富度原型实现。
- 新建: rag-api/gliner_smoke_test.py — 初步验证脚本。

**Verification**
1. 安装依赖后执行 smoke test，确认模型可加载并返回非空证据结构。
1. 对 6 到 10 条样本输出 evidence 与 score，人工检查是否符合 Information Richness Analyzer 的预期趋势（高密度 > 中密度 > 低密度）。
1. 记录性能指标：首次加载耗时、单条推理耗时、内存占用粗测；判断是否满足 Phase1 过滤器的实时性要求。
1. 失败场景验证：无网络、模型下载失败、空文本输入、超长文本输入时应返回可解释降级结果而非抛异常。

**Decisions**
- 已确认原型位置：infrastructure/nlp。
- 已确认依赖策略：允许本次加入并安装 GLiNER 做 smoke test。
- 本次范围包含：新增原型与测试脚本、完成初测报告。
- 本次范围不包含：修改现网评分主链路、替换 detect_information_density、生产部署参数调优。

**Further Considerations**
1. GLiNER 模型选择建议先用轻量基线（如 base 级别）验证正确性，再视延迟决定是否切换更小模型。
2. 若中文识别效果不足，建议在原型阶段同时准备中英混合样本评估，避免后续接入后出现语言偏置。