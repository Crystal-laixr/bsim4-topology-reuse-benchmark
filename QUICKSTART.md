# 快速上手与复现指南

## 1. 任务是什么

项目研究的是：当大量 SPICE 仿真具有相同器件连接关系、仅数值参数变化时，能否在 NGSPICE 中复用已建立的电路、矩阵结构和 KLU 符号对象，从而减少重复初始化，并与 HSPICE independent、HSPICE `.alter` 和官方 NGSPICE 做公平比较。

公司侧后续工作的合理边界是：

1. 阅读并修改 `upstream/ngspice_for_sizing/` 中的优化 NGSPICE C 源码。
2. 用仓库提供的固定电路、参数、模型、误差门槛和计时脚本做回归测试。
3. 对比修改前后的正确性、耗时、内存和复用计数，确认优化没有改变数值结果或拓扑安全边界。
4. 输出代码改动、运行环境、原始 JSON、汇总 CSV/图表、门槛检查和结论说明。

不需要从公开仓库获取 HSPICE 程序或许可证；这些必须由执行单位在本地合法配置。

## 2. 三轮实验分别回答什么

| 轮次 | 电路与范围 | 主要问题 | 推荐用途 |
|---|---|---|---|
| 第一轮 | 550 管规则反相器链，DC | 拓扑复用机制能否工作、在轻量规则电路上是否加速 | 快速理解优化机制 |
| 第二轮 | 580 管 16-bit ripple-carry adder，DC + transient | 在统一 BSIM4 模型、精度和单核条件下，NGSPICE/HSPICE 如何公平比较 | 公司复现与修改后的主回归基准 |
| 第三轮 | 第二轮电路，多 worker、强/弱扩展 | 多进程吞吐、批长度、复杂度和 HSPICE 许可证上限如何影响端到端时间 | 并行与部署评估，非首次上手必跑项 |

第一次接手建议先读 [第二轮报告](fair-comparison/REPORT.md)，再读 [第一轮报告](REPORT.md) 理解机制，最后读 [第三轮报告](fair-comparison/parallel-scaling/REPORT.md) 理解并发和许可证结论。

## 3. 仓库中已经包含什么

- 优化 NGSPICE 源码以 Git submodule 固定在提交 `828d455865fe1b530672de4be6519703826057be`，其官方基线为 ngspice `pre-master-47` 提交 `eb68de42d0ca8c97efd92f8d7528e7e7841f5fc9`。
- 三轮实验的网表生成器、模型卡、固定参数点、运行脚本、门槛检查和分析脚本。
- 已发布的原始记录、汇总 CSV、图表和报告，可在没有 HSPICE 的机器上直接审阅和重新分析。
- 不包含 HSPICE binary、许可证文件、许可证服务日志、账号凭据或公司内部路径配置。


## 4. 获取源码

推荐 Linux x86_64、Ubuntu 24.04 或 WSL2 Ubuntu 24.04。CentOS/RHEL 也可以，但包名和工具版本需要按系统调整。

在 CentOS 7/RHEL 7 等旧系统上，先确认 `gcc --version` 可执行；若编译器来自 Software Collections，需要在同一 shell 中启用对应 devtoolset，例如 `source /opt/rh/devtoolset-9/enable`，再运行构建脚本。

源码自测需要 Python 3.9 或更高版本。脚本会优先寻找 `python3.12`、`python3.11`、`python3.10`、`python3.9`，也可显式设置 `PYTHON_BIN=/path/to/python3.12`。系统默认 `python3` 较旧时，不要让它覆盖新版本解释器。

```bash
git clone --recurse-submodules https://github.com/Crystal-laixr/bsim4-topology-reuse-benchmark.git
cd bsim4-topology-reuse-benchmark
git submodule status
```

如果此前没有使用 `--recurse-submodules`：

```bash
git submodule update --init --recursive
```

`git submodule status` 应显示优化源码提交 `828d455...`。公司若要修改优化逻辑，应在 `upstream/ngspice_for_sizing/` 对应的源码仓库中建立自己的分支，并同步更新本仓库的 submodule 指针；不要只复制一个本地 build 目录。

## 5. 构建优化 NGSPICE

优化源码自带构建和单元验证入口：

```bash
sudo apt update
sudo apt install -y build-essential autoconf automake libtool bison flex \
    libreadline-dev libncurses-dev libfftw3-dev python3
cd upstream/ngspice_for_sizing
bash tools/build_and_verify.sh --quick
cd ../..
```

成功后可执行文件位于 `upstream/ngspice_for_sizing/build/src/ngspice`。`--quick` 会验证编译、参数绑定、一对多传播和 Python 单元测试；需要验证优化源码自身的完整并行示例时再运行：

```bash
cd upstream/ngspice_for_sizing
bash tools/build_and_verify.sh --full
```

公平对照需要用相同参数分别构建官方与优化 NGSPICE。仓库提供了标准脚本，它会把官方源码固定到 `eb68de42...`，并以 `--with-x=no --disable-xspice --disable-cider CFLAGS=-O2` 构建两者：

```bash
bash fair-comparison/scripts/setup_binaries.sh
```

官方源码默认放在未跟踪的 `upstream/ngspice_official/`，优化源码使用已固定的 submodule。脚本最后会打印两个 binary 路径，把它们填入 `.benchmark-env`。如果公司已有源码目录，可通过 `OFFICIAL_ROOT`、`OPTIMIZED_ROOT` 和 `BUILD_JOBS` 覆盖。正式运行前记录两者的 commit 和 SHA-256。

