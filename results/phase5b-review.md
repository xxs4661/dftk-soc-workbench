# Phase 5B：charge-only spinor SCF 与总能量闭环

**执行和本轮工程验收 PASS；数值结论 `REVIEW_REQUIRED`，等待人工复核。**
本轮从实际双分量轨道重构的价电子密度更新 Hartree/非磁性 LDA 势，完成 A/B 两次独立 spinor SCF、
各自额外的终点闭环映射，再执行一次独立原生 scalar C。没有使用历史密度或能量替代新运行。

- Base：`60140a4148a510f0b2eb36f7bf00d683f3105a9a`。
- 分支：`codex/phase5b-spinor-scf-energy`；起始工作区干净，从指定 base 新建。
- 唯一真实批次 run_id：`abc-20260905T130100Z`；实际顺序 **A → B → C → 有限差分**。
- 实际运行时间：2026-09-05 13:01:16.944 至 13:07:38.635 UTC；进程退出码 **0**。
- [完整结果](phase5b/real-abc.json)、[真实日志](phase5b/real-abc.log)、[逐轮表](phase5b/density-maps.csv)、
  [A 映射记录](phase5b/maps-A.jsonl)、[B 映射记录](phase5b/maps-B.jsonl)、[证据/hash 清单](phase5b/evidence-manifest.json)。
- 执行时 HEAD 为上述 base，11 个实际执行的驱动/模块/设置文件以 SHA-256 记录，全部与交付源码一致。
  本轮普通提交 SHA 在提交后的回复给出，不 amend 报告以加入自身 SHA。

## 实现范围与能量依据

[简短设计与固定源码依据](../prototypes/spinor/SCF-DESIGN.md)列出了各项允许轨道因子求值的接口及行号。
沿用 `Psi[component,G,state]`，展平 `component+2*(G-1)`，矩阵自由 `Hscalar[n] ⊗ I2`。
每个 k 点具有自己的 NG；spinor 每态容量为 1，8 个满占据态、16 个目标态及 6 个空辅助态，空间权重和为 1。

新增闭环由 workbench 管理：spinor 初值/轨道、实际本征求解、容量为 1 的占据、R/n/m、密度反馈和能量归属。
复用冻结 DFTK 的空间算符、FFT、低层 LOBPCG、Hartree、lda_x+lda_c_pw 与 NLCC。
`scf.jl` 不调用 scalar SCF；唯一原生 scalar 调用在独立 C 参考函数，且在 A/B 完成后执行。

能量桥接将 `chi=[Xup Xdown]`、`fchi=[f;f]` 作为空间密度矩阵因子。
这些列不单独归一化、不做 QR，也不按 scalar 容量 2 重算占据；电子数结合分量实际范数计算，仍为 8。
能量主路径内部从这些实际轨道重构 n，显式转成 `(40,40,40,1)`，只遍历一次七项能量。
外部指定的 expected_n 仅用于一致性检查，不能替换轨道密度；不支持或重复的 term、修改的泛函/缩放设置明确拒绝。

唯一支持的总能量为 T、AtomicLocal、AtomicNonlocal、Hartree、Xc、Ewald、PspCorrection 之和。
其中动能/非局域项是加权二次型；局域项使用显式密度；Hartree/XC 使用当前价电子 n；两个每胞常数各一次。
NLCC 由 DFTK TermXc 内部加入一次，Hartree、电子计数及 `integral(n*vxc)` 均仅使用价电子 n。
从同一 H[n] 的总局域势减去原子局域势和 Hartree 势取得 vxc，避免再次求值 XC。

主能量始终是 **E[Psi,n_out]**，不是与混合密度拼接的能量。
固定 H 带能是另一个量；双计数核对使用实际作用于当前轨道的 H[n_out]：
`Etotal = Eband_expect − EH − integral(n*vxc) + Exc + EEwald + EPspCorrection`。
没有使用旧 H[n_in] 的本征值和替代这个期望，没有加减 Phase 4C 的常数 C。

## 固定设置、独立初态和运行

[本轮设置](../prototypes/spinor/phase5b.toml)在真实运行前保存；SHA-256：
`34b013ee3ff65e9f666175c7fad064d6998f046187c9dfb0891d923b338c1f51`。门槛和 mixing 均未调整。
Float64/ComplexF64，alpha=0.3，最多 200 次映射（包括闭环），16+6 态，LOBPCG tol=1e-10 Ha、maxiter=300。

仍为原 B0：Si 两原子，a=10.26 bohr，Ω=270.011394 bohr³，30 Ha，显式 `{0,−1/2}³` 八点、每点权重 1/8，
lda_x+lda_c_pw、NLCC、零温、8 电子、无对称性约化、无 SOC/外磁场。FFT [40,40,40]，
NG=[2085,2120,2120,2100,2120,2100,2100,2120]，所有程序/BLAS/FFT/MPI 按一线程/一进程运行。

