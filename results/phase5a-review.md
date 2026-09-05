# Phase 5A：固定标量势上的 spinor 原型

**工程验收 PASS；数值结论 REVIEW_REQUIRED，等待人工复核。**
本轮完成一次新的 B0 标量 DFTK SCF，并在同一进程的最终 `scf.ham` 上真实求解双分量本征问题。
没有实现 SOC、自旋耦合赝势、spinor SCF 或新的总能量闭环。

- Base：`47159d7b28f01a86f26425183803ee31cb2d2f70`。
- 分支：`codex/phase5a-spinor-prototype`；从该 base 新建，起始工作区干净。
- 新运行：`b0-20260905T104910Z`，实际开始/结束为 2026-09-05 10:49:36.551 / 10:50:02.599 UTC。
- [完整真实结果](phase5a/real-b0.json)、[运行日志](phase5a/real-b0.log)、[文件与原始轨道 hash 清单](phase5a/evidence-manifest.json)。
- 执行时 HEAD 仍为 base；实际执行的新增脚本、模块和容差文件用 SHA-256 标识，全部与交付文件一致。
  普通提交完成后的新 SHA 在交付回复中提供，不为包含自身 SHA 而 amend。

## 实现与边界

[设计说明](../prototypes/spinor/README.md)给出了固定源码接口证据和可替换的原型布局。
新模块使用 `Psi[component,G,state]`，展平行为 `component+ncomp*(G-1)`，对应 `kron(Hscalar,Icomp)`。
组件容器和标量提升经 ncomp=1/2/3 人工测试；实际 Si 限定 ncomp=2。

`ComponentOperator` 持有真实 `HamiltonianBlock`，逐分量调用现有标量 `mul!`。
每次仅分配与轨道块同阶的连续数组，未构造真实 Si 的 `2NG×2NG` 稠密 Hamiltonian。
复数向量、多列和非连续视图均测试；维度错误及输入/输出重叠明确拒绝，输入保持不变。
正定动能预条件器对两分量使用同一 `T_G+1 Ha` 分母；没有改写 DFTK 或底层求解器方法。

直接调用固定版本低层 `DFTK.lobpcg_hyper`；没有绕过高层标量包装器的 NG 检查。
标量高层包装器仅用于最终 H 的标量参考态。FFT 适配复用现有周期 Bloch `u` 变换，
没有额外乘 `exp(ik·r)`；倒空间总分量范数等于 `dvol*sum(abs2,u)`，不是每个分量各自归一到 1。

新增局域 Pauli 作用仅用于 synthetic algebra tests：`V12=Bx-im*By`、`V21=Bx+im*By`。
它没有接入 Si Hamiltonian，不表示 SOC 或新的物理磁场计算。

## 新测试及运行

以下均使用冻结 workbench Project/Manifest，新 Julia 进程、现有下载缓存、离线包模式，
`JULIA_LOAD_PATH=@:@stdlib`，Julia/OMP/BLAS 各一线程。实际加载身份先比较真实路径，再对公开证据脱敏。
`JULIA_DEPOT_PATH` 指向已经安装完整依赖的缓存；不在公开命令中保存私人绝对路径。

| 操作 | 实际命令（仓库根目录） | 退出码 / 结果 | 日志或记录 |
|---|---|---|---|
| 新增单元测试 | `julia --startup-file=no --project=environment/workbench tests/spinor/runtests.jl .work/phase5a-preflight` | 0；544/544 PASS | [unit-tests.log](phase5a/unit-tests.log) |
| B0 接口预检，无 SCF | `julia --startup-file=no --project=environment/workbench scripts/run_spinor_b0.jl --preflight .work/phase5a/preflight-20260905-a` | 0；PASS；SCF NOT_RUN | [JSON](phase5a/interface-preflight.json)、[日志](phase5a/interface-preflight.log) |
| 唯一真实 B0 运行 | `julia --startup-file=no --project=environment/workbench scripts/run_spinor_b0.jl .work/phase5a/b0-20260905T104910Z` | 0；SCF、真实求解及工程门槛 PASS | [real-b0.log](phase5a/real-b0.log) |
| 新驱动帮助 | 上述驱动加 `--help` | 0；PASS | [日志](phase5a/cli-help.log) |
| 新驱动缺参 | 上述驱动不加参数 | 2；成功拒绝 | [日志](phase5a/cli-missing-arguments.log) |
| 复用已有目录 | 再请求已有真实运行目录 | 2；拒绝；原结果 hash 不变；没有再运行 SCF | [CLI 记录](phase5a/cli-checks.json)、[日志](phase5a/cli-existing-run.log) |
| 修改边界 | 逐字节比较 base 全部文件，并检查两个 checkout | 0；PASS | [source-boundary.json](phase5a/source-boundary.json) |
| 补丁格式 | `git diff --check` 与 `git diff --cached --check` | 0；PASS | 提交前执行 |

