# 第三轮：并行 worker、批长度与分析复杂度

完成正式记录 872 个，汇总单元 329 个。

## 结果口径

- 强扩展固定 1000 点，比较同一批任务的完成时间。
- 弱扩展每 worker 固定 1000 点，比较整机总吞吐和并行效率。
- `effective_workers` 小于请求 worker 时，表示任务数不足以让所有 worker 都有工作。
- HSPICE 许可证排队属于端到端时间；共同 worker 上限内的记录用于严格公平比较。

## 交叉点

- `dc/end_to_end` complexity=21 `ng_reuse_vs_hspice_alter`：首次实测 1，speedup=2.5045120666290783。
- `dc/end_to_end` complexity=21 `official_ng_vs_hspice_ind`：首次实测 1，speedup=5.591043951199506。
- `dc/end_to_end` complexity=21 `optimized_vs_official`：首次实测 1，speedup=1.0013336400174668。
- `dc/end_to_end` complexity=21 `reuse_vs_optimized`：首次实测 64，speedup=1.2143590411413927。
- `dc/end_to_end` complexity=101 `ng_reuse_vs_hspice_alter`：首次实测 1，speedup=1.984334059555113。
- `dc/end_to_end` complexity=101 `official_ng_vs_hspice_ind`：首次实测 1，speedup=9.105082890486624。
- `dc/end_to_end` complexity=101 `optimized_vs_official`：首次实测 8，speedup=1.0108019853051107。
- `dc/end_to_end` complexity=101 `reuse_vs_optimized`：首次实测 not_observed，speedup=。
- `dc/solver_only` complexity=5 `ng_reuse_vs_hspice_alter`：首次实测 1，speedup=2.891569033108945。
- `dc/solver_only` complexity=5 `official_ng_vs_hspice_ind`：首次实测 1，speedup=4.9490689300728405。
- `dc/solver_only` complexity=5 `optimized_vs_official`：首次实测 1，speedup=1.0025695000857409。
- `dc/solver_only` complexity=5 `reuse_vs_optimized`：首次实测 1，speedup=1.0936496919014334。
- `dc/solver_only` complexity=101 `ng_reuse_vs_hspice_alter`：首次实测 1，speedup=1.9748475426101146。
- `dc/solver_only` complexity=101 `official_ng_vs_hspice_ind`：首次实测 1，speedup=9.146194709004009。
- `dc/solver_only` complexity=101 `optimized_vs_official`：首次实测 4，speedup=1.001067116969467。
- `dc/solver_only` complexity=101 `reuse_vs_optimized`：首次实测 not_observed，speedup=。
- `tran/end_to_end` complexity=4 `official_ng_vs_hspice_ind`：首次实测 not_observed，speedup=。
- `tran/end_to_end` complexity=4 `optimized_vs_official`：首次实测 1，speedup=1.0016571313376523。
