# NGSPICE 与 HSPICE 公平对照实验

## 为什么需要第二轮

第一轮以高度重复的反相器链和优化 NGSPICE 的 `batchrun` 为中心，启动、解析与拓扑复用收益占比较大，且缺少官方 NGSPICE 基线和真实瞬态工作量，因此不能仅凭第一轮总时间判断模拟器本体优劣。本轮改用 580 管静态 CMOS 16 位 ripple-carry adder，统一模型卡、精度、输入、采样网格、输出量、编译工具链和单核绑定，并分开 solver-only 与 end-to-end。

## 实验完整性

- 完成 312 个正式批次；DC 规模 1/10/50/100/200/500，瞬态规模 1/5/10/20。
- 每种模式完成规定的 5 次单点或 3 次重复，汇总取中位数。
- 580 个 MOSFET、500 个 14 维参数点；发布审计状态 `pass`。
- 瞬态数字逻辑稳定采样检查 640 项全部通过。

## 数值一致性

- `dc` `hspice_independent` vs `hspice_alter`：max=0 V，median=0 V，P95=0 V。
- `dc` `ngspice_official_independent` vs `ngspice_optimized_independent`：max=0 V，median=0 V，P95=0 V。
- `dc` `ngspice_optimized_independent` vs `ngspice_optimized_reuse`：max=1e-15 V，median=0 V，P95=1e-16 V。
- `dc` `hspice_independent` vs `ngspice_official_independent`：max=5.1e-14 V，median=0 V，P95=3.4e-14 V。
- `tran` `hspice_independent` vs `hspice_alter`：max=0 V，median=0 V，P95=0 V。
- `tran` `ngspice_official_independent` vs `ngspice_optimized_independent`：max=0 V，median=0 V，P95=0 V。
- `tran` `hspice_independent` vs `ngspice_official_independent`：max=0.771821 V，median=9.8106e-07 V，P95=0.0012802 V。

瞬态跨模拟器最大差异发生在开关边沿；median 和 P95 较小且所有稳定数字结果一致。由于双方 BSIM4 内部实现并非同一源码，瞬态速度结论表述为相同公共模型卡与误差设置下的实际性能比较。

## 最大规模排名

- `solver_only/dc` N=500：第 1 名 `ngspice_optimized_independent`，45.824697 s。
- `solver_only/dc` N=500：第 2 名 `ngspice_official_independent`，45.877468 s。
- `solver_only/dc` N=500：第 3 名 `ngspice_optimized_reuse`，55.648952 s。
- `solver_only/dc` N=500：第 4 名 `hspice_alter`，126.466532 s。
- `solver_only/dc` N=500：第 5 名 `hspice_independent`，263.070766 s。
- `solver_only/tran` N=20：第 1 名 `hspice_alter`，0.980838 s。
- `solver_only/tran` N=20：第 2 名 `hspice_independent`，2.407502 s。
- `solver_only/tran` N=20：第 3 名 `ngspice_optimized_independent`，301.309291 s。
- `solver_only/tran` N=20：第 4 名 `ngspice_official_independent`，301.350576 s。
- `end_to_end/dc` N=500：第 1 名 `ngspice_official_independent`，46.295444 s。
- `end_to_end/dc` N=500：第 2 名 `ngspice_optimized_independent`，46.352922 s。
- `end_to_end/dc` N=500：第 3 名 `ngspice_optimized_reuse`，56.278201 s。
- `end_to_end/dc` N=500：第 4 名 `hspice_alter`，126.874358 s。
- `end_to_end/dc` N=500：第 5 名 `hspice_independent`，262.516055 s。
- `end_to_end/tran` N=20：第 1 名 `hspice_alter`，20.961318 s。
- `end_to_end/tran` N=20：第 2 名 `hspice_independent`，38.651198 s。
- `end_to_end/tran` N=20：第 3 名 `ngspice_optimized_independent`，300.961207 s。
- `end_to_end/tran` N=20：第 4 名 `ngspice_official_independent`，301.351620 s。