544 项是本轮 workbench 测试，不是上游 DFTK 测试。覆盖交错索引/共享存储、复数正交化、
独立 Kronecker oracle、真实固定 LOBPCG 的小型人工矩阵求解、正确 Hermiticity 公式、SU(2) 对易、
维度/alias/输入不变性、FFT 往返/Parseval/复内积，以及独立平面波相位和 `1/sqrt(Ω)` 幅度检查。
人工 FFT 基底 NG=[87,83]，含非零 k 点；并不使用新赝势或 SCF。
密度测试覆盖四个纯态（含 `(1,i)/sqrt(2)` 的正 my）、Hermiticity/PSD、n≥|m|、
SU(2) 协变、等占据子空间幺正混合不变性，以及非零 By 的独立逐点矩阵作用和 `v±norm(B)` 本征值。

准备期两次候选缓存探测分别在缺少 ChainRulesCore、Roots 时停止，均未进入测试或 SCF；这些尝试记为 NOT_RUN，
未安装或升级依赖。改用已存在的匹配缓存后，完整测试、接口预检和正式计算各完成一次。
接口预检记录的是其执行时驱动 hash；正式计算前随后补充了初值记录、正交性门槛和异常阶段状态检查，
正式结果中的驱动 hash 与交付版本一致。数值阈值始终未改变。

首次 staged 格式检查发现新日志中的三处行尾空格；仅清理公开日志副本，保留原始日志及其 hash，随后两项 diff 检查均退出 0。

## 环境与输入身份

身份检查 PASS，详见[单元测试身份](phase5a/unit-test-identity.json)及真实结果的 `environment`。

| 项目 | 实测与冻结要求 |
|---|---|
| Julia | 1.12.7 |
| Active project | `<workbench>/environment/workbench/Project.toml` |
| Active Manifest | `<workbench>/environment/workbench/Manifest.toml` |
| Manifest SHA-256 | `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37` |
| DFTK 实际源码 | `<workbench>/.work/DFTK.jl/src/DFTK.jl`，0.8.0，`2f51b91213e26726fb9c6a17e5fae235a1412d01`，clean |
| DFTK UUID | `acf6eb54-70d9-11e9-0013-234b7a5f5337` |
| PseudoPotentialIO 实际源码 | `<workbench>/.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl`，0.3.3，`fec942781560c391f20214ba4cd85fb2431deb84`，clean |
| PseudoPotentialIO UUID | `cb339c56-07fa-4cb2-923a-142469552264` |
| 原 B0 case SHA-256 | `2f7aaf914ef6db5ccfa4c81a124b24c5bd32b27383d95c756c97266a22b63f65` |
| Si UPF SHA-256 | `686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805` |
| 真实结果 JSON SHA-256 | `7f9b541fbf690133828c6734b1b3c2f62bd4aad8039f2ecd7105a65a59d4e02e` |

使用原 a=10.26 bohr、两原子、Ω=270.011394 bohr³、30 Ha、显式八点及空间权重 1/8，
scalar NC Si UPF、lda_x+lda_c_pw、NLCC、零温、非磁性、8 电子，无空间或 k 点约化。
实际 FFT 网格 [40,40,40]。SCF 容差 1e-8，固定对角化容差 1e-10 Ha，seed=0，
7 次 SCF 迭代后密度残差 2.289809609576421e-9。
原生标量 SCF 总能量 **−8.42888453274439 Ha/cell**，仅保存为上下文。

