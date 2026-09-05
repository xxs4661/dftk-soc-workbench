# Phase 4C — Si 能量参考与有限数值敏感性

日期：2026-09-05。Base：`f05e6d70750f10d5ea87ebb9f7c6a5ec993c7063`。
分支：`codex/phase4c-reference-and-convergence`。开始时工作区干净、HEAD 等于指定 base；从该提交建立新分支，保留全部历史。没有重置、stash、amend 或合并 main。

**本轮仅新增 C1、C2、C3 三组配对计算，全部退出 0 并收敛，没有重试。B0 是 HISTORICAL_REUSED，不是本轮 SCF。未实现或验证 SOC/spinor，未建立完整 k 点收敛。**

## 状态与来源

| 检查层级 | 结果 |
| --- | --- |
| execution_status | PASS：三组 QE/DFTK SCF 及 DFTK 最终同一势对角化完成 |
| input_comparability_status | PASS：每组逐项验证；环境和 QE 身份与 B0 一致 |
| 能量参考证据层级 | 对应源码约定 + 原始 UPF 独立积分 + 实际 DFTK correction 输出；QE 内部数值未直接提取 |
| cutoff 检查 | 仅 8 点下 30→40→50 Ha 的两段敏感性，已测量；含默认 FFT 网格变化 |
| k 网格敏感性 | 50 Ha 下 8→64 点，已测量且显著 |
| 完整 k 点收敛 | NOT_ESTABLISHED；更密网格 NOT_RUN |
| 数值一致性 / 是否进入 spinor 开发 | REVIEW_REQUIRED；本轮不设事后通过阈值 |

| 设置 | DFTK Ha / QE wfc Ry / rho Ry | k 点数 | 来源 | run_id |
| --- | --- | --- | --- | --- |
| B0 | 30 / 60 / 240 | 8 | HISTORICAL_REUSED | `20260905T040945688395Z-1cc8a50c` |
| C1 | 40 / 80 / 320 | 8 | NEW_EXECUTION | `20260905T074125905466Z-f5d2bbc2` |
| C2 | 50 / 100 / 400 | 8 | NEW_EXECUTION | `20260905T074548814292Z-602630a9` |
| C3 | 50 / 100 / 400 | 64 | NEW_EXECUTION | `20260905T074856190211Z-bba6ecaf` |

B0 来源 commit 为本轮 base；[Phase 4B 报告](phase4b-review.md)与原始证据均未改写。[本轮历史核对](phase4c/preflight/historical-audit.json)验证其原始及公开文件 hash、原输入/配置、原 UPF 及 QE 保存的副本。用当前参数化代码重新生成的 case、DFTK 输入、QE 输入逐字节相同；旧 XML/stdout 重解析和原 DFTK 结果复算出的完整比较对象也完全相同。分析器另用已接受 evidence manifest 绑定 B0 原始字节，不能只靠 run_id 冒充历史结果。

## 环境与共同输入