## 关键结论

- DC 中官方与优化 NGSPICE independent 数值完全一致、速度也接近；这分离出第一轮结果并非来自不同模型调用。
- DC 中优化 reuse 与 independent 达到近机器精度一致，但本电路/分析下 reuse 未必更快；是否获益取决于每点求解成本与批处理实现开销。
- 严格瞬态下 HSPICE 显著快于两种 NGSPICE independent，这与第一轮看似 NGSPICE 全面更快的印象不同。
- `hspice_alter` 相对 independent 在 DC 和 end-to-end 瞬态均降低批处理时间；内部机制只依据外部时间证据描述，不推测专有实现。
- solver-only 与 end-to-end 排名分别保存在 `data/summary/rankings.csv`，线性拟合与加速比分别见 `linear_fits.csv` 和 `speedups.csv`。

## 精度与复用限制

共同生产设置为 `RELTOL=1e-6 VNTOL=1e-9 ABSTOL=1e-13 GMIN=1e-12` 与 Gear。更严格的 NGSPICE 设置出现 timestep-too-small；放宽设置对自身严格参考最大偏差约 5.9 mV，因此双方统一采用当前严格且可完成的设置。优化 reuse 的瞬态同二进制一致性曾达到 1.68e-4 V，超过 1e-5 V 门槛，故不进入正式瞬态排名；DC reuse 保留。

## 可复现入口

```bash
python3 fair-comparison/scripts/generate_inputs.py --points 500 --seed 717
bash fair-comparison/scripts/run_matrix.sh
python3 fair-comparison/scripts/analyze.py
```

## 对实验清单问题的最终回答

### 拓扑复用是否真的带来加速？

结论是：拓扑复用机制确实工作，但不是对所有电路和分析都必然加速。第一轮 550 管反相器链 DC 中，NGSPICE independent 为 34.563370 s，reuse 为 33.093501 s，获得 1.044 倍加速；内部统计显示 500 次 setup 中 499 次为 reuse，KLU symbolic 也复用 499 次。两者最大电压差仅 1.38362e-14 V，因此这不是以错误结果换取的速度。

第二轮 580 管加法器的 500 点 end-to-end DC 中，优化 NGSPICE independent 为 46.352922 s，reuse 为 56.278201 s；reuse 相对 independent 的速度比为 0.824 倍，即慢约 21%。二者 DC 最大差约 1e-15 V，故数值正确性没有问题。由此应将结论表述为：复用能消除结构性初始化，但收益取决于该部分在总时间中的占比以及复用管理成本。

### HSPICE `.alter` 是否存在复用或缓存？

存在明确的批处理加速证据，但不能仅据此断言 HSPICE 复用了拓扑矩阵。第二轮 500 点 end-to-end DC 中，HSPICE independent 为 262.516055 s，`.alter` 为 126.874358 s，约快 2.07 倍；20 点 end-to-end transient 中，independent 为 38.651198 s，`.alter` 为 20.961318 s，约快 1.84 倍。两种 HSPICE 模式的 DC 和 transient 输出均完全一致。

这证明 `.alter` 避免了大量进程启动、网表读取和重复批处理工作。由于 HSPICE 内部实现是专有的，且没有可直接验证的矩阵对象统计，严谨结论是：`.alter` 存在明显缓存或复用效果，但不足以确认其复用了稀疏矩阵或 symbolic factorization。

### NGSPICE 在什么规模下超过 HSPICE？

必须按分析类型回答。

- DC：在本实验的全部实测规模 1、10、50、100、200、500 中，NGSPICE independent 和 reuse 都快于 HSPICE independent 与 `.alter`；首次实测领先点为 N=1。500 点 end-to-end DC 中，official NGSPICE independent 为 46.295444 s、optimized independent 为 46.352922 s、HSPICE `.alter` 为 126.874358 s、HSPICE independent 为 262.516055 s。optimized independent 相对 HSPICE independent 快约 5.66 倍。
- 严格 transient：在实测至 20 点的范围内，NGSPICE 未超过 HSPICE。20 点 end-to-end transient 中，optimized NGSPICE independent 为 300.961207 s，HSPICE independent 为 38.651198 s，HSPICE `.alter` 为 20.961318 s。线性拟合的稳态斜率分别约为 15.066、1.934、1.003 s/点；NGSPICE 的每点成本已经更高，因此继续增大点数不会通过摊薄启动成本形成有利交叉点。