A 以 `DFTK.guess_density` 开始；初始化前后价电子数均为 8，明确记录的一次归一化系数恰为 **1.0**。
guess 最小密度为 0.006172865852287137。B 使用同一 guess 的规定余弦扰动，qbar=−3.6307939229858567e-17，
扰动 L2 范数 0.00401374828445403，最小密度 0.006111137193764266，积分仍为 8。
A/B 初始密度 hash 不同；独立随机 seed 分别为 54001–54008、55001–55008，首轮一般复数 QR 的两个分量均非零。
B 没有从 A 热启动；同一运行内部才使用上一映射轨道。C 用全新原生 guess、seed=0，密度容差收紧到 1e-9，
未修改历史 B0 case；其标量 8+3 态对角化容差仍为 1e-10 Ha。

| 运行 | 状态 | 普通迭代 / 额外闭环 | 总映射数 | 初始未混合残差 | 最终未混合残差 | 原生/轨道—密度总能量 (Ha/cell) |
|---|---|---:|---:|---:|---:|---:|
| A spinor | PASS | 52 / 1 | 53 | 0.1522167495910364 | 3.220091734766808e-11 | −8.428884532744394 |
| B spinor | PASS | 52 / 1 | 53 | 0.15226990456191916 | 3.233562468001258e-11 | −8.428884532744394 |
| C native scalar | PASS | 8 个原生 SCF 迭代 | 不适用 | 原生历史见 JSON | 4.720704502982586e-10 | −8.428884532744393 |

A/B 第 52 次候选残差分别为 8.539984451146579e-10、8.580223834514848e-10。
候选的 **n_out** 用于第 53 次闭环映射；最终结果属于这次新求解的轨道与自身密度，未丢弃闭环输出。
普通步骤使用线性混合；每轮同时记录 n_in、n_out、n_mixed、实际 n_next 的 hash、电子数、L2 范数和最小值。
未混合残差始终为 `sqrt(dvol)*norm(n_out−n_in)`；混合步长另记，不用于制造收敛。
没有逐轮裁剪、重归一化或强制对称化；负密度的舍入容许规则在设置文件中预先声明。

独立检查的 **104 条 n_next → 下一 n_in hash 链全部连续**，104 次势变化和固定复数探针 H 作用变化均非零。
实际算符尺寸随 k 变化为 4170–4240。A/B 每点每次求解分别用 1–49 / 1–48 次迭代；
求解器迭代总和为 5083 / 5441，求解器列 matvec 为 96916 / 100658。
这些是求解器范围的计数；输入 H 直接残差、自身密度 H 残差及探针诊断的作用另外记账，不混作速度比较。

## 原门槛与闭环核对

| 检查 | A 实测 | B 实测 | 门槛 |
|---|---:|---:|---:|
| 最终未混合密度 L2 残差 | 3.22009e-11 | 3.23356e-11 | 1e-9 |
| 全过程 H[n_in] 最大目标态直接残差 (Ha) | 9.99250e-11 | 9.99197e-11 | 1e-9 |
| 最终 H[n_out] 使用原 λ 的最大直接残差 (Ha) | 9.86306e-11 | 9.86020e-11 | 1e-7 |
| 全过程目标 `norm(X'X−I)` 最大值 | 3.10158e-14 | 3.17267e-14 | 1e-9 |
| 全过程快照最大电子数误差 | 2.13163e-14 | 1.59872e-14 | 1e-8 |
| 最终实测 `norm(m)/norm(n)` | 1.24914e-13 | 1.40820e-13 | 1e-7 |
| 与 C 原生密度相对 L2 差 | 2.53480e-11 | 2.53126e-11 | 1e-7 |
| 与 C 原生总能量绝对差 (Ha/cell) | 1.77636e-15 | 1.77636e-15 | 1e-7 |
| 与 C 最大能量分项差 (Ha/cell) | 4.14278e-11 | 4.14007e-11 | 1e-6 |
| 16 态与 C 重复 8 态原谱最大差 (Ha) | 6.49858e-12 | 6.48287e-12 | 1e-6 |
| 全过程同源分项/双计数检查最大误差 (Ha/cell) | 1.59872e-14 | 1.24345e-14 | 1e-9 |

全部 PASS。106 次映射共 **13,568 个目标态直接残差**均实际重算并检查。
原始逐态数据保留在忽略日志；公开逐轮记录保留每 k 点最大值、正交性和计数，最终完整逐态数据保留在完整结果 JSON。
最终 H[n_out] 的 Rayleigh 商及其残差另作诊断，明确不是新对角化本征值。

