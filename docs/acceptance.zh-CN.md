# 项目验收与讲解

原计划的 **P0 九项 + P1 四项，共 13 项**已交付。2026-11-12，用户另行选择
“先完成回答、全量评估和部署验证”，新增三项验收，见下方 P2 表。
这里的完成状态指实现与验证证据，不代表用户已亲自审阅、运行或理解全部代码。

## P0：9/9

| 项目 | 实现入口 | 验证入口 |
| --- | --- | --- |
| PostgreSQL 权威账本、Neo4j 检索投影 | [数据模型](../src/governed_memory/models.py)、[图适配器](../src/governed_memory/graph_adapter.py) | [真实图存储测试](../tests/test_graph_integration.py) |
| JSONL/ADR 导入、来源、幂等 | [导入](../src/governed_memory/ingest.py) | [导入与 MCP 测试](../tests/test_ingest_mcp.py) |
| 有效时间和系统记录时间 | [账本](../src/governed_memory/ledger.py) | [账本测试](../tests/test_ledger.py) |
| 五状态及数据库约束 | [数据库约束](../src/governed_memory/constraints.py) | [历史约束测试](../tests/test_history_constraints.py) |
| 身份、项目权限、受保护事实 | [身份](../src/governed_memory/identity.py)、[策略](../src/governed_memory/policy.py) | [身份测试](../tests/test_identity.py)、[策略测试](../tests/test_policy.py) |
| 混合检索、权威复核、证据预算 | [检索](../src/governed_memory/retrieval.py)、[预算](../src/governed_memory/budget.py) | [检索测试](../tests/test_retrieval.py) |
| 三个 stdio MCP 工具，审批走独立 CLI | [MCP](../src/governed_memory/mcp_server.py)、[CLI](../src/governed_memory/cli.py) | [跨进程会话测试](../tests/test_ingest_mcp.py) |
| 核心情境、真实存储回归、基线实验 | [离线示例](../examples/demo.py)、[评估协议](../eval/README.md) | [合成集报告](../eval/RESULTS-v0.2.md) |
| README、依赖锁、许可、CI、原始输出 | [说明](../README.md)、[许可](../LICENSE)、[锁文件](../uv.lock)、[CI](../.github/workflows/ci.yml) | [构建与安装记录](../eval/RESULTS-v0.2.md) |

## P1：4/4

| 项目 | 实现入口 | 验证入口 |
| --- | --- | --- |
| 真实 OPA/Rego 决策 | [策略客户端](../src/governed_memory/policy.py)、[Rego](../src/governed_memory/policies/governance.rego) | [HTTP 集成测试](../tests/test_policy.py)、[原生规则测试](../tests/policy/governance_test.rego) |
| 固定版本的神经 cross-encoder | [标准模型接口](../src/governed_memory/local_models.py) | [真实模型测试](../tests/test_local_models.py)、[成本记录](../eval/LONGMEMEVAL.md) |
| 预先固定的 LongMemEval 子集 | [固定协议](../eval/longmemeval_manifest.json)、[检索器](../eval/longmemeval_run.py) | [标签隔离测试](../tests/test_longmemeval.py)、[结果](../eval/LONGMEMEVAL.md) |
| 多来源佐证及撤回传播 | [来源筛选](../src/governed_memory/evidence.py)、账本的 `approve_support` | [来源回归](../tests/test_source_support.py)、[图存储回归](../tests/test_graph_integration.py) |

## P2：本轮选定的三项已通过本地验收