[当前 workbench 身份](phase4c/preflight/identity.json)、[环境对照](phase4c/preflight/environment-audit.json)和[QE 启动链](phase4c/preflight/qe-identity.json)均为本轮新检查。Julia 1.12.7；DFTK 0.8.0，UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337`，实际加载 `.work/DFTK.jl/src/DFTK.jl`，commit `2f51b91213e26726fb9c6a17e5fae235a1412d01`；PPIO 0.3.3，UUID `cb339c56-07fa-4cb2-923a-142469552264`，实际加载 `.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl`，commit `fec942781560c391f20214ba4cd85fb2431deb84`。两个源码 checkout 都 clean。真实路径先比较、后脱敏。

active project 为 `<workbench>/environment/workbench/Project.toml`，实际采用同目录 Manifest，其 SHA-256 为 `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`。冻结 Project、Manifest、source lock、checksums 均未改变；每次配对再次使用新 Julia 进程核对身份。

QE 实际启动输出及 XML creator 均为 **7.5**；既有发行包为 QuantumEspresso_jll **7.5.1+0**，两者不混为同一个版本字段。启动链 `<home>/.local/bin/pw.x` → `qe-jll` → 既有 `qe-runner.jl` → JLL callback 的真实 pw.x，位于 artifact `273d3312b2a70e6223250dbf4a39ab3f28b04104`。二进制 SHA-256 `0500a3db2fc668d4e558d6e667522fbd62793bdf87631776e6b0c4bc3c4e50f0`，启动器、runner、JLL UUID/版本及二进制均与 B0 相同，运行后再次核对。QE 源码 commit **未确认**，以下源码约定来自 `qe-7.5` 标签，不能视为已证明 JLL 构建的精确源码 commit。无软件安装、升级或重编译。

Si UPF SHA-256：`686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805`，沿用 `dojo.nc.sr.lda.v0_4_1.standard.upf`。UPF 2.0.1、NC、scalar、has_so=false、Z=4、NLCC=true；两边读取同一副本，输入和 QE `.save/Si.upf` hash 均相同。本轮未重新下载赝势。

共同设置：a=10.26 bohr，两 Si 位于 (0,0,0)、(¼,¼,¼)，体积 270.011394 bohr³；该几何是固定测试输入。DFTK `lda_x+lda_c_pw` 对应 QE `SLA PW NOGX NOGC` 的原始 PW92，保留 NLCC；径向 `rcut=nothing`。非磁性、无 SOC、零温固定占据、8 电子、4 占据态、每点 8 目标标量带。SCF 目标仍为 DFTK 密度变化 L2 范数 1e−8、QE conv_thr=1e−10 Ry；上限 150，DFTK 对角化 1e−10 Ha、3 辅助带，QE diago_full_acc=true。CPU 顺序执行，MPI/Julia/OMP/BLAS/FFT 各 1 进程或线程。

新配置 [C1](../benchmarks/si-sr-lda/phase4c/C1.json)、[C2](../benchmarks/si-sr-lda/phase4c/C2.json)、[C3](../benchmarks/si-sr-lda/phase4c/C3.json)记录相对 B0 的全部变更。8 点为 {0,−½}³，64 点为 {0,¼,−½,−¼}³，各点空间权重分别为 1/8、1/64；显式确认包含关系，关闭对称性及约化。点数由请求配置给出，解析器不从输出自定期望值；数量、唯一性、模整数坐标匹配、权重与 8 电子/8 带检查均保留。

## 局域势参考：两个独立途径

在 Ha 原子单位下，`alpha = 4*pi*∫[r²*Vloc_Ha(r)+Z*r]dr`，`C = 2*alpha/Ω`。按 [UPF 格式](https://pseudopotentials.quantum-espresso.org/home/unified-pseudopotential-format)，PP_R 单位 bohr，PP_LOCAL 单位 Ry，因此先除以 2。先逐点抵消库仑尾部，再积分有限组合，没有对发散的库仑 G=0 变换直接积分。

A：[独立脚本](../scripts/inspect_si_reference.py)从实际原始数组积分 0–15.09 bohr（PP_R 全部 1510 点、间距约 0.01 bohr），采用实际坐标上的局部二次插值求积；最后单区间也按局部二次式处理，支持非均匀网格。没有导入 DFTK、调用 correction 或读取谱数据。独立 C 在新谱结果分析前已算定；其后录入 CLI 日志的复核输出逐字节相同。积分上限来自 PP_R，不来自历史元数据中命名不当的 `rho_cutoff_bohr`：标准 UPF `rho_cutoff` 是建议的密度能量截断。历史文件不改写。

B：[固定 DFTK](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L308)计算有限 correction；[PspCorrection 项](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/psp_correction.jl#L18)把 `N*C` 加入能量，其算符为 Noop（零算符）。DFTK 局域势 G=0 本身设为零，因此 correction 不给本征值加常数。

[QE 7.5 有限 G=0 系数](https://github.com/QEF/q-e/blob/qe-7.5/upflib/vloc_mod.f90#L151)和[局域势组装](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/setlocal.f90#L67)对应保留 `C` 的约定；两原子结构因子提供倍数 2。因此预期 `ε_DFTK−ε_QE≈−C`。完整公式、单位、算符及原生能量记账引用见[说明](../benchmarks/si-sr-lda/phase4c/README.md#independent-local-potential-reference)。这属于**基于对应源码约定与输入数据的预测**，没有直接提取实际 QE 二进制内部 G=0 值。未修改、复制或翻译 QE 算法实现。

| 量 | 实际数值 |
| --- | --- |
| 独立 alpha / Si | 6.669650355851782 Ha·bohr³ |
| 独立 C | +0.04940273265543588 Ha |
| 四组实际 E_PspCorrection | 0.3952218612434866 Ha/cell，逐组完全相同 |
| 四组实际 E_PspCorrection/8 | +0.04940273265543583 Ha |
| 独立 C − correction/8 | 4.85723e-17 Ha |
| 同网格梯形 C | 0.04939962996777792 Ha |
| 二次 − 梯形 C | 3.102687658e-06 Ha |
| 二次粗化 stride 2 / 3 / 4 的 ΔC | -6.250093e-11 / 7.107376e-10 / -1.003437e-09 Ha |

求积方法差异及粗化变化只是敏感性诊断，不是严格误差上界。末端被积函数约 −3.8023e−7 Ha·bohr²；最后 14.10–15.09 bohr 对 C 的贡献为 −4.3098e−8 Ha，尾部并不严格为零；R 以外没有积分或拟合。原始数组完整结果和诊断见[reference.json](phase4c/preflight/reference.json)。

符号、两原子倍数与 1/Ω 因子均有解析人工函数测试。固定 UPF、原子数和体积下，C 与 cutoff/k 网格无关；实际四组 correction 相同。这里 N=中性价电子数 8，不将此结论推广到任意带电模型。**没有向任何 SCF 总能量重复加减 N*C。**

| 设置 | 全局 HOMO DFTK / Ha | 全局 HOMO QE / Ha | 实际参考差 D−Q / Ha | 参考差 + 独立 C / Ha |
| --- | --- | --- | --- | --- |
| B0 | 0.183711229272175 | 0.233114502297711 | -0.049403273025536 | -5.40370100e-07 |
| C1 | 0.183709889164761 | 0.233113979564361 | -0.049404090399600 | -1.35774416e-06 |
| C2 | 0.183709465243402 | 0.233113157273971 | -0.049403692030569 | -9.59375133e-07 |
| C3 | 0.174293685022049 | 0.223696922874957 | -0.049403237852908 | -5.05197472e-07 |

HOMO 差只用于观测对照，从未用于确定 C。完整逐态原始差与 `Δε+C` 均保留；其带符号范围和占据/空态 RMS 在下述结构化分析中可查。

## A：同设置的跨程序差异

总能量差为 DFTK−QE；所有值保持原生 SCF 来源，没有拟合、平移或用本征值和替代。QE XML 为 Ha，stdout 为 Ry，转换依据延续固定版本格式说明；每次用 stdout 末次收敛总能量核对 XML。eV 使用 CODATA 2022 的 27.211386245981 eV/Ha。

| 设置 | DFTK Ha/cell | QE Ha/cell | ΔE Ha/cell | ΔE meV/atom |
| --- | --- | --- | --- | --- |
| B0 | -8.428884532744391 | -8.428880195604947 | -4.3371394440e-06 | -0.059009788 |
| C1 | -8.428892052776076 | -8.428887713769669 | -4.3390064075e-06 | -0.059035190 |
| C2 | -8.428896161666895 | -8.428891822661353 | -4.3390055424e-06 | -0.059035178 |
| C3 | -8.518042295147023 | -8.518037948043528 | -4.3471034950e-06 | -0.059145356 |

能谱逐 k 点按分数坐标模倒格矢匹配，再比较排序的最低 8 带；不匹配波函数。原始最大差/RMS 以 eV 给出，两个参考诊断以 μeV 给出（1 μeV=1e−6 eV）。HOMO 方案对每个程序的全采样点集只用一个全局参考；C 方案只移除独立预测的共同项，不作拟合。

| 设置/集合 | 原始 max/RMS eV | 单全局 HOMO 后 max/RMS μeV | 独立 C 后 max/RMS μeV |
| --- | --- | --- | --- |
| B0 全部 | 1.344336993 / 1.344329258 | 8.473540 / 3.893732 | 20.153324 / 12.811932 |
| B0 占据 | 1.344334534 / 1.344327737 | 8.473540 / 4.565576 | 17.694396 / 11.184449 |
| B0 空态 | 1.344336993 / 1.344330779 | 5.449105 / 3.078606 | 20.153324 / 14.254799 |
| C1 全部 | 1.344353786 / 1.344347152 | 13.922659 / 7.298481 | 36.946101 / 30.464556 |
| C1 占据 | 1.344353786 / 1.344348049 | 10.089797 / 6.118615 | 36.946101 / 31.282010 |
| C1 空态 | 1.344353063 / 1.344346255 | 13.922659 / 8.312532 | 36.222729 / 29.624554 |
| C2 全部 | 1.344353528 / 1.344341369 | 10.582355 / 3.952581 | 36.688282 / 24.795800 |
| C2 占据 | 1.344344996 / 1.344340263 | 6.629647 / 3.380335 | 28.156484 / 23.513157 |
| C2 空态 | 1.344353528 / 1.344342476 | 10.582355 / 4.451867 | 36.688282 / 26.015281 |
| C3 全部 | 1.344331637 / 1.344330938 | 1.050104 / 0.455549 | 14.797228 / 14.100840 |
| C3 占据 | 1.344331190 / 1.344330735 | 0.619897 / 0.243407 | 14.350599 / 13.895976 |
| C3 空态 | 1.344331637 / 1.344331141 | 1.050104 / 0.596492 | 14.797228 / 14.302770 |

主要约 1.3443 eV 的共同项与独立预测的符号和量级吻合，但并非精确解释全部差异。C 诊断的最大残差约 15–37 μeV。HOMO 后差在 8 点 cutoff 序列中不单调：8.47→13.92→10.58 μeV，C3 为 1.05 μeV；原生总能量跨程序差保持约 −4.34e−6 Ha/cell。这里没有挑选“通过”阈值，也不把 C3 更小的差追认为已有物理精度标准。未解释的漂移和非单调变化保留供审查，本轮不进一步扫描或调参。

完整数据：[结构化统计与证据索引](phase4c/20260905T075146761615Z-19093b4b/sensitivity.json)，每组逐态 CSV：[B0](phase4c/20260905T075146761615Z-19093b4b/B0.csv)、[C1](phase4c/20260905T075146761615Z-19093b4b/C1.csv)、[C2](phase4c/20260905T075146761615Z-19093b4b/C2.csv)、[C3](phase4c/20260905T075146761615Z-19093b4b/C3.csv)。B0/C1/C2 各 64 条，C3 为 512 条，包含原始本征值、未平移差、HOMO 参考后差和独立 C 诊断残差。

## B/C：各程序自身的敏感性

下表变化均为“后设置−前设置”。各解统一选 Γ 的最高占据能级为一个全局参考，供该解所有被比较的共同八点使用；cutoff 段也采用相同定义。原始参考值、原始谱、占据/空态分别统计均保留在对应 CSV/JSON，没有逐 k 点归零。跨网格只比较共同原八点，而不是 64 点按行截取前八点。

| 变化 | 程序 | ΔE Ha/cell | ΔE meV/atom | 原谱 max/RMS eV | Γ 参考后 max/RMS eV |
| --- | --- | --- | --- | --- | --- |
| B0→C1 | DFTK | -7.5200316854e-06 | -0.102315243 | 1.149989323e-04 / 4.922512834e-05 | 7.853275181e-05 / 2.891243727e-05 |
| B0→C1 | QE | -7.5181647219e-06 | -0.102289842 | 9.474907270e-05 / 3.462773527e-05 | 8.052477363e-05 / 2.779668023e-05 |
| C1→C2 | DFTK | -4.1088908187e-06 | -0.055904308 | 3.788452760e-05 / 1.525665792e-05 | 2.634903976e-05 / 7.334181424e-06 |
| C1→C2 | QE | -4.1088916838e-06 | -0.055904319 | 4.621031544e-05 / 2.126883842e-05 | 2.383465402e-05 / 9.432434125e-06 |
| C2→C3 | DFTK | -8.9146133480e-02 | -1212.894935232 | 2.562164324e-01 / 1.792832665e-01 | 2.285873182e-01 / 1.069919701e-01 |
| C2→C3 | QE | -8.9146125382e-02 | -1212.894825054 | 2.562287912e-01 / 1.792925613e-01 | 2.285795046e-01 / 1.069927926e-01 |

| 变化 | 程序 | Γ 参考前值 Ha | Γ 参考后值 Ha | 参考变化 Ha | 数据 |
| --- | --- | --- | --- | --- | --- |
| B0→C1 | DFTK | 0.183711229272175 | 0.183709889164761 | -1.3401074141e-06 | [逐态 CSV](phase4c/20260905T075146761615Z-19093b4b/B0_to_C1_DFTK.csv) |
| B0→C1 | QE | 0.233114502297711 | 0.233113979564361 | -5.2273334930e-07 | [逐态 CSV](phase4c/20260905T075146761615Z-19093b4b/B0_to_C1_QE.csv) |
| C1→C2 | DFTK | 0.183709889164761 | 0.183709465243402 | -4.2392135927e-07 | [逐态 CSV](phase4c/20260905T075146761615Z-19093b4b/C1_to_C2_DFTK.csv) |
| C1→C2 | QE | 0.233113979564361 | 0.233113157273971 | -8.2229039061e-07 | [逐态 CSV](phase4c/20260905T075146761615Z-19093b4b/C1_to_C2_QE.csv) |
| C2→C3 | DFTK | 0.183709465243402 | 0.174293685022049 | -9.4157802214e-03 | [逐态 CSV](phase4c/20260905T075146761615Z-19093b4b/C2_to_C3_DFTK.csv) |
| C2→C3 | QE | 0.233113157273971 | 0.223696922874957 | -9.4162343990e-03 | [逐态 CSV](phase4c/20260905T075146761615Z-19093b4b/C2_to_C3_QE.csv) |

固定 8 点下，40→50 Ha 的原生能量变化约 −0.0559043 meV/atom，相对谱最大变化约 2.4–2.6e−5 eV；这只是有限区间的观测，不能仅因 QE/DFTK 接近就称 cutoff 已收敛。默认 FFT 与 cutoff 同时变化，未分离波函数截断和 FFT/NLCC/径向积分误差。

50 Ha 的 8→64 点变化显著：两程序均约 −1212.895 meV/atom，Γ 参考后的共同点谱最大变化约 0.2286 eV、RMS 约 0.1070 eV。程序间相近与各程序 k 积分稳定是不同问题；当前证据不支持 8 点已收敛，更不能仅凭两种网格宣布 64 点充分收敛。

| 设置 | DFTK 本采样网格 gap / eV | QE 本采样网格 gap / eV |
| --- | --- | --- |
| B0 | 0.415357521352 | 0.415356679578 |
| C1 | 0.415379619949 | 0.415369223252 |
| C2 | 0.415384261527 | 0.415382983758 |
| C3 | 0.587043194979 | 0.587043808090 |

另检查 C3 的极值位置：HOMO 位于 Γ；最低空态位于与 (0,−½,−½) 等价/对称的原八点中，C3 共同八点与全 64 点给出相同采样 gap。本例 gap 变化并非因为新增点出现更低空态；这是对实际极值的检查，不推广成一般结论。它仍是有限自洽 k 网格上的 gap，不是已收敛基本带隙。

## 求解与尚未分离的误差

| 设置 | DFTK/QE FFT | NPW 范围 | SCF 轮数 D/Q | DFTK Δρ | QE SCF error Ha | DFTK 显式残差 max Ha | QE 最后 ethr Ry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 40³ / 36³ | 2085–2120 | 7 / 8 | 2.28981e-09 | 5.14190e-12 | NOT_RUN（历史未保存 ψ） | 1.770e-12 |
| C1 | 45³ / 45³ | 3274–3287 | 7 / 7 | 2.29690e-09 | 3.24353e-11 | 9.945295e-11 | 2.980e-11 |
| C2 | 50³ / 48³ | 4512–4573 | 7 / 7 | 2.29624e-09 | 2.26789e-11 | 9.977710e-11 | 3.510e-11 |
| C3 | 50³ / 48³ | 4512–4584 | 7 / 7 | 1.94257e-09 | 6.51285e-13 | 9.625244e-11 | 2.460e-12 |

各设置的全部逐点 NPW 与坐标匹配后两程序完全相同，完整列表在分析 JSON。B0 的求解器历史最大残差为 6.90553e−11 Ha；它没有本轮新增的显式残差，不能拿新值填补历史。C1/C2/C3 在原有最终自洽势上额外计算每个目标态 `norm(Hψ−εψ)`，不改变势、密度、能量或本征值；分别 64/64/512 个值均有限且最大值小于原 1e−10 Ha 容差。这些最大值接近原容差，不支持更强的残差精度宣称。原始 LOBPCG 历史值仍保留，零槽可能来自已锁定态。

QE 没有输出逐态残差；其 diago_full_acc、最后 ethr、SCF 误差与 XML/text 收敛证据均保留。[QE 独立读取审计](phase4c/preflight/qe-audit.json)还将全部 XML 本征值与文本四位小数 eV 按坐标核对，符合舍入精度；微 eV 比较依赖完整精度 XML，不能用粗文本证明。[DFTK 审计](phase4c/preflight/dftk-audit.json)核对原生能量与最终 SCF 历史值一致，能量分项和仅有浮点求和舍入差。

未分离因素包括默认 FFT 网格、径向积分/插值、NLCC 离散化、各程序 SCF 标准及求解误差；同 FFT 尺寸也不证明实现完全相同。独立积分尾部不严格为零，QE 内部有限项数值不可直接取出。未将这些因素中的任何一个无证据地指定为全部残差来源。

## 命令、测试与交付证据

精确入口命令、退出码及各引擎完整命令在[执行 ledger](phase4c/preflight/execution-ledger.json)和各次 result.json。新增配对命令均为 `python3 scripts/run_scalar_baseline.py --case benchmarks/si-sr-lda/phase4c/Cn.json --julia-depot <existing-workbench-cache>`（n=1,2,3），每组入口、身份检查、QE、DFTK 均退出 0。独立积分 CLI 和全部分析命令也退出 0；[可复现说明](../benchmarks/si-sr-lda/phase4c/README.md#running-and-analyzing)列出命令。

| 设置 | 配置 SHA-256 | DFTK 输入 SHA-256 | QE 输入 SHA-256 |
| --- | --- | --- | --- |
| B0 | `2f7aaf914ef6db5ccfa4c81a124b24c5bd32b27383d95c756c97266a22b63f65` | `618f46548779453dae52ed3a01a3a87d066ddf8583e5ea1b83f220670a07c87e` | `f634604331eab32dfc03daab4fb6c7abb704cbe75dd6c6f1b7c03feb47675fe2` |
| C1 | `fda4c5c4d13985e92c5d552827ec226eda311e4a403b110fd8f2abdd81428237` | `088c33df1f62ed8698eb356418939e4be5f71c529d44642b96eb7851951c836f` | `729f6a71d0647a6db72a4b639c0a04e1dcda4c9900330846e207ccd341eb0cb9` |
| C2 | `b431f464b5787dd191da9b2cb0281725ccbe030082e374ed246cd490a8f16e3e` | `e41cdbc40aa8d223b791686ecf100cf544e5bfb9dee98b1625e931aa591c957d` | `043335277da1a05d482e07505f49d79f6dd283e5a7182f5836fd9bc14e92e3ef` |
| C3 | `fbaecf97ca828ba324f6b983cbee236b1c5bdceb10ce881426774b2fa44eccb8` | `941fcc81ee0b054b585df67b78059906aee49da1f2ca51cf47215dc04d11ce1b` | `4ae4b6833eeaf1b09f8644ca0bfa0c236fc840e33d021b51b8b162bad8fa6df9` |

| 设置 | 本次结果 | 完整脱敏日志 | 结构化原始结果 | 文件身份 |
| --- | --- | --- | --- | --- |
| C1 | [20260905T074125905466Z-f5d2bbc2](phase4c/20260905T074125905466Z-f5d2bbc2/result.json) | [QE](phase4c/20260905T074125905466Z-f5d2bbc2/qe.stdout) / [DFTK](phase4c/20260905T074125905466Z-f5d2bbc2/dftk.stdout) | [QE XML](phase4c/20260905T074125905466Z-f5d2bbc2/qe-data-file-schema.xml) / [DFTK JSON](phase4c/20260905T074125905466Z-f5d2bbc2/dftk-result.json) | [hash manifest](phase4c/20260905T074125905466Z-f5d2bbc2/evidence-manifest.json) |
| C2 | [20260905T074548814292Z-602630a9](phase4c/20260905T074548814292Z-602630a9/result.json) | [QE](phase4c/20260905T074548814292Z-602630a9/qe.stdout) / [DFTK](phase4c/20260905T074548814292Z-602630a9/dftk.stdout) | [QE XML](phase4c/20260905T074548814292Z-602630a9/qe-data-file-schema.xml) / [DFTK JSON](phase4c/20260905T074548814292Z-602630a9/dftk-result.json) | [hash manifest](phase4c/20260905T074548814292Z-602630a9/evidence-manifest.json) |
| C3 | [20260905T074856190211Z-bba6ecaf](phase4c/20260905T074856190211Z-bba6ecaf/result.json) | [QE](phase4c/20260905T074856190211Z-bba6ecaf/qe.stdout) / [DFTK](phase4c/20260905T074856190211Z-bba6ecaf/dftk.stdout) | [QE XML](phase4c/20260905T074856190211Z-bba6ecaf/qe-data-file-schema.xml) / [DFTK JSON](phase4c/20260905T074856190211Z-bba6ecaf/dftk-result.json) | [hash manifest](phase4c/20260905T074856190211Z-bba6ecaf/evidence-manifest.json) |

测试命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts:tests python3 -m unittest -v test_scalar_baseline test_qe_baseline_parser test_phase4c_baseline test_si_reference test_si_sensitivity`，退出 **0，91/91 通过**，见[日志](phase4c/preflight/delivery-tests.log)。包括受影响 Phase 4B 测试及新增的 64 点正负例、固定电子/带数、共同点与 Γ 全局参考、独立积分解析函数/单位/符号/倍数/体积、能量不被 C 修改、历史 hash 绑定、独立性协议、失败不复用旧结果。人工函数和人工谱仅为 synthetic tests；其中四项 B0 replay 明确标为 HISTORICAL_REUSED，均不是本轮 SCF 或上游测试。