## 6. 配置本机路径与许可证

仓库脚本不再依赖作者服务器的绝对路径。复制模板并只修改本机文件：

```bash
cp .benchmark-env.example .benchmark-env
```

至少配置以下变量：

- `PYTHON_BIN`：Python 3，可执行文件路径。
- `NGSPICE_OFFICIAL_BIN`：官方 NGSPICE 可执行文件。
- `NGSPICE_OPTIMIZED_BIN`：优化 NGSPICE 可执行文件。
- `HSPICE_BIN`：本地合法安装的 HSPICE 可执行文件。
- `HSPICE_ENV_FILE`：可选，执行单位自己的许可证环境脚本。
- `HSPICE_CONCURRENCY_CAP`：允许本实验占用的许可证并发数；不确定时保持 `1`。

`.benchmark-env` 已加入 `.gitignore`。运行脚本只读取该环境，不会启动 `lmgrd`，也不会复制或归档 license 文件。

系统还需要 GNU `/usr/bin/time`、`taskset`、`sha256sum` 和常见 Linux 系统工具。完整矩阵会占用较长时间和大量 HSPICE license，务必先跑 smoke test。

## 7. 推荐复现顺序

### 7.1 不运行模拟器，只核对已发布结果

分析脚本只使用 Python 标准库，可以基于仓库中已提交的数据重新生成汇总：

```bash
python3 scripts/analyze.py
python3 fair-comparison/scripts/analyze.py
python3 fair-comparison/parallel-scaling/scripts/analyze.py
```

第三轮自动生成的简表写入 `fair-comparison/parallel-scaling/data/summary/generated_report.md`，不会覆盖人工整理的综合报告。

### 7.2 构建优化源码并验证其自测

先执行第 5 节的 `tools/build_and_verify.sh --quick`。这是定位编译环境或源码修改错误最快的入口，不依赖 HSPICE。

### 7.3 第二轮 smoke test：公司首次复现的推荐入口

```bash
bash fair-comparison/scripts/run_matrix.sh --smoke
```

该步骤会生成输入，分别运行 DC/transient、solver-only/end-to-end 的小规模样例，并执行结构与数值检查。通过后再考虑完整矩阵：

```bash
RESUME=1 bash fair-comparison/scripts/run_matrix.sh
```

`RESUME=1` 会跳过已存在的有效输出，适合中断后继续。不要在没有确认许可证额度和预计时间前直接启动完整矩阵。

### 7.4 第一轮机制复现

```bash
python3 scripts/generate_inputs.py --points 500 --seed 717
bash scripts/run_matrix.sh
```

第一轮包含优化 NGSPICE 的 `batchrun`、setup/KLU symbolic reuse 计数和 HSPICE `.alter` 对照，适合解释“复用了什么”。

### 7.5 第三轮并行 smoke test

```bash
bash fair-comparison/parallel-scaling/scripts/run_matrix.sh --smoke
```

完整第三轮涉及 1 到 256 workers。公开结果采用了 [缩减范围](fair-comparison/parallel-scaling/REDUCED_SCOPE.md)，公司复现时应根据机器核数和许可证上限重新选择 workers，不应照搬 256 workers。运行完整并行矩阵前，先审阅脚本中的 worker/复杂度列表，并把 `HSPICE_CONCURRENCY_CAP` 设为获得授权的值。

## 8. 成功后看哪些输出

每一轮都采用相同的证据链：

- `params/`、`models/`、`netlists/`：输入、模型和生成后的网表。
- `data/raw/`：每次执行的 JSON、压缩工作目录和机器环境。
- `data/summary/`：门槛、计时、误差、加速比、交叉点和排名。
- `figures/`：汇总曲线。
- `REPORT.md`：实验解释与结论。

公司修改源码后，至少应比较：同模拟器修改前后最大绝对误差、返回码与门槛状态、总时间与每点时间、峰值 RSS、`setup_reuse`/`symbolic_reuse`/`lufac_calls` 等计数。只有正确性门槛通过后，性能变化才有意义。

## 9. 常见报错

### `... is not executable` 或仍找不到模拟器

确认已复制 `.benchmark-env.example` 为 `.benchmark-env`，变量指向真实可执行文件而不是目录。也可以临时指定其他配置：

```bash
BENCHMARK_ENV_FILE=/path/to/team.env bash fair-comparison/scripts/run_matrix.sh --smoke
```

### HSPICE license checkout 失败

这是本地安装或许可证环境问题，不应通过修改 benchmark 绕过。先在同一 shell 中直接执行 `$HSPICE_BIN -v`，再由管理员确认 license 变量、服务状态和允许并发数。

### 优化 NGSPICE 不认识 `batchrun`/`batchparam`

实际使用的不是本仓库 submodule 构建出的优化 binary，或 submodule 提交不正确。检查：

```bash
git -C upstream/ngspice_for_sizing rev-parse HEAD
"$NGSPICE_OPTIMIZED_BIN" -v
```

### 结果和已发布数字不同

先核对源码 commit、binary SHA-256、CPU、操作系统、编译选项、HSPICE 版本、KLU、线程环境和许可证排队。不同机器的绝对时间不应直接逐秒相等，更可靠的是数值门槛、方法排序、同机加速比和复用计数。
