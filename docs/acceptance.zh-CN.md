# 项目验收与讲解

验收范围是原计划的 **P0 九项 + P1 四项，共 13 项**。下表给出实现和验证入口，
用于核对进度。这里的完成状态指代码、测试、实验记录和仓库交付，不代表用户已
亲自审阅代码或理解全部实现。

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

公开数据实验只用了固定的 14/500 题，并且只评估来源会话召回。BM25 为 18/18，
神经混合检索为 17/18，加入 cross-encoder 后为 18/18；重排没有显示优于 BM25，
CPU 查询中位耗时约 1.515 秒。两个无答案问题仍返回上下文，不能称为正确拒答。
这些数值都不能写成问答准确率或全量基准成绩。

继续阅读：[代码路径](code-guide.md)、[操作与升级](usage.md)、[设计边界](design.md)。
