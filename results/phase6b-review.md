# Phase 6B：FR 完整 Hamiltonian 与轨道能量集成

**本轮固定范围的工程检查 PASS；数值结论为 `REVIEW_REQUIRED`，等待人工审查。**
真实 Mg 的三个固定密度 spinor 本征问题、当前轨道能量、自旋交叉项、双计数及有限差分均通过预声明门槛；原 Si 完整人工标量退化恢复原生 DFTK。
这些是未自洽试验体系上的接口一致性结果，不是自洽基态、平衡 Mg 晶相、物理收敛或 QE SOC 验证。

- Base：`1db8b61e7d962c7476b301e8a5be0be3725fbe6f`。
- 新分支：`codex/phase6b-fr-hamiltonian-energy`，从指定 base 创建，起始工作区干净；普通提交 SHA 在提交后回复中提供。
- 成功真实 run_id：`20260906T004533Z-real-2eb791c8`；实际执行时间 **2026-09-06 00:45:39.597–00:46:00.833 UTC**，退出码 **0**。
- [真实结果](phase6b/real-mg-si.json)、[日志](phase6b/real-mg-si.log)、[实际命令](phase6b/real-mg-si.command.json)、[48 个目标本征值及逐态残差](phase6b/mg-eigenpairs.csv)、[能量分项](phase6b/energy-terms.csv)、[差分数据](phase6b/finite-differences.csv)。
- 实现集中于 [common data / full-H / energy / variational / runtime checks](../prototypes/fr_integration/README.md)；沿用未修改的 Phase 5A 布局、FFT/密度和 Phase 6A 非局域算符。没有复制 Phase 5B SCF。

## 冻结身份与预声明配置

新 Julia 进程先检查实际加载路径的 realpath，再核对 UUID、版本、commit、checkout 状态；公开证据随后脱敏。
[环境记录](phase6b/real-environment.json)确认：