### 正确性、内存和瓶颈

第二轮 DC 的 HSPICE 与 official NGSPICE 最大差为 5.1e-14 V；瞬态的 640 个稳定数字逻辑采样全部一致。瞬态跨模拟器在开关边沿的最大差为 0.771821 V，median 为 9.8106e-7 V、P95 为 1.2802 mV，因此瞬态速度比较应理解为相同公共模型卡、容差和输出工作量下的实际实现性能比较，而不是逐点波形完全相同的比较。500 点 DC 的峰值 RSS 约为 HSPICE 41.8--45.5 MiB、NGSPICE independent 11.9 MiB、reuse 14.9 MiB。

严格瞬态下 NGSPICE 的主要瓶颈不是进程启动，而是 BSIM4 器件计算、时间步控制、Newton 迭代、矩阵数值分解和线性求解；这解释了 HSPICE 在该工作负载中的明显优势。

## 补充解释：两种电路为何得到不同的复用效果

### 两种电路的工作量不同

虽然两轮电路均约为 550--580 管，但晶体管数量不能直接代表求解难度。550 管反相器链由 25 路规则的 11 级链组成，矩阵结构规整、器件连接重复，单参数点的求解相对简单；其成本中重复建拓扑、创建设备和矩阵初始化所占比例较高，因此跳过 setup 和 symbolic 有可见收益。

580 管加法器包含 XOR、NAND、进位链和多级缓冲；节点扇入/扇出、关键路径和器件尺寸更复杂，尤其在严格瞬态时有多个节点同时切换。此时主要成本转向器件模型计算、Newton 迭代、矩阵数值分解和时间步推进，拓扑复用不能消除这些每点必需工作。

```text
独立运行 = 进程启动 + 网表解析 + setup + symbolic + 每点数值求解
拓扑复用 = 一次启动/setup/symbolic + 每点参数更新 + 状态清理 + 每点数值求解
```

第一轮前四项的比例较高，故复用略有收益；第二轮数值求解占比更高，可节省的结构性开销比例变小。

### 为什么复用在第二轮可能减速

复用并非免费跳过初始化。`batchparambind` 需要查找和绑定可变参数字段；`batchparam` 要在每点写入参数；参数变化后需要使受影响模型、器件和矩阵数据失效；下一点前还要清理上一点的解向量、迭代状态、收敛标志和分析状态。`batchrun` 另有任务调度、结果收集和内部统计开销。

模型参数变化后，BSIM4 仍要重新计算大量尺寸相关和温度相关数据。KLU 的 symbolic 结构可以复用，但矩阵数值每点都变，numeric factorization、LU 和 solve 仍必须执行。因此，实际可能满足：

```text
节省的 setup + symbolic 时间
<
参数绑定 + 参数写入 + 状态清理 + 批处理管理开销
```

第二轮 DC 中 optimized independent 的每点成本仅约 0.09 s；即使复用节省若干毫秒 setup，批处理管理只要增加更多毫秒，端到端总时间就会变长。这并不说明拓扑复用设计错误，而是说明在该电路和分析条件下，可复用部分不是主要瓶颈。

此外，优化 reuse 的瞬态同二进制波形差曾达到 1.68e-4 V，超过 1e-5 V 门槛，故已从正式瞬态排名中排除。这提示瞬态状态清理尚未与全新进程完全等价，不能用该结果宣称性能优势。

一句话总结：拓扑复用只节省结构性初始化，不节省每个参数点必需的 BSIM4 计算、数值分解和迭代；当后者占主导，或复用管理成本较高时，复用可能没有收益甚至减速。
