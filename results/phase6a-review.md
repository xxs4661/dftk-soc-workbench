# Phase 6A：独立相对论非局域算符

**本轮工程验收 PASS；数值结论为 `REVIEW_REQUIRED`，等待人工审查。**
真实 Mg FR-NC 数据已用于构造自旋角投影子，并实际作用于一般复数输入。
独立 L·S 核、解析径向函数、标量退化和时间反演检查均通过。
这不是 DFTK 主线 SOC 支持、SOC SCF 或 QE SOC 对拍。

- Base：`c235481e0a3eb149759d12293cbf005916ab09fb`。
- 分支：`codex/phase6a-relativistic-projectors`；从指定 base 新建，起始工作区干净。
- 唯一真实入口 run_id：`mg-si-20260905T164800Z`；退出码 **0**。
  run_id 仅为唯一标签；实际开始/结束为 **2026-09-05 16:22:47.274 / 16:22:53.779 UTC**，以 JSON 时间字段为准。
- [真实结果](phase6a/real-mg-si.json)、[真实日志](phase6a/real-mg-si.log)、
  [最终测试](phase6a/tests-final.json)、[日志](phase6a/tests-final.log)、[原始/公开 hash 清单](phase6a/evidence-manifest.json)。
- 普通提交 SHA 在提交后回复给出，不修改报告以加入自身提交 SHA。

## 真实输入、通道和 D 映射

两个本地文件均由内容 hash 确认，没有恢复下载、换家族或更改值。

| 输入 | SHA-256 | 本轮用途 |
|---|---|---|
| Mg，原 fully relativistic NC / PBEsol | `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256` | 元数据、径向 beta、独立非局域算符 |
| 原 B0 scalar NC Si / LDA | `686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805` | 由真实标量输入建立的 synthetic 完整退化通道回归 |

Mg 解析为 UpfFile，既有严格元数据验证 PASS。原 DFTK 构造器仍在冻结的
`PspUpf` SOC 保护位置返回 **EXPECTED_SOC_REJECTION**；核对了异常类型、完整消息和抛出位置。
新模块从解析对象读取，没有设 `has_so=false`、改写 UPF 或调用被拒绝的构造结果。

| 内部通道 | source beta / relbeta index | parsed position / 原 D 行列 | l | 2j | 块内径向编号 |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 1 | 0 | 1 | 1 |
| 2 | 2 | 2 | 0 | 1 | 2 |
| 3 | 3 | 3 | 1 | 1 | 1 |
| 4 | 5 | 5 | 1 | 1 | 2 |
| 5 | 4 | 4 | 1 | 3 | 1 |
| 6 | 6 | 6 | 1 | 3 | 2 |

真实文件共有 **6 个径向 beta**：s₁/₂、p₁/₂、p₃/₂ 各两个。
原 D 为 6×6 对角矩阵且有正负项；内部以 parsed positions `[1,2,3,5,4,6]` 同时重排两轴。
源 index 仅关联元数据，不能替代压缩矩阵下标。缺失、重复、无法关联、剪枝歧义或越界输入明确拒绝。
同一 (l,j) 的两个径向投影子全部保留。真实 Mg 的 D 恰为对角；非对角、非正定径向块由 synthetic 测试覆盖。
不同 (l,j) 的非零 D 耦合被明确拒绝，没有静默丢弃。未要求 PP_RELWFC 或每个 l 必须有两个 j 分支。

唯一列标签表为 `(atom,l,2j,2mj,radial)`，P 与 D_expanded 共用。
每原子展开数为 **2×2 + 2×2 + 2×4 = 16**，没有再乘自旋因子 2 或 2j+1。
真实 Mg 没有 d/f 通道；l=2、3 的角向、径向、核及退化检查全部明确属于 synthetic。

## 单位、积分、球谐与 Fourier 约定

[公式/接口说明](../prototypes/relativistic/CONVENTIONS.md)包含固定源码链接、独立参照依据及列基变换。
实际规范为 `b_internal=PP_BETA_raw/2`、`D_internal=2D_raw`，其中 PP_BETA 为 r·beta。
完整算符的净 Ry→Ha 换算是 1/2；测试中的 `b=raw,D=D_raw/2` 给出相同算符，误差 **0**。
原数组被复制保留，测试确认解析对象不变；不分别归一化 beta，也不假定所有 UPF beta 使用同一种能量量纲。