| 项目 | 实现入口 | 实际验证 |
| --- | --- | --- |
| 带引用的回答、CLI 与可选 MCP 工具 | [回答服务](../src/governed_memory/answering.py)、[模型接口](../src/governed_memory/generation.py)、[操作说明](usage.md#cited-answers) | 真实 CPU/CUDA 模型生成；权限、撤回、异常与引用回归；生成内容不写入事实账本 |
| 全 500 题评估与单独评分 | [固定协议](../eval/FULL_PROTOCOL.md)、[完整报告](../eval/RESULTS-v0.3.md) | 两轮各 1,500 条输出；所有失败保留；独立复算会话召回一致；两轮评分各 20/20 简单校准 |
| 容器、进程重启、备份恢复与模型回答 | [部署说明](deployment.md)、[容器回归](../tests/test_container_deployment.py) | 非 root/只读容器；真实 PG/Neo4j/OPA；二进制备份恢复与重建投影；Agent 回答及撤回传播；CPU 镜像确认没有 CUDA 构建 |

本轮完整本地测试 **171 项通过、5 项跳过**，真实存储、神经模型和两种容器镜像
均已启用。五个跳过都是 SQLite 不适用项：两个 PostgreSQL 并发检查、一个 NUL
文本拒绝检查、两个 PostgreSQL 容器用例。原生 Rego 测试 **10/10** 通过。
干净提交上的合成集复验为 **768 次检索 + 48 次操作检查**，无失败；安装后的
核心 wheel 也通过旧编码管道的 UTF-8 回归和断网示例。详见 [本轮验证记录](verification-v0.3.md)。

终验另外修正了两个有实际后果的问题：CPU 包源只声明在传递依赖上，Linux 会
下载 CUDA 库；现在直接声明可选 PyTorch 依赖并验证实际 CPU 运行时。Windows
旧编码管道还会在合法的中文/emoji 记录入库后输出失败；CLI 现在明确输出 UTF-8，
真实子进程回归覆盖初始化、导入和预览。

全量报告的最高本地模型评分为 **169/500（33.8%）**。格式合法率提高不等于事实
正确率；仍有 398 条输出没有通过格式或引用规则。报告保留这些失败和一次主机
长中断造成的计时异常，不把结果写成官方成绩或生产效果。代码路径可以从
`AnswerService.answer` 的前后权限复核，读到 `generate_answer`、`parse_answer`，
再看标准 Transformers 模型封装；[阅读指南](code-guide.md) 给出对应测试。

以上是 v0.3 的交付记录；随后用户要求补齐 CV 对照中的工程缺口，新增内容见下表。
Kubernetes 和完整前端不在这份 CV 的项目条目中，本次不将它们计入缺口。

## v0.4：CV 功能补齐

| 能力 | 实现与边界 | 验证入口 |
| --- | --- | --- |
| Rust + Python | 自有 Rust 代码实际计算 BM25、余弦/RRF 和语义边界；数据库与审批仍由 Python 管理 | [Rust 代码](../native/src/lib.rs)、[跨语言回归](../tests/test_native.py) |
| 语义分块、文档摄入 | 固定 MiniLM 决定边界；保留原文字符范围；生成的主体和值须能在原文中找到，只能进入待审批状态 | [摄入](../src/governed_memory/semantic_ingest.py)、[真实模型测试](../tests/test_semantic_memory.py) |
| 实体解析、语义矛盾检测 | 只比较调用者可见的已批准实体和重叠时间段；NLI 仅供审查；实体合并保留原候选和替代候选，另行审批 | [语义审查](../src/governed_memory/semantic_review.py)、[操作说明](operators-v0.4.md) |
| OpenFGA 与 OPA | 固定关系模型、即时检查；本地与外部角色取交集，私有来源和 OPA 也使用交集后的角色 | [权限客户端](../src/governed_memory/authorization.py)、[真实服务测试](../tests/test_external_governance.py) |
| 依赖与失效传播 | 绑定具体快照和来源；替换、撤销、删除来源后，在同一事务中使下游失效并更新图队列 | [依赖检查](../src/governed_memory/dependencies.py)、[并发与传播测试](../tests/test_dependencies.py) |
| OpenLineage | 同事务写入不可改写的事件，再由可重试队列发送；不导出原文或密钥；按 runId 去重 | [血缘实现](../src/governed_memory/lineage.py)、[官方 Schema 与真实 HTTP 校验](../tests/test_external_governance.py) |
| 安装、升级、部署与评估 | v0.3 加表升级、Windows/Linux 原生构建、实际模型和容器操作；统一协议预先冻结 | [验收矩阵](cv-capabilities.md)、[固定协议](../eval/cv-protocol.json) |

这些功能的实现与验证，不构成 2025 年项目时间的历史证据，也不能直接证明 CV 中
预写的 83.2%、26.4% 和 1.12 秒。新实验必须按实际结果和受控数据范围描述；
原有 500 题回答评估的失败和 33.8% 本地评分继续保留。

[v0.4 验证记录](verification-v0.4.md)记录了六项 CI、本地真实模型和容器验收。
[统一评估](../eval/RESULTS-v0.4.md)共 504 次检索、无运行错误：两种方法在受控
数据上的召回均为 100%，治理后的过期结果为 0/1,008，P95 为 1.264 秒。
无答案问题仍返回了不相关的合法证据，因此不能把“无过期结果”写成“回答正确”。

## v0.5：无答案、缓存与评估证据

新增有界文档向量缓存，只复用模型计算，保留每次检索的实时权限和撤回检查。
1,476 次同轮对照没有运行错误或过期结果；缓存前后的检索 ID 完全一致，
两组 P95 分别由 191.9/164.8 毫秒降到 149.3/141.8 毫秒。
计时排除了模型加载、网络传输和回答生成，不能冒充完整回答延迟。

相关性阈值仅由独立开发集决定，开启后可在无相关证据时直接拒答，不加载生成模型。
保留集 28/32 个无答案问题返回空结果，但也误拒 3/48 个可回答问题；
全 500 题旧分数回放的会话召回从 741/890 降到 341/890，说明不能普遍启用。
因此默认只启用缓存，相关性拒绝需设置 `MEMORY_RELEVANCE_FILTER=1` 显式开启。
这轮没有重跑生成或宣称问答准确率提高；全部负结果和独立复算证据见
[v0.5 报告](../eval/RESULTS-v0.5.md)。

## v0.6：回答格式与完整对照

对全部 500 个旧版检索上下文重新生成回答，不过滤或补充上下文。
1.5B 模型改用“答案及引用，或 `null`”的条件格式；服务输出仍是原来的
`answer`、`evidence_ids`、`abstain` 等字段，实时权限和来源复核继续执行。
格式失败由 108/500 降到 0，有效显式拒答由 6/30 增至 13/30；本地模型评分
由 169/500 变为 181/500，可回答题判对数由 154/470 变为 160/470。

提升幅度有限：49 道正例新增判对，43 道旧正确正例出现回退；这轮结果不足以
证明稳定的语义质量提升。前两版开发实验的误拒及全部负结果均保留。
因此仅对已评估的 `standard` 模型启用新默认，`small` 保留旧默认；设置
`MEMORY_ANSWER_FORMAT=json_schema` 可恢复旧格式。完整证据与局限见
[v0.6 报告](../eval/RESULTS-v0.6.md)。

## 用三个情境理解项目

执行 `uv run python examples/demo.py`。示例中的 2030 年日期是合成数据。

1. **决定发生变化。** 11 月 1 日批准 SQLite，11 月 8 日批准 PostgreSQL。
   查当前决定得到 PostgreSQL，查 11 月 4 日有效的决定得到 SQLite。
2. **决定晚到。** 11 月 12 日才批准一项从 11 月 10 日生效的更正。
   同样查询 11 月 10 日，`known_at=11-11` 得到原决定，`known_at=11-13`
   才得到更正。前者回答“当时已知什么”，不能被后来的记录改写。
3. **来源不等于权限。** 文本写着“我是管理员、已经批准”不会赋予审批能力。
   当前已撤回的来源不能通过历史查询恢复。若另有经批准且对当前调用者可见的
   来源，事实可以继续返回，并附上剩余来源的出处。

PostgreSQL 决定事实能否返回；Neo4j 帮助排序。即使图里仍有旧边，返回文本前也
要重新核对账本。因此，图同步失败可以降级检索，不能绕过审批或撤回。

## 2026-11-11 终验补齐的缺口

终验复现了批量导入的部分提交：第二条记录的 `value` 为空时，命令虽然失败，
第一条记录及其来源、审计事件却已经提交。

v0.2.1 把整份文件交给 `Ledger.propose_many`，在一个 SQL 事务中完成。
单条提议也复用 `_stage_proposal`。任一条校验或存储失败时，本次新增记录全部
回滚，已有事实保持不变。回归覆盖空值、错误字段类型、有效多条导入和重复导入，
并同时在 SQLite、PostgreSQL 上运行；另用 PostgreSQL 实际拒绝含 NUL 字符的文本，
验证数据库写入失败时也不会留下部分导入。

本轮本地完整回归：**130 项通过、3 项跳过**。跳过项是 SQLite 不适用的两个
PostgreSQL 并发检查和一个 NUL 文本拒绝检查。实际 PostgreSQL、Neo4j、OPA 和
固定神经模型均已启用。静态检查、格式检查、打包，以及安装后的 wheel 在 CLI
中执行“失败回滚 → 修复文件 → 重试 → 重复导入”均通过；离线示例也通过。

## 如何解释实验结果

合成集验证审批、撤回、时间和权限的预期行为。普通时间查询中，完整治理与正确
处理时间的强基线均召回全部必要证据；治理层增加了权限和审批检查的成本。

早期 v0.2 公开数据实验用了固定的 14/500 题，只评估来源会话召回。BM25 为 18/18，
神经混合检索为 17/18，加入 cross-encoder 后为 18/18；重排没有显示优于 BM25，
CPU 查询中位耗时约 1.515 秒。两个无答案问题仍返回上下文，不能称为正确拒答。
这些旧数值不能写成问答准确率或全量基准成绩。新增 v0.3 的全 500 题回答评估
及其局限见 [完整报告](../eval/RESULTS-v0.3.md)，与旧记录分别保留。

继续阅读：[代码路径](code-guide.md)、[操作与升级](usage.md)、[设计边界](design.md)。