分析器对 B0/C1/C2/C3 重新解析和复算均与原始配对结果一致，随后输出独立 C 诊断与有限变化；[分析命令及退出码](phase4c/preflight/analysis-command.json)。原始数据在忽略目录 `.work/scalar-baseline/<run_id>/`，分析原始输出在 `.work/phase4c-analysis/20260905T075146761615Z-19093b4b/`。公开文本仅脱敏私人路径并规范行末空白/换行；每目录 manifest 分别列 raw/published SHA-256，原始字节不改。没有提交 UPF、波函数、完整 .save、二进制、源码副本或缓存。

`git diff --check` 退出 0；[范围检查](phase4c/preflight/scope-check.json)确认 base 的 119 个文件中，114 个保护文件逐字节不变，只对四个允许的小型配对脚本和一份相关旧测试作必要修改。两个上游 checkout 仍 clean。

FAIL / BLOCKED：无未解决的运行、环境或输入阻塞，三组均一次完成。只读 QE 审计最初草稿曾把浮点 −0.5000000000000001 的等价点及 JOB DONE 后分隔行处理错，[草稿](phase4c/preflight/qe-audit-initial-checker-errors.json)保留；修正审计检查后全部通过，未改运行数据或生产解析器。这不是 SCF 重试。独立审计计数不合并到 91 项单元/回归测试中。

