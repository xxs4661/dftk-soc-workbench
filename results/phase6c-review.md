# Phase 6C review — charge-only Mg SOC SCF

两条真实、顺序执行且独立初始化的 SOC SCF 完成，A/B 各 **191 maps**（190 次迭代及 1 次额外闭环），均退出 0。双初态比较通过事前工程门槛；未放宽阈值、重启 SCF 或扩展物理参数。QE 输入仅准备，未执行。**数值审查仍为 REVIEW_REQUIRED**。

最终分项状态见 [status.json](phase6c/status.json)。A/B 和比较原记录保留各自执行时尚未准备 QE、尚未完成其他动作的状态；后续组合状态另存，不改写原始记录。

## 两个真实运行与双初态比较

- A：`20260906T151940Z-A-270110aa`，[终点](phase6c/20260906T151940Z-A-270110aa/result.compact.json)、[逐轮表](phase6c/20260906T151940Z-A-270110aa/maps.csv)、[逐 k 求解](phase6c/20260906T151940Z-A-270110aa/solvers.csv)、[日志](phase6c/20260906T151940Z-A-270110aa/run.log)。
- B：`20260906T153016Z-B-62835d43`，[终点](phase6c/20260906T153016Z-B-62835d43/result.compact.json)、[逐轮表](phase6c/20260906T153016Z-B-62835d43/maps.csv)、[逐 k 求解](phase6c/20260906T153016Z-B-62835d43/solvers.csv)、[日志](phase6c/20260906T153016Z-B-62835d43/run.log)。
- [独立只读 A/B 比较](phase6c/20260906T154035Z-compare-f24619d0/comparison.json)，退出 0；最终数组 hash 核对后才反序列化，没有重新求解。

| 实测量 | A | B |
| --- | ---: | ---: |
| 目标态 / 辅助态 | 24 / 6 | 24 / 6 |
| 映射 / closure | 191 / 1 | 191 / 1 |
| 实际 k 点求解数 | 573 | 573 |
| 累计 LOBPCG 迭代 | 10544 | 10685 |
| 累计 solver n_matvec | 230294 | 231494 |
| 未混合终点 L2 | 1.65423467e-09 | 1.65372679e-09 |
| 所有映射最大求解残差 Ha | 9.99824426e-11 | 9.99936044e-11 |
| 所有映射最大 Gram Frobenius | 5.54093834e-14 | 4.62432512e-14 |
| 终点 H[n_out] 旧 lambda 残差 Ha | 1.08230426e-08 | 1.08116775e-08 |
| 终点 H[n_out] Rayleigh 残差 Ha | 9.17152835e-09 | 9.15927994e-09 |
| 真实 Pauli norm(m)/norm(n) | 1.03143049e-13 | 9.83135237e-14 |
| Rayleigh 重算 f 最大差 | 7.10952385e-43 | 7.10671195e-43 |
| 完整 H[n_out] TR 作用相对误差 | 3.76888690e-17 | 3.70883157e-17 |
| Γ Kramers 原始谱差 Ha | 5.32907052e-15 | 2.22044605e-15 |
| ±k 原始谱差 Ha | 2.44249065e-15 | 8.43769499e-15 |
| H[n_out] Γ Rayleigh 成对差（诊断）Ha | 1.77635684e-15 | 1.33226763e-15 |
| H[n_out] ±k Rayleigh 差（诊断）Ha | 2.22044605e-15 | 3.10862447e-15 |
| 配对占据最大差 | 1.42324721e-49 | 7.90136067e-50 |
| 所有映射最高两态占据最大值 | 1.93498010e-109 | 1.93532268e-109 |
| 所有映射全局电子根误差 | 0.00000000e+00 | 0.00000000e+00 |
| 所有映射实空间电子数最大误差 | 8.52651283e-14 | 4.97379915e-14 |
| 所有映射轨道电子数最大误差 | 8.52651283e-14 | 5.15143483e-14 |
| 所有映射七项求和误差 Ha | 1.42108547e-14 | 1.42108547e-14 |
| 所有映射 DC 误差 Ha | 2.55795385e-13 | 2.27373675e-13 |
| 终点实空间电子数 | 10.000000000000002 | 10.000000000000004 |
| 终点轨道电子数 | 10.000000000000004 | 10.000000000000007 |
| 内部 E / Ha per cell | -57.325987985147734 | -57.32598798514773 |
| S/kB | 1.2426050669902275e-34 | 1.2426050665736324e-34 |
| E_entropy=-TS / Ha per cell | -1.2426050669902276e-37 | -1.2426050665736325e-37 |
| F / Ha per cell | -57.325987985147734 | -57.32598798514773 |