径向完整因子 `F_l=4π integral r*b_internal*j_l(qr) dr`。
生产返回 `F_l/q^l`，与 `q^l*Omega_ljmj` 相乘。冻结 Hankel 的 4π 和 q^-l 语义已核实，没有漏乘或重复。
本轮使用一条稳定的 modified-Hankel 实现：物理 r 网格上的冻结 DFTK 求积规则，
`|qr|<=0.5` 时使用收敛级数计算 `j_l(qr)/(qr)^l`，较大参数使用冻结快速表达式。
这是针对源码明确警告的小参数消减误差作出的实现选择；在正式测试前固定，没有调门槛或修改上游。

Mg 原网格 **1510 点，0–15.09 bohr，步长 0.01 bohr**；各 beta 声明 cutoff index=160，
积分上限 **1.59 bohr**。其后原始样本确为零。实际规则为 `simpson_uniform`，包括末区间处理。
没有额外截短、外推原点、重复乘 PP_RAB 或修改真实径向数值。
q=0 时 s 因子取有限极限，l>0 完整 P 为零；不计算零向量方向，也不在 NaN 后补零。
对 0、1e-8、1e-4、0.2、0.9、2.3、4 bohr⁻¹ 保存了所有通道的 [径向值](phase6a/mg-radial.csv)。

复球谐采用 Condon–Shortley 相位，与实心实球谐的关系由显式等式定义；
独立 Legendre 点值参照覆盖 Y00、Y10、Y11、负 m 共轭关系和非轴向复数方向。
CG 使用请求中的 j± 相对符号，2j/2mj 为整数；j 在有限性及绝对 1e-10、相对 0 验证后转换。
行号保持 `sigma+2*(G-1)`，分量顺序 up/down，Pauli sigma_y 为 `[0 -i; i 0]`。
P 的相位是 `exp(-i*q·R)*(-i)^l/sqrt(Ω)`；Cartesian 与 fractional 的 2π 只转换一次。

## 独立数学与径向证据

全部误差使用预声明的 `norm(actual-reference)/max(norm(actual),norm(reference),1)`；
本应为零的量使用绝对范数。算符/能量统一为 Ha，q/r 为 bohr⁻¹/bohr，角函数无量纲。
单独径向数值采用上述 beta/D 成对规范，不把其量纲错误推广给所有转换器。

| 检查 | 最大归一化误差 | 预声明门槛 |
|---|---:|---:|
| 独立复球谐点值 | 3.23107e-16 | 1e-12 |
| 独立最高权态/Jminus 与生产 CG 列 | 2.50314e-16 | 1e-12 |
| CG 正交性 | 1.43329e-16 | 1e-12 |
| 独立 L·S 的 Pi_j 与 U_j U_j† | 1.37383e-16 | 1e-12 |
| Jz / J² 标签 | 0 / 3.35117e-16 | 1e-12 |
| Gaussian 完整 F，两个固定网格 | 5.14075e-15 | 1e-8 |
| Gaussian modified F/q^l，额外小 q 标度核对 | 6.73458e-14 | 1e-8 |
| synthetic 独立非局域核 | 4.24226e-16 | 1e-11 |
| synthetic l=0..3 完整标量退化 | 2.22530e-15 | 1e-11 |
| synthetic 非局域能量两路径 | 2.22045e-16 | 1e-11 |

L·S 参照由轨道升降算符和 Pauli/2 独立构造，未调用生产 CG。
除投影幂等、互斥、完备、rank/trace 外，测试核对有序 Jz/J² 标签和 CG 列相位。
独立核直接收缩未耦合 Y、Pi_j、径向函数和 D，不是再调用生产 P 后计算 PDP†。
synthetic 核使用解析 Gaussian 径向函数，并含非对角 D、不同 j± 径向/耦合和非零虚部自旋翻转。
故意错误的相对符号即使仍使算符厄米，也被独立核拒绝。

Gaussian 使用 a=0.7、rmax=12 bohr，固定 2401/4801 点，`a*rmax²=100.8`，尾部指数极小。
两网格完整 F 最大误差分别为 **4.30e-15 / 5.14e-15**，不要求舍入量级的误差单调。
完整 [56 项解析比较](phase6a/gaussian-radial.csv)以及 modified F 小 q 检查均保留。

