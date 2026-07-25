# 550 管 BSIM4 拓扑复用性能实验报告

## 实验配置

- 电路：25 路 × 11 级 CMOS 反相器链，共 550 个 BSIM4 MOSFET。
- 参数：500 个固定种子 Latin hypercube 点，每点同时改变 14 个参数。
- 分析：25°C，VIN 0–1.8 V、步长 0.1 V 的 DC 扫描。
- 规模：1、10、50、100、200、500；单点 5 次，其余 3 次并取中位数。
- 执行：单线程并固定 CPU；比较 HSPICE independent、HSPICE `.alter`、NGSPICE independent、NGSPICE topology reuse。

## 500 点核心结果

| 方案 | 中位总时间 (s) | 平均每点 (s) | 峰值 RSS (KiB) |
|---|---:|---:|---:|
| hspice_independent | 119.421813 | 0.23884363 | 58084 |
| hspice_alter | 54.578790 | 0.10915758 | 60200 |
| ngspice_independent | 34.563370 | 0.06912674 | 10964 |
| ngspice_reuse | 33.093501 | 0.06618700 | 15816 |


## 加速比与交叉点

- 500 点 NGSPICE topology reuse / NGSPICE independent：`1.044×`。
- 500 点 HSPICE `.alter` / HSPICE independent：`2.188×`。
- 500 点 NGSPICE topology reuse / HSPICE independent：`3.609×`。
- 500 点 NGSPICE topology reuse / HSPICE `.alter`：`1.649×`。
- 首次实测超过 HSPICE independent：`1`。
- 首次实测超过 HSPICE `.alter`：`1`。
- 相对最佳 HSPICE 方案的主要交叉点：`1`。

## HSPICE `.alter` 判断

500 点加速比为 `2.188×`，拟合后的 `.alter`/独立模式稳态斜率比为 `0.454`；read 阶段总时间比为 `2.945`，setup 阶段总时间比为 `0.513`。按预注册规则，结论为：**总时间明显降低，但阶段日志仍显示逐点 read/setup，不能据此认定拓扑矩阵被复用**。

## NGSPICE 复用证据与瓶颈

- 500 点共调用 setup `500` 次，其中复用 `499` 次；KLU symbolic reuse 为 `499` 次。
- `CKTload` 累计 `42296` 次，耗时 `26.334 s`，约占总时间 `79.6%`。
- 14 个逻辑参数产生 `280000` 次直接写入，耗时 `4.755 s`，约占总时间 `14.4%`。
- 因 setup 与 symbolic 已几乎完全复用，后续主要瓶颈是 BSIM4 矩阵装载、数值分解及大量参数扇出写入，而不是拓扑初始化。

## 线性拟合

| 方案 | 估计初始化时间 (s) | 稳态每点斜率 (s/点) |
|---|---:|---:|
| hspice_independent | 0.070064 | 0.23874916 |
| hspice_alter | -0.537544 | 0.10828624 |
| ngspice_independent | 0.029393 | 0.06908634 |
| ngspice_reuse | 0.022570 | 0.06614826 |


## 数值一致性

| 对比 | 样本数 | 最大绝对差 | P95 绝对差 | 最大相对差 |
|---|---:|---:|---:|---:|
| ngspice_independent vs ngspice_reuse | 10000 | 1.38362e-14 | 1.30104e-15 | 8.32026e-07 |
| hspice_independent vs hspice_alter | 10000 | 0 | 0 | 0 |
| hspice_independent vs ngspice_independent | 10000 | 0.0497 | 0.0401 | 0.0518331 |


同模拟器优化前后通过严格门槛后才纳入性能结论。跨模拟器误差只用于描述 BSIM4 实现差异，不作为复用正确性的单一判据。

## 文件索引

- `data/raw/`：逐次 JSON、压缩模拟器日志和系统信息。
- `data/summary/`：计时、加速比、误差和线性拟合 CSV。
- `figures/`：总时间、每点时间、加速比和峰值内存曲线。
- `params/points.csv`：全部 500 个参数点。
- `netlists/`：独立网表、HSPICE `.alter` 网表和 NGSPICE batch 命令。