A/B 相对密度差 **1.52135611e-13**；绝对密度 L2 差 `5.08276287e-13`；
E/F 差各 **7.10542736e-15 Ha/cell**；同 k 最低16原始能级最大差 **8.94140664e-13 Ha**。
24 个共同态的 f 最大差 `3.77818344e-46`；μ 差 `5.54487012e-13 Ha` 仅作诊断，无平台内 μ 等同性门槛。

A/B 每条的 191 个输入势与 H 探针 hash 均不同，n_next→下一 n_in 的 hash 链连续。两条均只有最终一次候选和随后闭环；真实扩带未触发，24→48 与上限失败仅由合成测试覆盖。原始单态残差、各 k 电子份额、占据平台、E 七项和检查点 hash 保留；[汇总](phase6c/measured-summary.json) 是直接读取原记录，无新拟合或物理计算。

## 范围、冻结边界与实现

接受起点 `9ec5ef155ad6c078ad6379a6b32f23b7f27da7eb`；从干净工作区创建
`codex/phase6c-soc-scf`，保留所有历史。适用 `CONTRIBUTING.md` 已阅读，未发现适用的
`AGENTS.md`。本轮仅为固定 Mg 体系的 charge-only SOC SCF 原型，不是非共线磁性 XC、
物性收敛、唯一基态或上游原生 SOC 支持声明。

既有 361 个跟踪文件中只改两份 workbench 原型：

- `prototypes/fr_integration/hamiltonian.jl`：显式加入 temperature/smearing 参数及已有设置绑定；
  默认仍为零温/None。公共 Model 始终只有 Kinetic、AtomicLocal、Ewald、PspCorrection、Hartree、Xc。
- `prototypes/spinor/scf.jl`：通用密度检查/控制器接收实际 `n_electrons`，默认仍为历史 Si 的 8；
  新 SCF 不调用旧 Si 填充、标量能量或旧 A/B/C 任务。

新增模块分为 ensemble、矩阵自由目标态求解、SCF 编排；驱动器负责检查点/JSON。
没有新增全局登记或证书系统，没有给 matvec 新增文件读取/序列化/hash。
复用原 FR context、源绑定、P/D 与通用 density-map 控制器。
A/B 每轮重建 Hartree/XC，实际 X/f 产生 R/n/m；不裁负值、归一化、清零 m 或平均 TR 配对。

固定 DFTK 的 `Model` 显式接收六项时不会自动加入 Entropy；native convenience model 和
`TermEntropy`/occupation 路径存在标量 capacity=2 假设。因此公共能量仍走六项/分量因子，
第七项 FR 非局域只出现一次，熵单独按物理 spinor f 与空间权重计算。
源码依据为冻结 checkout 的 `src/Model.jl`、`src/standard_models.jl`、`src/terms/entropy.jl`、
`src/occupation.jl` 及本仓库 `prototypes/fr_integration/energy.jl`。

全局 FD 使用稳定 logistic、有界二分（最多 256 次，电子数误差 <=1e-12），保留极小 f，
不逐 k 填十态或缩放 f。禁带数值平台采用已记录的确定性中点规则。
初始目标 24、辅助 6；同一 n_in 下仅允许 24→32→40→48，所有提升的目标必须重新实际收敛。
辅助态不参与 f/n/E/S。最高两目标态占据 <=1e-10 是有限态工程诊断，不是无限空态尾部上界。

SCF 固定 alpha=0.1、总预算 400 maps；`sqrt(dvol)*norm(n_out-n_in)` 触发候选，
随后在候选输出上再执行一次真实映射。闭环失败不能返回旧 PASS。自己的上一轮轨道是唯一热启动来源。
所有本轮数值源码在 A/B 期间保持不变；终点重新核对配置、实际加载身份与执行源码 hash。

## 运行环境、输入与事先门槛

本轮 preflight、每条 A/B 的开始/结束及真实比较均在新 Julia 进程核对实际路径身份。
Julia 1.12.7；单 Julia/BLAS/FFT 线程、MPI size=1；CPU。
`Base.active_project()` 为 `<workbench>/environment/workbench/Project.toml`，实际 Manifest
位于同目录。先使用 realpath 比较，公开时才脱敏。没有更换环境后沿用已加载旧包的会话。