| 项目 | 实测身份 |
|---|---|
| Julia | 1.12.7；Julia / BLAS / FFT / MPI 均为单进程或单线程 CPU |
| active project | `<workbench>/environment/workbench/Project.toml` |
| actual Manifest | `<workbench>/environment/workbench/Manifest.toml` |
| Manifest SHA-256 | `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37` |
| DFTK | 0.8.0，UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337` |
| pathof(DFTK) | `<workbench>/.work/DFTK.jl/src/DFTK.jl` |
| DFTK commit | `2f51b91213e26726fb9c6a17e5fae235a1412d01`，clean，与 lock 一致 |
| PseudoPotentialIO | 0.3.3，UUID `cb339c56-07fa-4cb2-923a-142469552264` |
| pathof(PseudoPotentialIO) | `<workbench>/.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl` |
| PPIO commit | `fec942781560c391f20214ba4cd85fb2431deb84`，clean，与 lock 一致 |

只复用已有下载缓存，没有安装、升级或 resolve 依赖。新配置 [phase6b.toml](../prototypes/fr_integration/phase6b.toml) 于 **00:29:53.797530 UTC**、正式测试前保存，SHA-256 为 `d3036fed641ec460e8171cc5aaa098ab83bf82912ab104aad45ba8b343cd8b4f`；[预声明记录](phase6b/settings-before-tests.json)与成功运行 hash 一致，没有事后放宽容差或更换探针。

默认误差为 `norm(a-b)/max(norm(a),norm(b),1)`；两侧范数均小于 1 时等于绝对误差。自旋翻转另用真实信号范数作分母。FD 可辨识门槛预先固定为总导数 `1e-5`、NL 导数 `1e-10 Ha/rad`。

## 同源数据、单位、XC 与公共模型

| 输入 | SHA-256 | 原始事实与本轮用途 |
|---|---|---|
| 原 Mg FR NC | `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256` | Mg，full，has_so=true，**z_valence=10**，PBESOL，**无 NLCC**；真实 FR 集成 |
| 原 B0 Si scalar NC | `686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805` | Si，scalar，has_so=false，z=4，有 NLCC；两原子 8 价电子人工标量退化 |

路径分别取自原 source lock 与 B0 case，实际文件字节均保持不变。Mg 使用 `DFTK.PBEsol()` 对应的 `gga_x_pbe_sol + gga_c_pbe_sol`；Si 使用 `lda_x + lda_c_pw`。公共 Model 的 Xc 与实际实例化 TermXc 标识都核对。Mg 没有混用 Si 的 local/XC/NLCC 数据。

受控 loader 对原字节校验 hash，**解析一次**，从同一个解析对象建立 common 和通道，登记实际对象身份及完整快照。复制真实 hash/token 字符串仍不能发行新绑定；不同源、改变原数组或更换对象均被拒绝。raw PP_HEADER 保留；PPIO 对 functional 的空格进行规范化，按冻结源码区分 raw 文本和 parsed 表示。真实 has_so、元素和泛函没有改写，Mg 仍被原生 PspUpf SOC 保护拒绝。

两份输入的公共数组都保留 **1510 点，r=0…15.09 bohr**；Mg beta 的 **160 点 / 1.59 bohr** 支撑未用于截断公共量。接口语义为 PP_LOCAL/2（Ha）、PP_RHOATOM/(4π)=r²n_valence、PP_NLCC=n_core（Fourier 前乘 r²）。只提供安全的 valence Fourier 接口；local/core 实空间插值直接使用原始有限值，不在原点做 0/0。

局域 G=0 精确取零；有限修正 `alpha=4π∫r(r V_Ha+Z)dr` 使用完整物理网格和冻结低层 Simpson。Mg `alpha=9.187494522099392`，每胞 PspCorrection=`N_e alpha/Omega=0.09187494522099392 Ha`，单独进入能量一次，Hamiltonian 中为 Noop。没有增加 Phase 4C 常数 C、拟合平移或重复补偿。Mg 原子价密度 Fourier(0)=`9.999997867876154` 作为原始有限网格/求积诊断保留，没有归一化它来替代 header 的 N_e。

显式 Model 只含 **Kinetic、AtomicLocal、Ewald、PspCorrection、Hartree、Xc** 六项；实际 native AtomicNonlocal 数量为 **0**。common 类型没有可供原生 AtomicNonlocal 使用的 scalar projector API，误用明确拒绝。full-H 在各自物理 k 块中采用 `ComponentOperator(H_common,2)+V_NL_FR`；绑定实际 basis、k、G 顺序、FFT 映射、原子顺序、晶胞和 source。相同 NG 的 k± 交换也不能通过。

## 固定密度本征求解与完整 H

Mg 为 **10 bohr 立方胞、一个原子 R=(0.17,0.23,0.31)、15 Ha** 的周期集成 fixture，非平衡晶相。FFT 为 **40³**，三点空间权重各 1/3，无空间约化。n_ref 按预声明的分数坐标余弦构造，离散均值 `qbar=-4.56e-17`；密度范围 **0.0098–0.0102**，积分 **10.000000000000004**。

每点独立 ComplexF64 Gaussian 初始子空间，完整 spinor 列 QR；目标 **16** 态、辅助 **6** 态。真实迭代 LOBPCG tol=`1e-10 Ha`、maxiter=300；未使用重复标量谱或完整稠密对角化。

| k | NG / spinor 维度 | seed | 迭代 | 最大显式目标残差 Ha | norm(X'X-I) |
|---|---:|---:|---:|---:|---:|
| Γ | 2777 / 5554 | 62001 | 45 | 9.554642e-11 | 3.440893e-14 |
| (0.125,0.0625,-0.1875) | 2770 / 5540 | 62002 | 45 | 8.222591e-11 | 4.149493e-14 |
| (-0.125,-0.0625,0.1875) | 2770 / 5540 | 62003 | 45 | 8.796554e-11 | 3.546394e-14 |

三点求解各记录 **46 次 full-H / 46 次 FR 调用**，作用列数为 **920 / 926 / 925**；显式残差检查后各为 47 次。每次 common lift 实际调用两个标量分量。数值分解误差为零；故意遗漏/重复 FR 的作用变化范数为 **0.106–0.157**，与一份 FR 作用相符，因而并非只靠计数声明没有重复。

| 完整 H 检查 | 实测最大值 | 预声明门槛 |
|---|---:|---:|
| Hermiticity normalized | 1.602e-16 | 1e-10 |
| H_common + FR 作用分解 normalized | 0 | 1e-10 |
| 时间反演作用 normalized | 5.351e-17（绝对差最大 5.179e-16） | 1e-10 |
| Γ 相邻 Kramers 配对差 Ha | 6.661e-14 | 1e-8 |
| k± 排序目标谱差 Ha | 9.415e-14 | 1e-8 |

时间反演按实际 G+k 建立逐点双射，再应用 `i sigma_y K`；不按行号猜测，也没有跨 k 物理耦合。未要求一般非 TRIM 单点内部简并。Γ 的正负零键问题已在一次失败执行中暴露并被回归测试覆盖。

预声明 down-only 复数探针给出 up 信号范数 **1.42888e-4 / 1.44244e-4 / 1.98793e-4**；common up 输出均为 **0**，full-H 与 FR up-down 输出的绝对/信号相对误差均为 **0**。信号远高于 `1e-12`，没有以近零结果宣称覆盖。

## 当前轨道能量、自旋交叉项与双计数

N_e 来自实际原子 z_valence 之和。诊断占据为每点最低 10 个显式 spinor 态 f=1，其余为 0；每态容量 1，没有调用 Si 八电子占据 helper，也没有证明全局基态填充。

由当前 X,f 构造 R/n/m；六项公共能量使用 `[Xup Xdown]`、`[f;f]` 和显式 valence n。两个分量列未单独 QR/归一化。Hartree/计数仅使用 valence；core 只在原生 Xc 内部加入一次，完整 GGA 梯度/散度势由冻结实现提供。

下表为 **固定 n_ref 求得的轨道，按其自身 n_X 重新计算的泛函**（Ha/cell），不是 n_ref 下旧本征值之和：

| 项 | 能量 |
|---|---:|
| Kinetic | 41.96510079731074 |
| AtomicLocal | -94.89658195804809 |
| AtomicNonlocalFR | -17.561496063524675 |
| Hartree | 39.985367503773986 |
| Xc | -8.728240227193043 |
| Ewald | -14.186487397403095 |
| PspCorrection | 0.09187494522099392 |
| **合计** | **-53.33046239986318** |

n_X 积分为 **10.000000000000039**；`sqrt(dvol)*norm(n_X-n_ref)=4.069221362833036`。
固定势本征值诊断和为 **-73.05088415266476 Ha**，而当前 H[n_X] 实际占据期望 B 为 **-1.9337335790456904 Ha**。二者差 **71.11715057361907 Ha**，清楚表明不能用旧谱冒充当前泛函的 B。这一未自洽密度差没有被反馈到新的本征求解。

完整非局域能量使用全 spinor 的 x'V_FR x；另由 P_up/P_down 系数独立拆分：

| 轨道集合 | 完整 E_NL | 自旋对角贡献 | 交叉贡献 | 完整−对角−交叉 Ha |
|---|---:|---:|---:|---:|
| 固定势求解轨道 | -17.561496063524675 | -17.561489182828034 | -6.880696639e-6 | -2.419e-15 |
| 一般复数 energy fixture（seed 62041） | -0.0490599495327087 | -0.049064465003523114 | **4.515470814e-6** | -1.751e-17 |

矩阵无关与投影收缩两条 NL 能量路径 normalized error 最大 **1.388e-17**。fixture 的自旋交叉贡献可明确分辨，删除交叉项、遗漏/重复 NL 或沿用旧 scalar nonlocal 能量键均被测试拒绝。

用当前 H[n_X] 的实际 B 检查
`E=B-E_H-integral(n_valence*vxc)+E_XC+E_Ewald+E_PspCorrection`。
求解轨道的 `integral(n*vxc)=-11.411491362331589 Ha`，双计数绝对差 **5.684e-14 Ha**；一般复数 fixture 为 **1.421e-14 Ha**。能量分项求和差为零，直接动能/local/Hartree/常数检查最大绝对差 **9.948e-14 Ha**。

固定全局自旋旋转 axis=(1,2,3)/sqrt(14)、angle=0.47 rad：密度 normalized 差 **1.986e-16**，公共能量最大变化 **4.441e-16 Ha**；FR 能量变化 **-1.3809723815e-6 Ha**，总能量变化与其相差 **1.094e-14 Ha**。本 fixture 的仅自旋旋转非不变性可分辨，不要求 SOC 算符对此不变。

## 轨道有限差分

使用实际 Γ 求解轨道的占据态 1 与空态 11，固定旋转 **0.13 rad** 得到非驻点中心。中心导数分别为：
**总能量 0.3434014861292257、NL 0.06696690765431117 Ha/rad**，均高于预声明可辨识门槛。
每个 ±h 重新生成轨道密度、Hartree、完整 PBEsol 和 FR 能量；[逐步证据](phase6b/real-mg-si.json)保存各自能量、密度 hash 与相对中心变化。

| h rad | 总能量中心差分 Ha/rad | 总导数 normalized error | NL 中心差分 Ha/rad | NL 绝对误差 Ha/rad |
|---:|---:|---:|---:|---:|
| 1e-3 | 0.34340126988041675 | 2.162488e-7 | 0.06696686300955434 | 4.464476e-8 |
| 3e-4 | 0.3434014668239153 | 1.930531e-8 | 0.06696690363720374 | 4.017107e-9 |
| 1e-4 | 0.34340148371114765 | **2.418078e-9** | 0.0669669072017598 | **4.525514e-10** |

最终步长的门槛为总误差 `1e-6`，NL 误差 `1e-9+1e-6*abs(analytic)=6.796690765e-8`。三步全部保留，没有选择更有利方向/步长或改变容差；此处数值差分和解析 H 作用是不同计算路径。

## 原 Si 的完整人工标量退化

使用原 B0 几何、30 Ha、八个显式 k 点和 LDA/NLCC，**没有新的 Si SCF**。同一真实 scalar Si 径向/D 数据构造完整人工 j/mj 退化通道；没有把它称作 FR Si。

- 原生 PspUpf 与新 common 的 charge、local Fourier（含 G=0）、valence/core Fourier、修正能、local/r²数组均一致；最大 normalized error **2.999e-17**，仅来自非零径向点 core 实空间的舍入。
- 相同未自洽密度下，完整 H_new 与 native scalar lift 的八点作用最大 normalized error **3.997e-17**。
- 完整列正交的一般复数 fixture：新总能量 **132.65205035731836 Ha/cell**，与原生七项能量差 **0**；NL 分项差 **-2.082e-17 Ha**、XC **-4.441e-16 Ha**，其余五项差均 **0**。
- Si 的平滑 core 在当前 FFT 网格积分为 **1.4798832079273931**，仅是 NLCC 密度诊断，不计入 8 个可占据价电子。测试显式表明重复 core 会改变 XC，且 core+valence 不能通过 valence 计数。

## 测试、失败记录与命令

成功执行的入口（完整参数、时间和退出码见对应 command JSON）：

```sh
julia --startup-file=no --color=no --project=environment/workbench tests/fr_integration/runtests.jl .work/phase6b/20260906T004752Z-tests-7c813603
julia --startup-file=no --color=no --project=environment/workbench scripts/run_fr_integration.jl .work/phase6b/20260906T004533Z-real-2eb791c8
julia --startup-file=no --color=no --project=environment/workbench tests/relativistic/runtests.jl .work/phase6b/20260906T004621Z-regression-11fdf03d
```

运行均指定已有 `JULIA_DEPOT_PATH=<existing frozen cache>`、`JULIA_LOAD_PATH=@:@stdlib`、`JULIA_PKG_OFFLINE=true` 及 Julia/BLAS/OpenMP 单线程；私人缓存绝对路径仅保留在本地，不提交。

| 本轮实际检查 | 结果与证据 |
|---|---|
| common-only 检查 | 75/75，exit 0；[结果](phase6b/common-only-tests.json)、[日志](phase6b/common-only-tests.log) |
| 最终 Phase 6B 工作台测试 | **241/241**，0 failures/errors/broken，exit 0；[结果](phase6b/tests-final.json)、[日志](phase6b/tests-final.log)、[命令](phase6b/tests-final.command.json) |
| 本轮重跑 Phase 6A 工作台回归 | **1272/1272**，exit 0；[结果](phase6b/phase6a-regression.json)、[日志](phase6b/phase6a-regression.log)、[命令](phase6b/phase6a-regression.command.json) |
| 独立 CLI 新进程 | help=0，缺少参数=2，已有目录=2；原真实 PASS JSON hash 不变；[记录](phase6b/cli.json) |
| 最终源码/门槛/能量算术复核 | PASS；[检查](phase6b/delivery-checks.json)，正式运行与最终测试实际加载的每个源码 hash 均匹配交付文件 |
| 历史文件及上游边界 | PASS；[起始](phase6b/boundary-start.json)、[最终](phase6b/boundary-final.json) |
| git diff --check、相对链接、隐私/禁入文件检查 | PASS，提交前执行并记录于 [仓库检查](phase6b/repository-checks.json) |

负例覆盖：混用来源；元素/Z/XC 不一致；beta cutoff 误用；Ry/Ha 错误；rhoatom/NLCC 语义混淆；core 重复或进入价电子计数；native NL 混入 common；FR 遗漏/重复；同尺寸错误 G/k/原子顺序；交叉项丢失；旧 scalar NL 能量；旧 H[n_ref] 期望；拟合常数；G=0 与 PspCorrection 重复补偿；非有限/形状/占据错误；求解/显式残差失败；旧 PASS 掩盖失败。Generic 与优化 HamiltonianBlock 均有真实算符作用和别名回归。

错误对象只存在于明确标注的 synthetic 测试中，测试成功表示成功拒绝它们；其自身的运行记录仍为 FAIL。没有生成伪物理 UPF。没有修改旧 helper，故未重新执行 Phase 5B SCF；1272 是本轮实际新执行的 Phase 6A 测试数，历史 1387/1387 未作为本轮结果。

四个已解决的执行问题全部保留，未改写成 PASS：

| 原执行 | 旧行为 / 修复与复现证据 |
|---|---|
| common-only attempt 1，exit 1 | 错将 raw functional 的多空格与 PPIO 规范化字段直接比较；依据固定 `upf2.jl:149,167` 修正 expected parsed 表示，保留 raw header；[失败日志](phase6b/attempts/common-functional-rejection.log) |
| `20260906T003757Z-tests-83d553f8`，exit 1 | Julia 入口宏未加括号导致 parse error，未进入测试/模型；括号修复；[日志](phase6b/attempts/entry-parse-error.log)、[命令](phase6b/attempts/entry-parse-error.command.json) |
| `20260906T003922Z-tests-f9bdd416`，exit 1 | 测试的 LibxcDensities 调用缺少冻结版本必需的 τ 参数，227 passed、1 error；补显式 nothing，未改生产 XC；[失败记录](phase6b/attempts/gga-test-api-error.json)、[日志](phase6b/attempts/gga-test-api-error.log) |
| `20260906T004258Z-real-621db3c3`，exit 1 | Si 已通过；Γ 的 Dict 键把 +0/-0 分开，完整 H 检查停止，**本征求解 NOT_RUN**；零值统一键表示，仍逐点核实实际坐标和双射，新增 Γ/T² 回归；[失败记录](phase6b/attempts/gamma-key-error.json)、[日志](phase6b/attempts/gamma-key-error.log) |

中间 233/233 和 240/240 测试结果也保留在独立本地目录；最终交付使用 241/241。前两个启动期错误在完整运行记录器初始化前发生，保留原日志/命令；不伪称它们具备完整数值执行源码快照。成功真实运行、最终测试及回归有完整执行身份和源码 hash。没有因这些错误增加物理参数点，三个本征问题只在成功真实执行中各求解一次。

## 证据边界、状态与剩余工作

[证据清单](phase6b/evidence-manifest.json)分别记录原始文件与脱敏公开文件 SHA-256；公开日志仅作路径脱敏、尾空白清理及 LF 行尾规范化，原日志不变。首次 diff 检查发现生成日志尾空格和 CSV 的 CRLF，规范公开文件后重新检查通过；原始轨道/密度二进制保存在对应 ignored run 目录，公开文件仅含必要数值、逐态残差、分项及差分。没有提交 UPF、上游源码副本、依赖缓存或私人绝对路径。

独立检查确认 base 的 **307 个已跟踪文件字节全部未变**；两个上游 checkout commit 和状态未变；source lock、Project、Manifest、checksums、原 FR 验证器/SOC guard、原 B0、Phase 4/5/6A 历史配置/报告/日志及 Si/Mg 原始字节均保留。

| 状态字段 | 最终状态 |
|---|---|
| common_psp_data_status / same_source_consistency_status | PASS / PASS |
| full_hamiltonian_status / fixed_density_eigensolve_status | PASS / PASS |
| fr_total_energy_functional_status / variational_consistency_status | PASS / PASS |
| scalar_limit_integration_status | PASS |
| numerical_review_status | **REVIEW_REQUIRED** |
| soc_scf_status / noncollinear_xc_status | **NOT_IMPLEMENTED / NOT_IMPLEMENTED** |
| qe_soc_benchmark_status | **NOT_RUN** |
| upstream_native_support | **NOT_IMPLEMENTED_BY_THIS_PHASE** |

最终必需项目无未解决 FAIL、BLOCKED 或 INCONCLUSIVE；上述失败尝试继续保留。NOT RUN：SOC/其他新 SCF、Phase 5B A/B/C 重算、QE、上游完整套件、cutoff/k 扫描、力/应力/结构优化、MD、MLP。没有建立物理 cutoff/k 收敛、Mg 材料性质或 QE 一致性。

这里的泛函 PASS 只说明当前 X/f/n 上能量与完整算符一致。下一阶段仍需审查受限数据/算符接口，并另外设计和验收 SOC 自洽闭环、占据与密度混合、非共线 XC 范围、稳定性及独立 QE SOC 对拍。既有对象身份登记采用进程内能力，公开可变缓冲不支持外部并发修改；这是受限工作台原型，不是通用上游 API。本轮到此停止，未启动下一阶段。代码、测试和分析有实质 Codex AI 辅助。