## 真实双分量求解证据

标量参考态为每点 8 个目标态+3 个辅助态；spinor 为每点 16 个目标态+6 个辅助态。
两者求解容差均为 1e-10 Ha；最大迭代数分别 150、300。spinor 初值使用 seed 53001–53008 的
独立 ComplexF64 Gaussian 随机矩阵及 thin QR，未使用已收敛标量态初始化。
初始 QR 最坏 Gram 范数为 1.3431367972177186e-14，两个分量均非零且有非零虚部；求解器保留了初始数组。

| k 序号 | 分数坐标 | NG / spinor 维度 | 迭代数 | 求解器列 matvec | 16 态最大直接残差 (Ha) |
|---|---|---|---:|---:|---:|
| 1 | (0,0,0) | 2085 / 4170 | 29 | 610 | 8.69758e-11 |
| 2 | (0,0,−½) | 2120 / 4240 | 37 | 661 | 9.70251e-11 |
| 3 | (0,−½,0) | 2120 / 4240 | 40 | 680 | 9.77654e-11 |
| 4 | (0,−½,−½) | 2100 / 4200 | 50 | 795 | 9.38191e-11 |
| 5 | (−½,0,0) | 2120 / 4240 | 37 | 661 | 9.90130e-11 |
| 6 | (−½,0,−½) | 2100 / 4200 | 48 | 782 | 7.69894e-11 |
| 7 | (−½,−½,0) | 2100 / 4200 | 51 | 797 | 9.89469e-11 |
| 8 | (−½,−½,−½) | 2120 / 4240 | 39 | 674 | 9.04681e-11 |

5660 个求解器列 matvec 与组件算符计数一致，底层标量列调用数恰好为其两倍。
直接残差核对每点另外调用 16 列，单独计数。完整 JSON 保留全部 **128 个直接 spinor 残差**、
64 个标量残差、每点迭代数、调用数、所有目标本征值、辅助本征值及两分量逐态范数。
求解器历史可能含锁定态的零槽；验收使用直接重算的 `norm(H*x-lambda*x)`，不使用这些零值。

只在求解结束后，将重复标量谱作为 oracle。占据子空间用投影泄漏和重叠奇异值比较，未要求简并波函数逐个相同：
最大泄漏 Frobenius 范数 1.3610313307857365e-10，重叠奇异值偏离 1 最大 4.218847493575595e-15。
这是额外诊断，没有事后为它选择通过阈值。

## 预声明门槛与实测值

具体范数和接近零处理在[容差文件](../prototypes/spinor/tolerances.toml)及设计说明中，数值门槛在真实计算前固定。
以下是 Float64/ComplexF64 原型工程检查，不是连续极限或实验精度声明。

| 检查 | 实测 | 门槛 | 状态 |
|---|---:|---:|---|
| 16 个 spinor 态与重复标量谱最大差 (Ha) | 7.32747e-15 | 1e-8 | PASS |
| 全部目标 spinor 最大直接残差 (Ha) | 9.90130e-11 | 1e-9 | PASS |
| 标量参考最大直接残差 (Ha) | 9.85355e-11 | 1e-9 | PASS |
| spinor `norm(X'X-I)` | 2.92867e-14 | 1e-9 | PASS |
| 标量 `norm(X'X-I)` | 4.52267e-15 | 1e-9 | PASS |
| 两表示中最大电子数绝对误差 | 3.55271e-15 | 1e-8 | PASS |
| spinor / 同一最终 H 标量密度相对 L2 差 | 2.29530e-11 | 1e-7 | PASS |
| 实测 `norm(m)/norm(n)` | 3.37050e-12 | 1e-7 | PASS |
| 固定 H 占据态期望值差 (Ha/cell) | 1.01308e-15 | 1e-7 | PASS |
| 标量期望值与占据本征值和差 (Ha/cell) | 2.70617e-16 | 1e-7 | PASS |
| spinor 期望值与占据本征值和差 (Ha/cell) | 1.38778e-16 | 1e-7 | PASS |

