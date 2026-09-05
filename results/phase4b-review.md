# Phase 4B — Si 标量相对论 QE–DFTK 基础对拍

日期：2026-09-05。Base：`45e3761242dd8c083cca586dc0efc82f93929bd5`。
分支：`codex/phase4b-scalar-si-baseline`。开始时工作区干净，HEAD 等于指定 base；从该提交新建分支，未合并 main、覆盖修改或改写历史。

**execution_status = PASS；input_comparability_status = PASS；numerical_agreement_status = REVIEW_REQUIRED；convergence_study_status = NOT_RUN。**

**本轮为 Si 标量相对论基础对拍，尚未完成 cutoff/k 点收敛研究，未实现或验证 SOC。**
有效配对 run_id：`20260905T040945688395Z-1cc8a50c`。两个程序实际 SCF 收敛，DFTK 的最终自洽势对角化也完成。没有设置或事后挑选“数值一致”的通过阈值。

## 环境与输入身份

先运行了既有 `python3 scripts/run_recorded.py identity`，退出 0；本轮结果见 [首次身份检查](phase4b/preflight/identity.json)。配对运行再次以新 Julia 进程检查实际加载路径、UUID、版本、commit、清洁状态及环境 hash，见 [本次身份](phase4b/20260905T040945688395Z-1cc8a50c/workbench-identity.stdout)。

