# 第三轮：并发扩展、许可证与端到端吞吐

## 摘要

本轮不是重新寻找“任务数”交叉点，而是把第二轮的 580 管、16-bit CMOS ripple-carry adder 公平对照扩展到并发 worker、批长度和分析复杂度，回答实际集群环境中哪一类工作负载能跑得更快。发布数据包含 872 条通过结构门槛的 matrix 记录；226 条早期失败记录保留在服务器隔离目录，不参与汇总或排名。

结论不是“某一个模拟器总是更快”。对 DC 工作负载，official NGSPICE 在 worker=1 已经超过 HSPICE independent；HSPICE `.alter` 明显优于其 independent 模式，但仍落后于 NGSPICE 的 DC 端到端结果。对严格 transient，实测范围内没有观察到 official NGSPICE 超过 HSPICE 的交叉点。并发提高的是持续吞吐而非单次求解能力；在 HSPICE worker 超过约 128 时，许可证并发上限和进程启动/网表读取成为端到端瓶颈。

## 与实验清单及前两轮的关系

实验清单要求验证拓扑复用、HSPICE `.alter` 的缓存/批处理效果、NGSPICE/HSPICE 的交叉条件，并交付可审计的原始计时、误差和复现材料。三轮的分工如下：

1. 第一轮用 550 管规则反相器链验证机制：优化 NGSPICE reuse 的 500 点 DC 总时间从 34.563370 s 降至 33.093501 s（约 1.044 倍），且 setup reuse 为 499/500，数值差约 1.38e-14 V。
2. 第二轮在 580 管 adder 上统一 BSIM4 模型、精度、输入/输出和单 CPU 核，建立单任务的公平排名与误差门槛。
3. 本轮保持该公平口径，补充强扩展、弱扩展和许可证受限的端到端时间。因此本报告解释“多 worker 下的可交付吞吐”，不取代第二轮的单任务/电路规模结论。

## 设计与公平性

- 电路为统一 BSIM4 参数的 580 管 16-bit CMOS ripple-carry adder；每个模拟器使用相同输入、输出、精度要求和计时边界。
- 所有比较禁用模拟器内部 OpenMP，并进行 CPU pinning；worker 并发是进程级并行，避免把内部多线程混入比较。
- 同时报告 solver-only 与 end-to-end：前者聚焦求解，后者包含网表生成、进程启动、文件读写与许可证 checkout，后者才是用户实际等待的时间。
- HSPICE 的并发许可证上限约为 128。超过该值的 worker 记录保留为真实集群吞吐证据，但不被解释为无限许可证下的纯求解性能。
- 复用 transient 曾出现同二进制下最大误差 1.68e-4 V、超过正式门槛，因此仍不进入 transient 正式排名。

## 完成范围与证据边界

完整 DC solver-only 主矩阵已经保留。为控制总运行时间，后续端到端与 transient 改为代表性抽样：DC end-to-end 使用 workers 1/8/32、一次重复；transient end-to-end 使用 workers 1/8/32、4 个 vectors、一次重复，且不包含 NGSPICE reuse。详细缩减规则见 [REDUCED_SCOPE.md](REDUCED_SCOPE.md)。

因此，872 是通过门槛的有效记录数，不是原计划 1392 格的完成声明；未采样 worker 不应被表述为完整曲线。历史失败记录没有删除，发布前的筛选依据见 [data/summary/matrix_gate.json](data/summary/matrix_gate.json)，公开载荷审计见 [RELEASE_AUDIT.md](RELEASE_AUDIT.md)。

## 结果与解释

### DC：NGSPICE 的交叉点在单 worker 即出现

在 DC end-to-end、complexity=21 下，official NGSPICE 相对 HSPICE independent 在 worker=1 即达 5.591 倍；NGSPICE reuse 相对 HSPICE `.alter` 在 worker=1 即达 2.505 倍。complexity=101 时，official NGSPICE 相对 HSPICE independent 在 worker=1 达 9.105 倍，reuse 相对 `.alter` 达 1.984 倍。solver-only 的对应趋势一致：official NGSPICE 相对 HSPICE independent 在 complexity=5/101 分别为 4.949/9.146 倍。

这说明在本电路、DC 和本精度口径下，“NGSPICE 何时超过 HSPICE”的答案不是等到大 worker 数：它从单 worker 已领先。worker 增长仍有价值，但主要用于提高批量任务的完成速率，而非制造一个原本不存在的单任务交叉点。完整数表、交叉点和曲线分别在 [data/summary/timings.csv](data/summary/timings.csv)、[data/summary/crossovers.csv](data/summary/crossovers.csv)、[data/summary/weak_scaling.csv](data/summary/weak_scaling.csv) 与 [figures](figures) 中。