标量占据容量 2、每点 4 个满占据态；显式 spinor 容量 1、每点 8 个满占据态。
所有额外态占据为零，权重和为 1，两者加权占据数均为 8。
全局有隙检查通过：标量/spinor 采样网格 gap 分别 0.015264107370228014 / 0.015264107370227181 Ha；
这仅是 B0 采样下允许固定占据的检查，不建立 k 点收敛。

密度从实际求得轨道分别 IFFT 并构造，未复制标量密度、未强制 m=0。
实空间积分电子数为标量 8.000000000000002、spinor 8.000000000000004。
独立标量密度适配与 DFTK.compute_density 的相对 L2 差为 3.08745e-16。
spinor R 的 Hermiticity 最大误差为 0，网格最小 n−|m| 为 0.0010395051531402635。
积分 Pauli 分量为 [3.42251e-15, −3.19009e-15, −3.15461e-16]；未解释为含电子磁矩符号或 μB 的磁化。

与保存的 SCF rho 分开比较：最终 H 标量重构 / SCF rho 的相对 L2 差为 2.77674e-10，
spinor / SCF rho 为 2.96554e-10。这些有限 SCF 差异未冒充同一 H 的严格参考。

固定 H 占据期望值：标量 **0.056942367394941226**、spinor **0.05694236739494021 Ha/cell**。
它们是带能，与上述原生 DFT 总能量含义不同，没有向总能量加入任何新修正。

## 审查问题、剩余事项和停止点

1. **真实实现**：组件表示、矩阵自由算符提升、复数双分量迭代求解、FFT 适配、明确容量的固定有隙占据、
   由实际轨道构造 R/n/m，以及固定 H 占据期望值比较。
2. **标量适配部分**：动能、局域势、非局域赝势的物理作用仍是现有标量 HamiltonianBlock；FFT 与底层 eigensolver 复用冻结 DFTK。
3. **16 态是真实求解**：八个 2NG 维算符、独立复数初值、29–51 次迭代、逐态直接残差及 matvec 证据齐全；重复谱只用作 oracle。
4. **复数与 sigma_y**：一般非同分量复数数据、非零 By、正 my 的 y+ 态及独立矩阵参考测试通过。
5. **显式残差**：全部 128 个目标 spinor 态通过原门槛，无失败态被删除或重新定义。
6. **独立密度与电子数**：来自实际 spinor 轨道及容量 1 的占据；两表示仍各为 8 电子；m 由公式实算。
7. **待讨论的上游接口**：组件布局是否接纳、组件原生 FFT/算符接口、通用 band/occupation 容量、避免组件复制的性能策略，
   以及未来 spinor/noncollinear 密度与能量泛函接口。本轮不宣称维护者接受任何 API，也未发送上游消息。
8. **为什么不是 SOC/SCF**：真实算符没有自旋非对角块或 FR projector，未更新 spinor 密度驱动的势，也没有 spinor 能量泛函闭环。

`spinor_scf_status=NOT_IMPLEMENTED`；`spinor_total_energy_status=NOT_IMPLEMENTED`。
SOC、FR 非局域投影、非共线 LSDA、力/应力、磁对称性、MLP、GPU 均未实现。
QE、C3/额外 cutoff 或 k 扫描、完整 DFTK 上游测试、旧 Phase 4A/4B/4C 测试套件均 **NOT_RUN**。
没有修改旧代码，因此无受影响的旧测试需要重跑；旧 Phase 4C 91/91、历史 minimal 1387/1387 均不计入本轮结果。

无遗留数值 FAIL 或 BLOCKED。base 的 **215 个已跟踪文件逐字节不变**；冻结 checkout 保持原 commit 且 clean，
包括 source lock、环境、保护检查、FR 验证器、历史配置、报告与结果。原始轨道约 25.7 MB 仅留在忽略目录，
公开证据约 63 kB；不提交 UPF、波函数、稠密矩阵或缓存。公开文件和原始文件 hash 分别列在证据清单。

仅以普通提交交付当前新分支，不推 main、不创建 PR、不合并、不发布上游留言。
当前工程结果支持进入人工架构与数值审查；**在此停止，不自动进入 Phase 5B**。