真实 Mg 的第二路线为 **256-bit 初等 Bessel 递推 + 物理网格梯形求积**。
它不调用生产核或 Simpson；最大 modified 径向差为 **1.20254e-6**。
这是两个离散积分规则的敏感性，**不是严格误差上界，也不是 Gaussian 误差或机器精度一致性失败**。
没有通过加密真实网格、调 cutoff 或调容差消除该差异。

## 实际 Mg 算符与原 Si 标量退化

Mg 的预声明几何为 10 bohr 立方归一化体积 Ω=1000 bohr³，原子位置 fractional `[0.17,0.23,0.31]`。
13 个固定 G 分别用于 Γ、`k=[0.125,0.0625,-0.1875]` 及 −k。
每个 k 的 P 为 **26×16**；合并 39 个 q 的 P 为 **78×16**，D_expanded 为 16×16。
合并矩阵仅是原子 Fourier 核的代数探针，跨点矩阵元不冒充物理 Bloch 跨 k Hamiltonian。
只有这一小型问题显式构造 78×78 核；实际 Si 平面波基始终矩阵自由。

| 真实 Mg 检查 | 归一化/零量绝对误差 |
|---|---:|
| 生产 CG 核与独立 L·S 核完整矩阵 | 3.80739e-17 |
| 两核对一般复数多列输入的作用 | 6.99560e-18 |
| dot(x,Vy)=dot(Vx,y) | 2.16840e-19 |
| 包含 q→−q 的时间反演 | 5.12074e-18 |
| T²=−I | 0 |
| 原子平移 P 相位 / V 协变 | 6.62129e-17 / 6.44615e-18 |
| 多原子作用等于单原子作用之和 | 4.12893e-18 |
| 固定 q/R 的体积 P / V 缩放 | 2.99368e-17 / 4.12724e-18 |
| 非局域期望与投影空间收缩 | 0 |

这些检查均低于 1e-11；核参照在真实 Mg 上共享所声明的径向离散规则，角向路线独立。
三个 k 的实际复数输入作用范数分别约 **0.0082453 / 0.0081467 / 0.00664867**，没有仅重复元数据报告。
合并探针的自旋翻转块范数 **2.71714e-5**，其虚部范数 **1.60011e-5**；未人为放大 Mg 的 j 差异。
加权探针非局域期望为 **−0.001694088161896329 Ha**，两种收缩一致；
输入是 Frobenius 范数为 1 的随机复数多列矩阵和诊断权重，不冒充物理占据态或每胞 DFT 总能量。

原 Si 仅从真实标量数据复制**相同径向函数、相同 D 块、完整 j/mj**的人工退化模型。
在原 B0 30 Ha 八点、NG=2085–2120 的实际平面波基上，逐点与冻结 DFTK 原生非局域算符提升比较。
每点原 scalar 投影列数 36，新 spinor 列数 72（两原子）。最大作用差 **5.92426e-16**，
完整 [八点结果](phase6a/si-scalar-limit.csv)保留。没有求解本征态、密度或 SCF。
没有平均真实 FR 通道，也没有宣称这是 Si FR 输入或 Si SOC benchmark。

## 命令、测试、记录与冻结边界

从仓库根目录，在新 Julia 进程中使用既有缓存；其私人路径不公开。
`JULIA_LOAD_PATH=@:@stdlib`、`JULIA_PKG_OFFLINE=true`，Julia/BLAS/OMP 各一线程。
没有 instantiate、下载、升级、重建依赖或修改 Project/Manifest。

| 实际入口 | 退出码/结果 | 证据 |
|---|---|---|
| `julia --startup-file=no --color=no --project=environment/workbench tests/relativistic/runtests.jl .work/phase6a-preflight/tests-attempt-1` | 0；1272/1272 | [首次日志](phase6a/tests-first.log) |
| 同上，输出目录为 `.work/phase6a-preflight/tests-attempt-2` | 0；**1272/1272** | [最终日志](phase6a/tests-final.log) |
| `julia --startup-file=no --color=no --project=environment/workbench scripts/run_relativistic_projectors.jl .work/phase6a/mg-si-20260905T164800Z` | 0；PASS | [真实记录](phase6a/real-mg-si.json) |
| 新入口 `--help` / 缺少参数 | 0 / 2，符合预期 | [CLI 台账](phase6a/cli-ledger.json) |
| synthetic throw / nonfinite / incomplete | 均为 1；本次 JSON 均 FAIL | [最终测试记录](phase6a/tests-final.json)及对应 synthetic 日志 |
| 请求已有 synthetic PASS 目录 | 2；旧文件字节不变 | 最终测试断言及日志 |
| 独立原始数组审计 | 0；PASS | [审计 JSON](phase6a/independent-raw-audit.json)、[实际命令/日志](phase6a/independent-raw-audit.log) |