| 项目 | 实际记录 |
| --- | --- |
| Julia / active project | 1.12.7；`<workbench>/environment/workbench/Project.toml` |
| Manifest | 同目录 `Manifest.toml`；SHA-256 `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37` |
| DFTK | 0.8.0；UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337`；commit `2f51b91213e26726fb9c6a17e5fae235a1412d01`；`.work/DFTK.jl/src/DFTK.jl`；clean |
| PseudoPotentialIO | 0.3.3；UUID `cb339c56-07fa-4cb2-923a-142469552264`；commit `fec942781560c391f20214ba4cd85fb2431deb84`；`.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl`；clean |
| QE 实际启动版本 | **PWSCF 7.5**，由启动输出及 QEXSD creator 确认；不是从安装包名称推断 |
| QE 安装来源 | 既有 QuantumEspresso_jll **7.5.1+0**；aarch64/macOS、libgfortran 5、MPICH artifact。未安装或升级软件；QE 源码 commit **未确认** |
| QE 启动器 | `<home>/.local/bin/pw.x` → `<home>/.local/bin/qe-jll`；启动器 SHA-256 `2693ceb566549491fb051ab3047bbf7033d51409f75a9a26a6f2a2f10db30c2c` |
| QE 实际二进制 | JLL callback 解析到 `<home>/.julia/artifacts/273d3312b2a70e6223250dbf4a39ab3f28b04104/bin/pw.x`；SHA-256 `0500a3db2fc668d4e558d6e667522fbd62793bdf87631776e6b0c4bc3c4e50f0`，运行后再次核对 |
| MPI / 线程 | 两边均 CPU、MPI 1 进程；OMP/Julia/BLAS/FFT 采用 1 线程。QE XML 的各并行字段均为 1；顺序执行，未作性能比较 |

[QE 启动链与精确命令](phase4b/20260905T040945688395Z-1cc8a50c/result.json)、[JLL 探测输出](phase4b/20260905T040945688395Z-1cc8a50c/qe-jll-probe.stdout)及[可获得的构建/安装信息](phase4b/preflight/qe-build-identity.json)区分了启动器、实际二进制和发行包标签。公开路径在真实身份比较之后脱敏；没有将另一个目录的 HEAD 作为加载身份。

Si 文件为 PseudoLibrary v0.2.1 / PseudoPotentialData v0.3.2 的 `dojo.nc.sr.lda.v0_4_1.standard.upf/Si.upf`。本轮复用已有 artifact，并独立核对完整 artifact Git-tree `11b56401937bd46168a84a333c623c0de8ae69e9` 和文件字节；未重新下载 archive。[配置与来源/hash](../benchmarks/si-sr-lda/case.json)及[可复现获取方法](../benchmarks/si-sr-lda/README.md)另行记录，不改旧 source lock。

UPF SHA-256：`686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805`。实际 header：UPF 2.0.1、Si、NC、`relativistic=scalar`、`has_so=false`、`z_valence=4`、`core_correction=true`，含 PP_NLCC。原始 functional 声明为 `SLA  PW   NOGX NOGC`。DFTK 使用 `PspUpf(...; rcut=nothing)`，实际保留 1510 点、末端 15.09 bohr 的径向网格；其 XC 项实际加载 core density。QE 输出明确报告 NC + core correction，保存目录内 Si 文件也与输入 hash 一致。UPF 本体未提交。

具体 XC 为 Slater 交换 + 原始 Perdew–Wang 1992 关联。QE 实际打印索引 `(1,4,0,0,0,0,0)`；DFTK 显式使用 `lda_x`、`lda_c_pw`，Libxc 7.0.0 的 IDs 1、12。已核对 QE 非磁性 PW 参数与 Libxc PW 一致，未混用 PZ/VWN 或 `lda_c_pw_mod`；没有强制 `input_dft`。[版本源码与参数依据](../benchmarks/si-sr-lda/README.md#exact-xc-and-nlcc)包含 QE 7.5、固定 PPIO/DFTK 和 Libxc 7.0.0 引用。

## 输入对照与收敛证据

[case.json](../benchmarks/si-sr-lda/case.json)是配对几何、k 点、截断能和 XC 的唯一配置；生成的 [QE 输入](phase4b/20260905T040945688395Z-1cc8a50c/qe.in)与 [DFTK 输入](phase4b/20260905T040945688395Z-1cc8a50c/dftk-input.json)随本次运行保存。

| 设置 | DFTK | QE |
| --- | --- | --- |
| 晶胞 | 按列存储三个矢量 | `ibrav=0`；`CELL_PARAMETERS bohr` 按行 |
| 固定几何 | 两边均 a=10.26 bohr，a/2×(0,1,1)、(1,0,1)、(1,1,0)；体积 270.011394 bohr³ | 实际输出逐分量核对相同 |
| 原子 | 两个 Si；分数坐标 (0,0,0)、(¼,¼,¼) | `ATOMIC_POSITIONS crystal`，输出坐标转回分数坐标核对 |
| k 点 | `ExplicitKpoints`，{0,−½}³ 全部 8 点 | `K_POINTS crystal` 显式同一 8 点 |
| 对称性 | `symmetries=false`，实际仅 identity | `nosym=true`、`noinv=true`；实际 8 点未约化 |
| 波函数截断 | 30 Ha | 60 Ry |
| 电荷/FFT | 实际 FFT 40×40×40 | `ecutrho=240 Ry`；实际 dense/smooth FFT 36×36×36 |
| 自旋/温度 | `spin_polarization=:none`；零温 | `nspin=1`，noncolin/lspinorb=false；fixed occupations |
| 电子/占据 | 8 电子；每点 4 态占据 2、其余空 | 相同物理计数；原始 XML 权重/占据约定见下文 |
| 目标带数 | 最低 8 带；另计算 3 个辅助带，保留其原始数据 | 实际输出 8 带，包括空态 |
| SCF 目标/上限 | tol=1e−8，maxiter=150 | conv_thr=1e−10 Ry，electron_maxstep=150 |
| SCF 实际 | converged=true；7 轮；最终密度差范数 2.2898086225e−9 | 8 轮；XML convergence_achieved=true + 最后文本收敛消息；error=5.1419011611e−12 Ha |
| 对角化 | SCF 中明确收敛前 8 带；最终同一势再对角化，阈值 1e−10 Ha | `diago_full_acc=true`；最后 ethr=1.77e−12 Ry；未另做 NSCF |

a 是人为固定测试输入，不是计算出的平衡值或新实验测量值。非对称矩阵测试验证了生成器的行/列转换，避免 Si 矩阵对称性掩盖错误。两边逐点平面波数完全相同（按配置点序）：`[2085,2120,2120,2100,2120,2100,2100,2120]`。k 点按分数坐标模整数倒格矢匹配，未按行号或能量接近程度配对。

DFTK 的 tol 是 `norm(ρout−ρin)*sqrt(dvol)` 的 L2 密度变化准则，[固定 SCF 源码](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/scf/self_consistent_field.jl#L239)与[回调准则](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/scf/scf_callbacks.jl#L153)可核查；它不等同于 QE 的 SCF 误差估计。DFTK 在 SCF 末尾[重建最终 Hamiltonian](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/scf/self_consistent_field.jl#L270)，因此在该同一势上再求最低 8 带，未更新密度或总能量。最终每点 2–5 次对角化迭代，求解器报告的目标带最大残差 `6.9055289512e−11 Ha`。零残差槽可能来自此前已锁定态，不代表独立重算的严格零残差；QE 没有输出逐带残差。

原始 QE XML 权重为 0.25（总和 2），占据为 1/0；DFTK 原始空间权重为 0.125（总和 1），占据为 2/0。按 QE [写入器 wg/wk](https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd_init.f90#L1159)和[非磁性简并约定](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/setup.f90#L647)，显式转换为 `空间权重=QE原权重/2`、`占据=2×QE原占据`。两种原始计数及统一后的加权电子数都为 8，未用隐含乘除因子凑数。

完整证据：[QE stdout](phase4b/20260905T040945688395Z-1cc8a50c/qe.stdout)、[QE XML](phase4b/20260905T040945688395Z-1cc8a50c/qe-data-file-schema.xml)、[QE 结构化结果](phase4b/20260905T040945688395Z-1cc8a50c/qe-result.json)、[DFTK 日志](phase4b/20260905T040945688395Z-1cc8a50c/dftk.stdout)、[DFTK 结构化结果及残差](phase4b/20260905T040945688395Z-1cc8a50c/dftk-result.json)。

## 总能量与本征值

差值统一为 **DFTK−QE**。总能量不拟合常数、不归零、不平移，也不以本征值和代替。QE XML 在 [QEXSD 单位声明](https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd.f90#L128)下使用 Ha；stdout 的最终值为 `−16.85776039 Ry`（8 位小数），结构化 Ha 保留更多位数。下表 eV 展示使用 [CODATA 2022](https://physics.nist.gov/cuu/pdf/factors_2022.pdf) 的 1 Ha=27.211386245981 eV。

| 总能量 | Ha/cell | Ha/atom | eV/atom |
| --- | ---: | ---: | ---: |
| DFTK SCF | −8.428884532744390 | −4.214442266372195 | −114.680816321641 |
| QE SCF（XML） | −8.428880195604947 | −4.214440097802473 | −114.680757311853 |
| 带符号差 | −4.3371394440e−6 | −2.1685697220e−6 | −5.9009788307e−5 |
| 绝对差 | 4.3371394440e−6 | 2.1685697220e−6 | 5.9009788307e−5 |

全局参考分别为整个 8 点集上的最高占据能级：DFTK `0.1837112292721751 Ha`，QE `0.2331145022977106 Ha`；参考差 `−0.049403273025535516 Ha`。各程序所有点、所有带统一减去自己的这一个参考。简并态只比较排序后的能量，不主张波函数逐个相同。

| 本征值集合 | 原始最大绝对差 / RMS（Ha） | 全局参考后最大绝对差 / RMS（Ha） | 全局参考后最大绝对差 / RMS（eV） |
| --- | ---: | ---: | ---: |
| 全部 64 值 | 4.9403473276e−2 / 4.9403189014e−2 | 3.1139686851e−7 / 1.4309201809e−7 | 8.4735404649e−6 / 3.8937321730e−6 |
| 占据态 32 值 | 4.9403382912e−2 / 4.9403133110e−2 | 3.1139686851e−7 / 1.6778182114e−7 | 8.4735404649e−6 / 4.5655759401e−6 |
| 空态 32 值 | 4.9403473276e−2 / 4.9403244919e−2 | 2.0025091468e−7 / 1.1313669509e−7 | 5.4491049856e−6 / 3.0786063087e−6 |

全部原始与全局参考后的逐点逐带数据：[eigenvalues.csv](phase4b/20260905T040945688395Z-1cc8a50c/eigenvalues.csv)；包含原始 eV 汇总和完整数值的 [comparison.json](phase4b/20260905T040945688395Z-1cc8a50c/comparison.json)。原始最大绝对差为 `1.3443369932 eV`，没有从交付中删去。

| 当前采样网格 | 最高占据态（Ha） | 最低空态（Ha） | 当前采样网格上的 gap（eV） |
| --- | ---: | ---: | ---: |
| DFTK | 0.1837112292721751 | 0.1989753366424141 | 0.415357521352 |
| QE | 0.2331145022977106 | 0.2483785787333276 | 0.415356679578 |

这不是已收敛的基本带隙。DFTK 零温费米能为 HOMO/LUMO 中点 `0.19134328295729458 Ha`，依据[固定占据源码](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/occupation.jl#L190)；QE XML 的费米能实际等于其最高占据能级 `0.2331145022977106 Ha`。定义不同，未用两者差单独判断错误。

单位、几何、赝势字节、具体 XC、NLCC、电子/占据及解析均已逐项核对。另将 64 个 XML 本征值按 k 坐标与 QE 文本 eV 值回核：最大舍入差 4.9823e−5 eV，符合文本 4 位小数精度；最终总能量 XML×2 与文本 Ry 差 1.2099e−9 Ry，符合 8 位小数精度。详见[独立读取审计](phase4b/preflight/final-qe-audit.json)。参考后 8.47e−6 eV 的差来自完整精度 XML，不能仅凭较粗的 stdout 数字证明，也没有根据两程序“比较接近”来反推单位。

原始本征值差在 `−0.0494034733` 至 `−0.0494029616 Ha` 之间，显示近似共同偏移，但并非严格常数。单个全局参考消去共同部分后仍有残差；本轮未完整核对两边势能 G=0 参考约定，不能断言全部差异都由能量零点造成。DFTK 的[局域势 G=0 处理](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L236)只是后续排查线索。FFT 网格、径向积分/插值及有限 SCF/对角化误差也应纳入后续研究，当前证据不足以分配各自贡献。所有能量均保留程序原生能量项，没有 workbench 外加的经验校正。

## 命令、hash、失败记录与停止点

完整可复现入口为 [运行说明](../benchmarks/si-sr-lda/README.md#run-and-inspect)。实际入口命令：`python3 scripts/run_scalar_baseline.py --julia-depot <existing-workbench-cache>`。缓存路径仅为运行参数；冻结 Project/Manifest 不变。实际 QE 命令为 `<selected-pw.x> -in qe.in`，在本次新建的 `qe/` 目录执行；DFTK 命令为 `julia --startup-file=no --color=no --project=<workbench>/environment/workbench <workbench>/scripts/run_dftk_baseline.jl <run>/dftk-input.json <run>/pseudo/Si.upf <run>/dftk-result.json`。两个命令退出码均为 0；JLL 二进制探测、workbench 身份检查也为 0。[本次结果记录](phase4b/20260905T040945688395Z-1cc8a50c/result.json)保存完整脱敏命令及 cwd。

- 配置 SHA-256：`2f7aaf914ef6db5ccfa4c81a124b24c5bd32b27383d95c756c97266a22b63f65`。
- DFTK 生成输入 SHA-256：`618f46548779453dae52ed3a01a3a87d066ddf8583e5ea1b83f220670a07c87e`。
- QE 生成输入 SHA-256：`f634604331eab32dfc03daab4fb6c7abb704cbe75dd6c6f1b7c03feb47675fe2`。
- 配置、输入 hash、环境与 QE 实际二进制身份在 SCF 前写入当前运行记录。每轮用独立目录；两边读取同一份复制后校验的 Si 字节。完整原始数据保留在忽略的 `.work/scalar-baseline/<run_id>/`；未复用旧 `.save`。必要的小日志与结果完整脱敏发布，仅另去除行末空白；原始字节保持不变。[证据 manifest](phase4b/20260905T040945688395Z-1cc8a50c/evidence-manifest.json)分别记录原始与公开字节 SHA-256，未混用二者。

| 执行 / 检查 | 退出码与状态 |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p '*baseline*.py' -v` | 0；[41 项新增测试通过](phase4b/preflight/baseline-tests.log)，仅 synthetic parser/comparison fixtures，不是上游测试或真实物理证据 |
| 首轮 `20260905T040024884822Z-52c153c4` | 入口 1；QE SCF 0 且收敛，解析器错误使用内部参数名 `scf_has_converged`，DFTK NOT RUN；[失败记录](phase4b/20260905T040024884822Z-52c153c4/result.json)。按实际 XML 和 [QE 写入器](https://github.com/QEF/q-e/blob/qe-7.5/Modules/qes_write_module.f90#L2779)改为 `convergence_achieved`，加入回归。 |
| 第二轮 `20260905T040513792276Z-2bf66131` | 入口 1；QE SCF 0，DFTK 在 SCF 前因 `Model.terms` 字段错误退出 1；[失败记录](phase4b/20260905T040513792276Z-2bf66131/result.json)、[异常日志](phase4b/20260905T040513792276Z-2bf66131/dftk.stderr)。改为固定源码的 `term_types`，实际模型构造预检后再运行。 |
| 第三轮有效配对 | 入口 0；QE SCF 与 DFTK SCF/最终势对角化均收敛，输入可比性通过；数值一致性仍 REVIEW_REQUIRED |
| `git diff --check` | 0，交付前通过 |
| 保护范围与上游清洁检查 | [71 个 base 已跟踪文件逐字节不变](phase4b/preflight/scope-check.log)，两个上游 checkout 均 clean |

测试覆盖单位方向、非对称晶格、k 点乱序/缺失/重复/模整数等价、权重与自旋计数、最终收敛结果选择、零退出但未收敛、截断/缺字段/NaN、checksum、单全局参考和失败不复用历史。补充检查拒绝配置内 PW/PZ 不一致、原始与规范化总能量矛盾和全局占据/空态重叠。新增重叠检查曾揭示一个正例 synthetic fixture 本身不满足绝缘模型，[该开发失败日志](phase4b/preflight/baseline-tests-fixture-overlap.log)保留；只调整了人工片段，真实 case 和数值参数没有改变。初始 `pw.x -h` 探测不受该程序支持，退出 1，日志也保留在 preflight；它不是 SCF 通过证据。

最终无未解决的执行/输入 BLOCKED。独立环境重建、旧记录器 28 项测试、完整 DFTK 上游套件均 **NOT RUN**：本轮没有修改旧记录器或 bootstrap 路径，不为凑数重跑；历史 1387/1387 不计入本轮。QE 单独 NSCF/bands 不需要，**NOT RUN**。cutoff/k 点扫描、其他材料、SOC、MLP、力/应力/优化/MD 均 **NOT RUN**。下一阶段应由人工审查后决定收敛研究及能量参考约定检查；本轮不继续扩展。

没有改既有 FR-NC 验收条件、source lock、Project/Manifest/checksums 或历史报告；没有提交 UPF、波函数、源码副本、包缓存、凭证或私人绝对路径。只形成普通提交并推送指定新分支，不推 main、不创建 PR、不合并、不发布上游留言。

AI 协助：Codex 主任务编写配对运行/比较逻辑并串行执行计算；三个子代理分别协助固定 DFTK API/脚本、Si 来源与 XC、QE 解析与只读审计。人工维护者负责最终数值审查；不对未披露的模型名称作推断。