A/B 最终实空间电子数均为 8.000000000000002；C 为 8.0。
A−B 总能量差为浮点 **0.0 Ha/cell**（门槛 1e-7），密度相对差为 7.721674517024331e-13。
两者相对 C 最终 H 重构密度的差为 1.66204e-11 / 1.65963e-11；C 重构密度与原生 SCF rho 的差为 1.79842e-11，
两类标量密度参考没有混淆。C 最低 8 态最大直接残差为 5.240856816251668e-11 Ha。
所有谱比较使用原始能级，没有拟合或参考平移。

## 总能量分项与双计数

单位均为 Ha/cell；表中为便于阅读的数值，完整结果保留浮点精度。

| 分项 | A | B | C native scalar | 最大绝对 spinor−C 差 |
|---|---:|---:|---:|---:|
| Kinetic | 3.282760091406583 | 3.282760091406556 | 3.282760091365156 | 4.14278e-11 |
| AtomicLocal | −2.489569317114388 | −2.489569317114180 | −2.489569317088786 | 2.56022e-11 |
| AtomicNonlocal | 1.287700523240671 | 1.287700523240511 | 1.287700523261825 | 2.13132e-11 |
| Hartree | 0.628470707060561 | 0.628470707060514 | 0.628470707051577 | 8.98392e-12 |
| Xc | −3.133003612395216 | −3.133003612395190 | −3.133003612391559 | 3.65707e-12 |
| Ewald | −8.400464786186092 | −8.400464786186092 | −8.400464786186092 | 0 |
| PspCorrection | 0.395221861243487 | 0.395221861243487 | 0.395221861243487 | 0 |

首轮明显未自洽的 A/B 快照双计数误差分别为 3.55271e-15 / 0.0 Ha，最终为 7.10543e-15 / 1.06581e-14 Ha。
每轮还独立核对组件动能、实际非局域算符期望、原子局域密度积分、`1/2*integral(n*vH)`，及两个每胞常数。
XC 主求值每快照一次（指七项遍历中的 Xc term；不是声称 Libxc 内部只有一次函数调用）。
最终实际 H[n_out] 占据期望为 A **0.05694236776070763**、B **0.05694236776066082 Ha/cell**，
这是固定 H 带能，与上表负的 DFT 总能量明确分开。

## 有限能量—Hamiltonian 核对

取 A 最终 Γ 点态 1（占据）和态 9（空），先作 0.13 rad 的二维幺正旋转。
试验中心能量 −8.427768969068655 Ha/cell，解析导数 **0.01706572307529615 Ha/cell/rad**，
明显不为零；不是仅在驻点检查近零导数。中心 Gram 误差 6.86736e-15。

| h (rad) | 中心差分 (Ha/cell/rad) | `abs(numeric−analytic)/max(1,abs(analytic))` |
|---|---:|---:|
| 1e-3 | 0.017065711698016628 | 1.13773e-8 |
| 3e-4 | 0.01706572205032823 | 1.02497e-9 |
| 1e-4 | 0.017065722968112595 | 1.07184e-10 |

最小步长门槛 1e-6，PASS。每个 ±h 都重新计算对应轨道密度、Hartree、XC 和总能量；
其不同密度 hash 及两侧能量全部保存。解析路径独立作用当前中心 H[n]，未用差分表达式反推。
仅执行这三个预定步长，没有额外 SCF、步长优化或物理参数扫描。

## 测试、命令和身份

从仓库根目录运行；使用现有缓存的 `JULIA_DEPOT_PATH`，其私人绝对路径不发布。
统一设置 `JULIA_LOAD_PATH=@:@stdlib`、`JULIA_PKG_OFFLINE=true`，Julia/OMP/BLAS 各一线程。
macOS 的 MPI 初始化在获准的普通主机进程中运行。没有安装/升级或重建依赖。

| 检查 | 实际命令或入口 | 退出码 / 结果 | 证据 |
|---|---|---|---|
| 旧回归和新增测试 | `julia --startup-file=no --color=no --project=environment/workbench tests/spinor_scf/runtests.jl .work/phase5b-preflight/attempt-1` | 0；**544/544 + 228/228 PASS** | [日志](phase5b/tests.log)、[新测试数值](phase5b/new-test-evidence.json) |
| A/B/C 与有限差分 | `julia --startup-file=no --project=environment/workbench scripts/run_spinor_scf_b0.jl .work/phase5b/abc-20260905T130100Z` | 0；PASS | [真实日志](phase5b/real-abc.log) |
| 五种人工失败 | `tests/spinor_scf/failure_worker.jl` 的映射上限/对角化/NaN/占据/电子漂移注入 | 均为 1，当前 JSON 均 FAIL；这是负例测试通过 | [实际失败记录](phase5b/synthetic-failure-records.json) |
| 拒绝旧目录 | 同一人工 worker 请求已存在的 synthetic PASS 目录 | 2，旧结果字节不变 | 新测试记录及断言 |
| 独立证据核对 | 读取逐轮记录和四个首轮/闭环原始检查点，未新增 SCF 或对角化 | PASS | [映射审计](phase5b/independent-map-audit.json)、[原始数组审计](phase5b/independent-raw-audit.log)、[独立能量审计](phase5b/independent-energy-audit.json) |
| 源码/环境边界 | 逐字节核对 base 全部文件，检查冻结 checkout | 0；PASS | [边界检查](phase5b/source-boundary.json) |
| 格式检查 | `git diff --check`、`git diff --cached --check` | 0；PASS | 提交前执行 |