独立审计首次启动退出 **1**：误用缺少 JSON3 的仓库本地缓存；在读取原始计算数组前失败。
[失败日志](phase6a/independent-raw-audit-first-launch.log)保留；改回已核对的既有共享缓存后退出 **0**，
没有安装/升级依赖或重跑物理算符。审计重新收缩保存的 P/D/X、复核 TR 和 Si 八点作用误差，
但未保存的平移/体积/双原子 P 未另行重建，不声称这些值也被原始数组独立复算。

最终重跑补齐了测试入口的执行源码 hash，确保最后的有限性保护由同一组最终文件覆盖。
首次 PASS 保留，不将两次重复测试相加宣称 2544 个不同测试；本轮新增断言数为 **1272**。
所有 synthetic 元数据/函数/故障对象明确标记，不能替代真实 Mg/Si 运行。
负例覆盖错误 j/index/parsed position、cross-block D、重复删除径向通道、单边单位或 D 重排、
r/4π/q^l/体积因子、错误 CG/共轭/简并计数、非对角 D 丢失和旧 PASS 复用。

实际环境身份 PASS：Julia **1.12.7**；workbench Project/Manifest 均为预期真实路径，
Manifest SHA-256 **`5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`**。
DFTK **0.8.0**，UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337`，实际加载冻结 checkout
`2f51b91213e26726fb9c6a17e5fae235a1412d01`；PPIO **0.3.3**，UUID
`cb339c56-07fa-4cb2-923a-142469552264`，实际加载 `fec942781560c391f20214ba4cd85fb2431deb84`。
两个 checkout 均 clean。先比较真实路径再脱敏，见[身份记录](phase6a/test-identity.json)。

配置在测试前固定，SHA-256 **`76ad86c37b49f3aa1b5aa46c64649b5fc285633099c07c477182de14241c3488`**，
见[预记录](phase6a/settings-before-tests.json)。真实入口 12 个、最终测试 18 个执行文件 hash 均与交付一致。
base 全部 **266 个已跟踪文件逐字节不变**，含 FR 验证器、Phase 4/5 历史数据、SCF/能量实现和冻结环境；
见[边界核对](phase6a/source-boundary.json)。`git diff --check` 及 `git diff --cached --check` 均退出 0，PASS。
原始探针/向量约 **5.0 MB** 留在忽略目录，公开只含摘要、选定矩阵/径向值、测试与日志。
原始与脱敏文件各自记录 hash，没有提交 UPF、完整径向数组、波函数或稠密 Si Hamiltonian。

## 状态、局限与停止

`metadata_status=PASS`；`angular_validation_status=PASS`；`radial_validation_status=PASS`；
`independent_operator_validation_status=PASS`；`scalar_limit_validation_status=PASS`；`real_fr_runtime_status=PASS`。
`numerical_review_status=REVIEW_REQUIRED`；`soc_scf_status=NOT_IMPLEMENTED`；
`qe_soc_benchmark_status=NOT_RUN`；`upstream_native_support=NOT_IMPLEMENTED_BY_THIS_PHASE`。

没有遗留物理测试 FAIL/BLOCKED。新 SCF、Phase 5B A/B/C 重跑、QE、完整上游套件、
更大材料/cutoff/k 扫描、力/应力、MLP 均 **NOT_RUN**；历史 544/228/1387 不计入本轮通过数。
本轮数学正确性和两个受限输入的工程一致性不能替代 SOC 能带或物理精度对拍。

Phase 6B 如获授权，需要另行接入 spinor 非局域 Hamiltonian 作用、FR 通道输入与对应能量接口。
**Phase 5B 的 scalar-factor 能量桥接仅适用于自旋无关空间算符**；SOC 非对角项必须通过
完整 spinor PDP† 计算，不能把上下分量当作独立标量能量相加。现有电荷/XC/能量归属需要单独集成审查。
本轮未作这些修改，没有进入 SOC SCF 或调试 SOC 能带。

仅普通提交并推送指定新分支，不推 main、不创建 PR、不合并或发布上游留言。完成后停止，等待人工审查。