NOT_RUN：B0 重新 SCF、B0 显式残差重算、完整 DFTK 上游/minimal、未受影响的旧 recorder 套件、独立环境重建、QE 单独 bands/NSCF、额外 cutoff、6³/8³ 等更密网格、第二材料、SOC/spinor/MLP、力/应力/优化。历史 1387/1387 不计入本轮。QE 内部 G=0 直接提取为 NOT_AVAILABLE；完整 k 点收敛为 NOT_ESTABLISHED。

## 给下一阶段的建议与停止点

快速开发回归可继续使用 **B0：30 Ha / 8 点**，保持已接受输入和历史锚点；适合检查以后新增代码是否退化回当前标量行为，不能用来宣称物理 k 点精度。相对本轮矩阵较严格的配对候选为 **C3：50 Ha / 64 点**，保留相同 UPF/XC/NLCC、精度设置和原生能量记账；这只是已测矩阵中更密的选择，绝非已收敛基准或新验收阈值。

是否进入 spinor 开发留待人工审查，状态 REVIEW_REQUIRED。本轮支持把标量结果作为未来开发回归锚点，尚不构成 SOC 数值验收、完整 k 点收敛或所有跨程序残差均已解释的证据。审查应明确接受哪些有限范围与未解释残差；若后续需要量化物理精度或解释非单调漂移，应另行授权收敛/底层数值检查，不在本轮扩大扫描。

本轮到此停止，等待审查；只形成普通提交并推送指定新分支，不创建 PR、不推 main、不合并、不改写历史、不发布上游留言。AI 协助按实际分工记录：主任务负责运行/分析/交付；三个子代理分别协助固定 DFTK 与测试、QE 解析与约定审计、独立 UPF 积分。人工维护者作最终数值与开发决策；不猜测模型名称。
