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