| 身份 | 实测与要求 |
| --- | --- |
| DFTK | 0.8.0；UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337`；commit `2f51b91213e26726fb9c6a17e5fae235a1412d01`；checkout clean |
| PseudoPotentialIO | 0.3.3；UUID `cb339c56-07fa-4cb2-923a-142469552264`；commit `fec942781560c391f20214ba4cd85fb2431deb84`；checkout clean |
| pathof | 分别为 `<workbench>/.work/DFTK.jl/src/DFTK.jl`、`<workbench>/.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl` |
| Project SHA-256 | `80ba283d76c997492af04fa4546edeb39aa397839daef085137ba045ba56a3c4` |
| Manifest SHA-256 | `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37` |
| source lock SHA-256 | `e1df6b6e926a57f129ccf7f50ea8ebd006d7239f46d530d96e19d67f16965a1b` |
| 新 Phase 6C 配置 SHA-256 | `fed341560f53663f580c37a8f691298aa24784957b49270c5e3f71289736c58c`；测试前保存，随后未变 |
| Mg UPF SHA-256 | `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256` |

真实 header：Mg、z_valence=10、FR-NC、full、has_so=true、PBESOL、无 NLCC。
一个 Mg，10 bohr 立方胞、位置 (0.17,0.23,0.31)，15 Ha，Γ 与 ±(0.125,0.0625,-0.1875)，
各空间权重 1/3，未约化。实际 FFT=40×40×40，NG=2777/2770/2770。
XC=`gga_x_pbe_sol + gga_c_pbe_sol`，仅 n 反馈；零温形式 XC 加非相互作用电子熵，
不是温度依赖 XC。tau=kBT=0.001 Ha，实际 Model 为 FermiDirac；不是 0.001 K。

A：严格均匀 Ne/Ω，seed=63001；B：乘 `1+0.02*(cos(2π(x+2y+3z))−gridmean)`，seed=64001。
坐标采用实际分数实空间网格，两初态正性/离散电子数均验证。每 k 按索引派生独立 ComplexF64
全列 QR 初态，未读取 Phase 6B 或另一条运行轨道。

门槛完整保存在 [phase6c.toml](../prototypes/soc_scf/phase6c.toml)：LOBPCG tol=1e-10/maxiter=300，
目标显式残差<=1e-9 Ha，Gram Frobenius<=1e-9；实空间/轨道电子数误差<=1e-8；
终点未混合密度 L2<=1e-8，自身密度 H 残差<=1e-7 Ha，Pauli `norm(m)/norm(n)`<=1e-7；
A/B 相对密度<=1e-6，E/F各<=1e-7 Ha，同 k 最低16原始能级<=1e-6 Ha；
七项/DC<=1e-8 Ha，F算术<=1e-12 max(1,|F|,|E|)，Rayleigh 重算 f 差<=1e-6；
Γ/±k谱差<=1e-8 Ha，TR作用归一化误差<=1e-10。未事后选阈值。

## 数值含义与终点来源

每轮 E 是同一 X/f/n_out 的完整七项内部能量，DC 核对使用 H[n_out] 的期望值；
`S/kB = -Σwk[f log f+(1-f)log(1-f)]`，`E_entropy=-tau S/kB`，`F=E+E_entropy`。
没有给 E 加经验常数，没有混入 n_next 的 XC 或旧本征值和，没有 native Entropy 或 fchi 熵翻倍。

正式本征值/f 来自实际闭环求解 H[n_in]，n_in 是上一候选的输出。
最终轨道生成 n_out，另在 H[n_out] 保存旧 lambda 残差、Rayleigh 商/残差和重算 f 的差。
完整 H 的 TR 作用实测在 H[n_out]；Γ/±k 原始谱与正式 f 配对来自闭环 H[n_in]。
自身密度下的成对 Rayleigh 差另列为诊断，**不是再次对角化**。
TR 使用 `i sigma_y K` 和真实 G+k 的一一映射；未要求非 TRIM 点内部任意两重简并。

密度残差为 sqrt(dvol) 加权绝对 L2；A/B 相对密度为
`norm(nA−nB)/max(norm(nA),norm(nB))`，相同 dvol 抵消。
谱比较按分数 k 模整数倒格矢唯一匹配，不按顺序/谱值、不平移或拟合。
H 残差为每个归一化目标列的欧氏范数，Gram 为 `norm(X'X−I)` Frobenius。
完整 TR 相对误差按既有 `norm(a−b)/max(norm(a),norm(b),1)`；Pauli 范数含全部三分量。

本 Mg 在 tau=.001 的实际谱处于数值禁带平台，驻定诊断 `NO_RESOLVABLE_PARTIAL_OCCUPATIONS`；
没有离端点可分辨的 f 可用于对数驻定残差，空集合返回零不是物理证明。
非平凡分数 f 的驻定、不同 k 电子份额与自由能极值由明确标注的 synthetic tests 验证。
实际 -TS 极小，Float64 的 F 与 E 可显示相同，但独立 S/-TS 数值仍保留，并非偷偷退回固定占据。


## 实际命令、测试及失败记录

所有 Julia 命令使用 `julia --startup-file=no --color=no --project=environment/workbench`；
环境为 `JULIA_LOAD_PATH=@:@stdlib`、`JULIA_PKG_OFFLINE=true`、`JULIA_NUM_THREADS=1`、
`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`，复用已有冻结 Julia 下载缓存。原始路径仅在忽略记录内，
公开 `command.json` 只脱敏路径；实际 argv、开始/结束和进程退出码均保存。未安装、升级或修改包环境。

| 本轮实际执行 | 结果 / 退出码 | 对应证据 |
| --- | --- | --- |
| `tests/soc_scf/runtests.jl .work/phase6c/20260906T153037Z-tests-2afdc3e7` | **438/438，0** | [日志](phase6c/20260906T153037Z-tests-2afdc3e7/run.log)、[结果](phase6c/20260906T153037Z-tests-2afdc3e7/test-result.json) |
| `tests/fr_integration/runtests.jl .work/phase6c/20260906T151424Z-regression6b-0083f6a9` | **241/241，0** | [日志](phase6c/20260906T151424Z-regression6b-0083f6a9/run.log) |
| `tests/spinor_scf/runtests.jl .work/phase6c/20260906T151532Z-regression5b-0967b49d` | **544/544 + 228/228，0** | [日志](phase6c/20260906T151532Z-regression5b-0967b49d/run.log) |
| `python3.12 -m unittest discover -s tests/soc_scf -p test_qe_preparation.py -v` | **24/24，0** | [日志](phase6c/preflight/qe-preparation-tests-attempt-3.log) |
| `scripts/run_soc_scf.jl A .work/phase6c/20260906T151940Z-A-270110aa` | **PASS，0** | [命令](phase6c/20260906T151940Z-A-270110aa/command.json) |
| `scripts/run_soc_scf.jl B .work/phase6c/20260906T153016Z-B-62835d43` | **PASS，0** | [命令](phase6c/20260906T153016Z-B-62835d43/command.json) |
| `scripts/compare_soc_scf.jl RAW_A_RESULT RAW_B_RESULT NEW_COMPARISON_JSON` | **PASS，0** | [实际 argv](phase6c/20260906T154035Z-compare-f24619d0/command.json) |
| `python3.12 scripts/prepare_soc_qe_input.py --run-a ... --run-b ... --comparison ... --output-dir benchmarks/mg-soc-fermi` | **PREPARED_NOT_EXECUTED，0** | [实际 argv 与 hash](phase6c/preflight/qe-final-preparation/command-and-hashes.json) |

438 项是 workbench 测试，不冒充上游测试或真实 SCF：含全局 FD/容量/权重/平移/溢出/平台/驻定与熵，
Ne=10/默认8控制器、错误归属与闭环/预算、小 alpha、错误占据/求解、实际 Mg 上的合成复杂轨道与能量夹具，
温度默认兼容、失败发布、k 映射与检查点比较。Hartree 势变化范数 `0.0813442906762512`、
完整 XC 势变化范数 `0.17852661224288738` 分别实测；等 f 幺正密度误差 `5.52e-17`，
不同 f 幺正混合导致密度 L2 改变 `9.53e-4`。这些是夹具，不是额外 Mg SCF。
帮助/缺参数、失败后不保留 PASS、旧目录拒绝也在实际新测试中执行。负例测试通过表示错误对象仍被拒绝。

早期失败均保留，未改变数值门槛：

| 尝试 | 实际结果、原因与处理 |
| --- | --- |
| ensemble-only attempt 1 | 退出1，测试语法歧义；修正后最终模块进入438项通过。[原日志](phase6c/preflight/ensemble-only-attempt-1/run.log) |
| temperature attempt 1 | BLOCKED / tests NOT_RUN，退出143；沙箱 MPI 导入前置失败。使用已有缓存并授权执行后47项通过，未改依赖。[阻塞记录](phase6c/preflight/temperature-attempt-1-bootstrap.json) |
| 最初 QE 准备器测试 | 退出1，系统 Python3.9 缺少 tomllib；改用已安装 Python3.12.14，最终24项通过。[原日志](phase6c/preflight/qe-preparation-tests.log) |
| `20260906T152327Z-tests-fb049534` | 退出1，新增比较测试的数字/点号语法错误，测试集合未执行；修正后重跑。[原命令/退出码](phase6c/20260906T152327Z-tests-fb049534/command.json) |
| 首次 staged diff 检查 | 退出2，公开CSV的CRLF和日志尾随空白；仅规范化公开文本并更新公开hash，原始数值文件不变。[记录](phase6c/preflight/diff-check-initial.json) |
| comparison-only attempt 1 | 39项通过、1个fixture错误：向String字典插入Bool；改为仍非法的字符串注入，保持拒绝断言，最终56项通过。[原日志](phase6c/preflight/comparison-only-attempt-1/run.log) |

中间 380/380、436/436 和各 standalone 结果另保留，不累计成最终测试数。真实 A/B 没有失败、
中断、恢复或重试；进程等待句柄、完成记录与退出码均核对。所有原始 run 目录唯一，驱动器拒绝旧目录；
PASS 在必要摘要/检查点/身份复核后发布。只有数组被序列化，未序列化 context/IdDict token。
每轮保留滚动最新检查点及首轮/候选/闭环/失败专用检查点；未实现自动恢复。

## QE 准备、公开证据与停止点

唯一输入见 [qe.in](../benchmarks/mg-soc-fermi/qe.in)、[参数](../benchmarks/mg-soc-fermi/parameters.json)、
[对照清单](../benchmarks/mg-soc-fermi/checklist.md)。输入 SHA-256：
`4d76b661c9a1c620da19e6f5db9dd9ee1e8651715bf9d421adce6db58c4d9476`。
同 Mg/晶胞/三点、PBEsol、10电子、24个spinor态；noncolin/lspinorb=true、起始磁化0、无nspin；
ecutwfc=30 Ry、ecutrho=120 Ry、FD degauss=.002 Ry，关闭对应约化，使用相对 pseudo/outdir。
关键字依据 [QE 7.5 固定文档](https://gitlab.com/QEF/q-e/-/raw/qe-7.5/PW/Doc/INPUT_PW.def)；
QE 的 E/F 输出约定及未来核对事项见清单中的官方文档/开发者回复。**未启动 pw.x**，
不声称输入已由 QE 验证或已完成 QE-aligned SOC。未来必须分别比较内部 E 与 F，不能复用旧 Si 八电子标量解析假设。

所有历史配置、报告、checksums、source lock、Project/Manifest、UPF 和两个上游源码保持不变，
[冻结边界](phase6c/boundary.json)核对了基线361份文件。A/B 执行时 HEAD 仍为接受起点，
实际新实现以执行文件 hash 记录，并与交付数值源码逐项一致；不声称起点已有本轮实现。
公开精简表没有原始轨道、大数组、UPF 或包缓存；[export-receipts.json](phase6c/export-receipts.json)
分别列出原始和公开文件 SHA-256及脱敏/摘取规则。原始数组和详细单态记录在 `.work/phase6c/<run_id>/`。
内部相对链接、隐私/凭证扫描、无UPF/二进制跟踪及 `git diff --check` 见 [交付检查](phase6c/delivery-checks.json)。

当前没有未解决的执行 FAIL/BLOCKED；早期已解决的失败如上。**NOT_RUN**：QE SOC 对拍、旧 A/B/C、
未受影响 Phase 6A 全套及完整上游测试；历史1387/1387、241/1272等不作为本轮新结果。
真实扩带未触发；可分辨部分占据的真实驻定检验不适用（每条0个检查、72个排除），合成测试单列。
**NOT_IMPLEMENTED**：非共线磁性 XC；**NOT_IMPLEMENTED_BY_THIS_PHASE**：上游原生支持。
未证明 cutoff/k/温度收敛、唯一基态、材料物性、GPU/AD 或通用接口。
下一科学门槛是首次独立 QE SOC E/F 对拍；本轮结束并等待人工审查，不自动进入该步骤。

AI 分工及限制见 [英文入口](../docs/upstream-coordination-summary.md)（250词）和
[上游问题表](../docs/soc-upstream-risks.md)。协调者及三个子代理的具体模型标识未暴露，未猜测；
本轮为 AI 辅助实现/审查，不等同独立人类专家、维护者审查或第三方复跑。未发邮件、上游留言或PR。
普通提交只推送指定分支；最终 SHA 在提交后回复中给出，不 amend 或改写历史。
