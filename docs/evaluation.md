# What the measurements mean

The project has working memory/governance features and recorded controlled
experiments. A higher number in one experiment does not establish superiority
over a different CV benchmark, dataset or deployment. Metrics below describe
their saved runs; none is a promise for future queries.

## Evidence card

| Task | Observation | Denominator and scope | Source |
| --- | --- | --- | --- |
| Temporal evidence selection | 60/60 positive queries recovered all gold evidence in each workload | 84 queries: 60 positive, 24 negative; known synthetic templates at 72 and 1152 assertions | [Full-path v0.8.1](../eval/RESULTS-v0.8.1.md) |
| Current stale evidence | 0/792 returned items in the largest governed case | Includes three replays of the same 84 queries; not 792 independent trials | [Saved observations](../eval/results/system-baseline-v081-2026-11-16/observations.jsonl) |
| Relevance heldout | 47/48 positive queries recovered all gold evidence (97.92%) | 80 previously evaluated synthetic queries: 48 positive, 32 negative | [v0.8 study](../eval/RESULTS-v0.8.md) |
| Full retrieval latency | P95 0.762 s; first-pass 0.806 s; repeats 0.516 s | CPU, 2 inference threads, one caller, warmed models, PostgreSQL + Neo4j + OpenFGA + MCP stdio, k=5, 1024 tokens | [Protocol and hardware](../eval/RESULTS-v0.8.1.md#final-baseline-and-source-identity) |
| Optional long-conversation answers | Local judge accepted 181/500 (36.2%) | A different 500-question answer task; local model grading, not official or human grading | [v0.6 answer evaluation](../eval/RESULTS-v0.6.md) |

Last full-path performance measurement: **v0.8.1**. Later presentation/installation
changes do not constitute a new performance evaluation. The release verification
checks installability and behavior; it does not refresh these scores.

## Why some results are 100%

The controlled temporal corpus supplies explicit approval, validity, withdrawal
and dependency signals. These tests check whether the implementation obeys those
rules. Recovering all gold evidence for its 60 positive questions gives 100%
Recall@5 on that set. The 1152 assertions replicate the same known scenario
templates across cohorts; they are not 1152 independent questions. Replaying each
question three times measures cache/timing behavior, not three new samples.

The separate stale-reduction experiment changed 498/816 stale returned items in
an unsafe session control to 0/789 in the governed retriever. That is a 100%
relative reduction **on that comparison**. It is not a new full-path session
comparison, a general security guarantee or proof of a zero future failure rate.

The evaluated relevance heldout already has a miss (47/48 positives). Negative
questions still receive unrelated but eligible evidence with the default
retriever, and answer correctness remains limited. Source authorization,
relevance, answer correctness and deployment reliability are separate properties.

## Can these results hold in use?

The same pinned inputs/models can be replayed to check regressions. New
histories, languages, data quality, policies, model revisions, hardware and
concurrency can change results. Fixed controls and correlated replays cannot
establish general accuracy or a statistical bound on future failures. No
production/WAN/concurrency SLO is claimed.

The P95 excludes process/model startup (observed 4.95-5.53 s), downloads,
ingestion, graph projection and answer generation. Services were on one hosted
runner. The old 0.408 s measurement excludes graph/remote-authority/transport;
it must not be compared to 0.762 s as a version speedup or regression.

One transport-pooling candidate regressed largest-case P95 by 8.8% and was
reverted. Its [negative results](../eval/results/system-transport-v1-2026-11-16/summary.json)
remain alongside the retained baseline. Future changes must retain failures,
freeze their protocol and disclose regressions rather than selecting a good run.

## Describing the project in a CV

Do not replace a measured 100% with an invented 98% to make it look plausible.
Either include its finite denominator and synthetic scope, or omit the percentage
and describe the implementation, verification and measured retrieval latency.
For example:

> Built a Rust/Python bitemporal memory service with approval-gated writes,
> provenance and live access checks; evaluated retrieval on 1152 synthetic
> historical assertions, with 0.762 s P95 through PostgreSQL, Neo4j, OpenFGA
> and MCP on a single CPU host with warmed models.

This describes a specific measurement, not a universal accuracy or latency
guarantee. Project development dates and recent GitHub publication dates are
distinct; repository upload time does not establish when development began.

## 中文说明：100% 是否真实、是否能保持？

**在对应已保存的测试集上是真实结果，不能保证换数据后仍为 100%。** 每组只有
60 道可回答模板题，重复三次并不等于 180 道独立新题；1152 条历史断言也不等于
1152 道独立问题。另一个已评估保留集为 47/48，可选回答任务的本地评分为 181/500。

因此不把 100% 放成通用准确率或安全保证，也不为了观感改成虚构百分比。CV 可以
直接写实现能力、受控数据规模、真实调用链路与 0.762 秒 P95，并注明模型已加载、
单调用者、同机 CPU 服务。部署时的实际效果需在使用者自己的数据和负载上验证。