首次暂存格式检查退出 2：新公开 CSV 的 CRLF 行尾被识别为尾随空白；仅统一为 LF，
逐字段核对数值不变，更新公开 hash 后重新检查为 0。原始计算记录未改动。

新增测试包括一般复数/非单位分量因子、独立 XC/NLCC 对照、错误 double-core、term/占据/密度拒绝、
改变密度后的 Hartree/XC/H 探针、冻结 H/旧密度/交换归属、未混合残差与小 alpha、失败闭环继续反馈、
映射上限/NaN/漂移、等占据幺正混合和全局 SU(2) 不变性、非驻点有限差分，以及实际驱动失败发布边界。
人工能量快照及三个提前中止的故障 hook 都标为 synthetic，没有完成新的物理密度映射，不能充当 A/B/C 证据。
原 544 项是本轮实际重跑，不复用 Phase 5A 日志；全部为 workbench 测试，不冒充上游测试。

本回合曾被界面中断；恢复时核对到测试实际已正常结束，退出码 0，没有代码/环境故障或丢失修改。
真实 A/B/C 在恢复后才首次启动，无失败计算或重试。标量日志中的 `−Inf` 仅为 `log10(0)` 的能量变化显示，
不是非有限总能量；临时构造 H 的 Inf 占位未用作能量，所有结果 JSON 数值均有限。

实际身份均 PASS：Julia **1.12.7**；active project/Manifest 位于 `<workbench>/environment/workbench/`。
DFTK **0.8.0**，UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337`，实际加载
`<workbench>/.work/DFTK.jl/src/DFTK.jl`，commit `2f51b91213e26726fb9c6a17e5fae235a1412d01`，clean。
PseudoPotentialIO **0.3.3**，UUID `cb339c56-07fa-4cb2-923a-142469552264`，实际加载
`<workbench>/.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl`，commit `fec942781560c391f20214ba4cd85fb2431deb84`，clean。
真实路径比较先于脱敏，详见[测试身份](phase5b/test-identity.json)及真实结果 provenance。

| 文件 | SHA-256 |
|---|---|
| 冻结 Manifest | `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37` |
| 原 B0 case | `2f7aaf914ef6db5ccfa4c81a124b24c5bd32b27383d95c756c97266a22b63f65` |
| Si UPF | `686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805` |
| 完整真实结果 | `0e7c9a48fcc4bc8e947a33519a660c2df83fb75f923f674bc0f89d11b719091a` |

## 交付状态与停止

`spinor_scf_status=PASS`、`spinor_total_energy_status=PASS` 仅指本轮受限 workbench 原型。
`numerical_review_status=REVIEW_REQUIRED`；`soc_status=NOT_IMPLEMENTED`；
`noncollinear_lsda_status=NOT_IMPLEMENTED`；`upstream_native_spinor_support=NOT_IMPLEMENTED_BY_THIS_PHASE`。
忽略 m 的 charge-only LDA 不称为非共线 LSDA；实测 m 保留，没有人为清零。

无遗留 FAIL/BLOCKED。QE、C3、额外材料或 cutoff/k 扫描、完整上游套件均 **NOT_RUN**；
历史 1387/1387、91/91 均不计入本轮测试。没有进入 FR 投影子、SOC、力/应力或其他扩展。
base 的 **239 个已跟踪文件逐字节不变**，包括 Phase 4/5A 报告、脚本、测试、B0 配置、FR 验证器及冻结环境。
两个上游 checkout 原 commit/clean 状态不变，没有 monkey patch 或删除保护检查。

原始轨道/密度约 97.7 MB 仅留在忽略目录；公开约 1.2 MB 的精简逐轮记录、结果和日志，
原始/公开文件 hash 分开记录。精简只省略中间逐态大数组，保留逐轮 hash、能量、残差最大值和计数；
最终逐态结果完整保留。公开日志仅脱敏并清理行尾空格，不更改数值或历史证据。
实现与分析包含 Codex AI 协助，需仓库所有者进行数值与架构复核；不宣称维护者已接受布局/API。

仅创建普通提交并推送当前指定分支，不推 main、不创建 PR、不合并或发布上游留言。
完成本轮有限闭环检查后停止，等待人工审查。