### `.alter` 是 HSPICE 的有效批处理模式，但证据边界明确

第二轮 500 点 DC 已显示 HSPICE `.alter` 由 262.516055 s 降至 126.874358 s（约 2.07 倍）。本轮继续将 `.alter` 作为 HSPICE 的最佳批处理对照，而非只和每点独立启动的模式比较。它表明 `.alter` 路径存在可观的批处理/缓存收益；但外部计时不能证明 HSPICE 内部究竟复用了 sparse matrix、symbolic factorization 还是其他状态，所以报告不把它夸大为“已证明内部矩阵复用”。

在高 worker 数下，HSPICE 的端到端时间还包含许可证排队、进程创建和网表读入。特别是请求 worker 超过约 128 时，任务会分波领取许可证：这是生产环境真实限制，却不能用来推断 HSPICE 单次数值求解本身没有扩展性。

### NGSPICE 源码优化和拓扑复用的收益是条件性的

optimized independent 与 official NGSPICE 的差距极小：DC end-to-end complexity=21 在 worker=1 仅 1.001 倍，complexity=101 的首次轻微领先也只有 1.011 倍。这表明本轮端到端瓶颈主要不在该源码优化路径。

复用的表现取决于分析复杂度与调度条件。DC solver-only、complexity=5 时，reuse 相对 optimized independent 从 worker=1 已有 1.094 倍；DC end-to-end、complexity=21 的首次可见优势在 worker=64，为 1.214 倍。相反，在 complexity=101 下没有观察到 reuse 相对 optimized independent 的交叉点。这与前两轮一致：规则、轻量 DC 会受益；复杂 adder 或数值求解占主导时，维护复用状态的开销可以抵消甚至超过收益。不能据此宣称“拓扑复用通用加速”。

### transient：本实验范围内 HSPICE 仍占优

第二轮 20 点严格 transient 的端到端时间为 HSPICE independent 38.651198 s、HSPICE `.alter` 20.961318 s、optimized NGSPICE independent 300.961207 s。本轮的 transient end-to-end、complexity=4 中，official NGSPICE 相对 HSPICE independent 的交叉点为 `not_observed`；optimized 相对 official 的变化仅约 1.002 倍。结合复用 transient 的误差门槛失败，当前证据支持“严格 transient 下应优先使用 HSPICE `.alter`”，而不是把 DC 的结论外推到 transient。

## 对实验清单问题的总回答

1. **拓扑复用是否真的加速？** 是，但有条件。第一轮轻量 DC 有约 1.044 倍收益；本轮低复杂度 solver-only 也观察到 1.094 倍。复杂 adder/高复杂度和严格 transient 不保证收益，后者还因误差门槛不能纳入排名。
2. **HSPICE `.alter` 是否存在复用或缓存？** 外部端到端计时显示明确的批处理收益（第二轮 DC 约 2.07 倍），足以把 `.alter` 作为公平的最佳 HSPICE 批处理模式；但没有内部 profiler 证据，不能断言其具体复用了矩阵或 symbolic factorization。
3. **NGSPICE 在何时超过 HSPICE？** 对本 adder 的 DC，official NGSPICE 在 worker=1 已超过 HSPICE independent，且相对 `.alter` 也有领先；对严格 transient，实测范围尚未出现交叉点，HSPICE `.alter` 更合适。
4. **并发与许可证的结论是什么？** worker 数提高可增加持续吞吐，但端到端速度会受到启动、I/O、网表解析和许可证的共同限制。HSPICE 超过约 128 并发许可证时出现排队；这解释了集群完成时间，却不应被误读为纯 solver 基准。

## 复现与发布审计

- 运行入口：`scripts/run_matrix.sh`；汇总与图表由分析脚本生成。
- 有效原始记录与汇总：`data/raw`、`data/summary/timings.csv`、`data/summary/strong_speedups.csv`、`data/summary/weak_scaling.csv`。
- 完整单任务公平对照、误差与电路解释见上级目录 [REPORT.md](../REPORT.md)；第一轮材料仍保留，未被本轮覆盖或删除。
- 发布不包含 HSPICE 可执行文件、许可证、守护进程配置或私有预检日志；数据筛选和文件大小审计记录在 [RELEASE_AUDIT.md](RELEASE_AUDIT.md)。
