# Phase 4A — UPF 验收与环境复现加固

日期：2026-09-05。分支：`codex/phase4a-validation-hardening`。
Base：`1e78bdb406f74dbae9601edd3a158cb04df24bd0`（与开始时远端 main 一致）。
原工作区 `git status --short` 为空。基于该已提交状态创建独立工作副本及新分支，没有 reset、stash、覆盖用户修改或改写历史。

**结论：真实 Mg 严格验收通过；错误元数据、错误加载身份及错误默认校验和均被拒绝；独立目录重建通过。** 本轮仅加固 workbench，没有实现 SOC，也没有开展 QE 或 LDA/LSDA 数值对拍。

## 审查发现的核实与修改

已阅读 workbench 的 CONTRIBUTING、交接文档、source lock、指定脚本、历史 JSON/source map、忽略规则，以及固定 DFTK 的 AGENTS/CONTRIBUTING 和相关解析器源码。workbench 没有额外 AGENTS；本轮没有修改两个上游源码目录。用户要求的“新 Julia 进程验证身份”适用于本轮，而非 DFTK 核心源码开发的持久 REPL 工作流。

| 问题与复现 | 旧行为 | 新行为与证据 |
| --- | --- | --- |
| 无关异常消息含 `unsupported` | 被分类为 REJECTED；总体可能 PASS | 执行旧源码表达式的回归实际失败，退出 1；最终测试拒绝该异常。精确匹配 ErrorException、完整消息及锁定 PspUpf 第 107 行的真实栈帧，才接受 SOC 拒绝。见 [旧回归](phase4a/legacy-red.log)、[单元测试](phase4a/unit-tests.log)。 |
| scalar、US/USPP/PAW、缺少 SO beta、索引问题、错误 l/j | 原脚本记录字段，没有 FR-NC 验收门槛 | 解析、元数据验证、构造检查分成简单函数。负例返回非通过，且不会进入 DFTK 构造；正常多径向 `(l,j)` 和明确索引重排通过。 |
| beta 位置与源 index 混用 | `betas[index]` 假设位置等于源索引 | 根据显式解析索引建立一对一字典映射。缺少索引、无法证明的剪枝变体为 UNSUPPORTED；重复、缺失、越界、关联不一致拒绝。 |
| 固定 checkout 不保证实际加载它 | 旧 bootstrap 对未跟踪 Manifest 的 DFTK 项目 instantiate；另行 clone 的 PPIO 没有实际绑定 | 新 workbench Project/Manifest 由 Pkg 生成，以相对路径 develop 两个固定 checkout；每次校验实际 pathof、checkout、UUID、版本、提交和清洁状态。历史 PPIO tree 当时确实匹配，不能据此说旧运行已经加载错包。 |
| 最小测试只依赖历史 bootstrap PASS | 更改源码后仍可能执行，旧标记不能证明身份 | minimal 入口使用相同新进程身份检查，并保存独立运行记录；不再信任旧 PASS 文件。上游 minimal 本轮 NOT RUN。 |
| 默认 Mg 固定标签未绑定内容 | 只计算 hash，不比较 source lock | 默认文件必须匹配 lock 中 SHA-256，改变字节的负例返回 8，parse_status 保持 NOT_RUN。 |
| 早期失败保留可误读的旧结果 | 共用 `results/upf-inspection.json`，新失败可能留下旧 PASS | 每次分配唯一 run_id 和目录，先写非通过 marker，再完成本次结果。历史 JSON 保留为历史；参数错误、缺少前提、异常和日志失败都有本次记录。 |
| Shell pipeline 只关注 Julia 退出码 | 过滤器或日志写入失败未完整判断 | 用 Python subprocess 替代 pipeline，逐项检查进程、过滤、JSON 和写盘。故障注入覆盖非零进程、零退出无 JSON、无效 JSON、过滤失败、日志写入失败和 JSON/退出码矛盾。 |

普通 `--mode inspect` 只产生 INFO_ONLY；运行器显式传 `--mode fr-nc`。严格验收只在解析、元数据以及预期 SOC 拒绝均满足时返回 0。JSON 分别记录四个状态字段、具体原因与退出码。完整退出码约定见 [脚本说明](../scripts/README.md)。

## 索引和角动量依据

固定 PseudoPotentialIO 的 [upf2.jl:410–467](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L410-L467) 表明：普通 beta 的 index 属性缺失或为 `*` 时才从标签补全；解析器按出现顺序收集记录，并移除全零 beta，不重编号。其 [upf2.jl:542–566](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L542-L566) 对 relativistic beta 只读取 index 属性，不从标签补全。因此无法从解析结果确定的关联不采用位置猜测，也不声称所有这些格式在物理上无效。

`j` 必须有限，`l=0` 只接受 1/2，`l>=1` 接受 `l±1/2`。容差为绝对 `1e-10`、相对 0，仅容纳文本浮点舍入；不把任意值四舍五入为合法 j。同一个 `(l,j)` 的多个径向投影子合法，不要求成对 j 分支，也不要求 PP_RELWFC。测试中的错误元数据是无径向数据的内存对象，不是物理赝势。

固定 DFTK 的 [PspUpf.jl:98–108](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L98-L108) 保留原有保护检查。Julia 真实抛错栈帧是该文件第 107 行的 `#PspUpf#63` 关键字方法；生成编号不固定，匹配保留函数名前缀、真实文件和行号。无关 unsupported、附加 gipaw 拒绝、不同异常类型、来源错误及构造成功都不能充当预期 SOC 拒绝。

## 环境记录

Pkg 初次生成时以原 DFTK Manifest 为解析种子，使用 `Pkg.PRESERVE_ALL`；157 个共享包版本未变化。额外直接依赖包括 JSON3 和实际使用的 Pkg/SHA/TOML/Test。没有编辑上游 Project，也没有改变 source lock。选定 Manifest 被明确允许提交，其余缓存与 `.work` 继续忽略。

| 项目 | 实测 |
| --- | --- |
| Julia | 1.12.7，新进程 |
| Active project | `<workbench>/environment/workbench/Project.toml` |
| 实际 Manifest | `<workbench>/environment/workbench/Manifest.toml` |
| Project SHA-256 | `80ba283d76c997492af04fa4546edeb39aa397839daef085137ba045ba56a3c4` |
| Manifest SHA-256 | `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37` |
| Source lock SHA-256 | `e1df6b6e926a57f129ccf7f50ea8ebd006d7239f46d530d96e19d67f16965a1b` |
| DFTK | 0.8.0；UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337`；commit `2f51b91213e26726fb9c6a17e5fae235a1412d01`；clean |
| PseudoPotentialIO | 0.3.3；UUID `cb339c56-07fa-4cb2-923a-142469552264`；commit `fec942781560c391f20214ba4cd85fb2431deb84`；clean |
| 实际 pathof | `.work/DFTK.jl/src/DFTK.jl` 和 `.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl`，在对应 workbench 根目录内 |

以上比较首先使用真实路径，之后才脱敏。Manifest 中两个开发依赖分别为 `../../.work/DFTK.jl` 和 `../../.work/PseudoPotentialIO.jl`。完整身份字段见下方运行 JSON。

## 实际命令与验收

以下命令从相应 workbench 根目录执行。下载缓存通过 `JULIA_DEPOT_PATH=<existing-cache>` 复用，`JULIA_PKG_OFFLINE=true`；这些占位符表示执行时的私有路径，未写入可迁移的 Project/Manifest。固定 DFTK 的 MPI 初始化需要本机执行权限，未更换 MPI 实现或依赖来绕过问题。

| 检查 / 实际命令 | 退出码 | 结果与证据 |
| --- | ---: | --- |
| `julia --startup-file=no tests/legacy_regression.jl <base-inspector>` | 1 | 旧逻辑真实 FAIL，暴露无关 unsupported 被接受；[日志](phase4a/legacy-red.log)。base-inspector 是 base 提交的原脚本。 |
| `python3 scripts/run_recorded.py tests` | 0 | 63 个 workbench Julia 断言通过：43 元数据、14 构造/门控、3 解析适配、3 实际包身份；[日志](phase4a/unit-tests.log)、[运行身份](phase4a/unit-20260905T022517446167Z-5486a6d5.json)。 |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_recorder.py` | 0 | 7 个记录器故障测试通过；[日志](phase4a/recorder-tests.log)。 |
| `python3 tests/test_cli.py` | 0 | 7 项 CLI 检查及历史文件不变检查通过；[日志](phase4a/cli-tests.log)、[退出码/run_id 明细](phase4a/cli-ledger.json)。 |
| `bash scripts/run_upf_inspection.sh` | 0 | 真实 Mg：parse PASS、metadata PASS、EXPECTED_SOC_REJECTION、overall PASS；[JSON](phase4a/mg-20260905T022522137872Z-e1106cef.json)。 |
| 独立目录 `setup_workbench.jl fetch --source-cache <primary>/.work` | 0 | 新 clone 两个固定 checkout；[日志](phase4a/rebuild-fetch.log)。 |
| 独立目录 `bash scripts/bootstrap_dftk.sh` | 0 | 保存的环境原样 instantiate，并由新 Julia 进程校验路径与身份；[日志](phase4a/rebuild-bootstrap.log)、[JSON](phase4a/rebuild-20260905T021831502128Z-2f2de3c2.json)。 |
| 独立目录脚本使用 `--project=<primary>/environment/workbench --check-environment` | 6 | 负例测试通过：尽管两目录 HEAD 相同且 clean，实际加载 primary 的包仍为 ENVIRONMENT_MISMATCH；[JSON](phase4a/wrong-environment.json)。 |
| 独立目录默认 Mg 附加一个换行后运行 wrapper | 8 | 负例测试通过：INPUT_MISMATCH，尚未解析；[JSON](phase4a/wrong-checksum-20260905T022039589823Z-96c0780d.json)。修改字节仅测试 checksum 门控，不作为物理输入验收。 |
| 恢复准确 Mg 字节后，在独立目录运行 wrapper | 0 | 重建后的真实 Mg 严格验收 PASS；[JSON](phase4a/rebuild-mg-20260905T022641863203Z-8dca2153.json)。 |
| `git diff --check` / shell syntax | 0 | 交付前检查通过；5 个 Shell 入口通过 `bash -n`。 |
| DFTK 上游 `:minimal` | — | **NOT RUN**。1387/1387 仅是历史 Phase 2 结果，不计入本轮测试数。 |

真实 Mg SHA-256：`19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`。来自既有、忽略目录中的记录样本，无需重新下载；其 PBEsol 家族仅用于元数据侦察，没有被称作 LDA/LSDA 数值基准，也未提交 UPF。

独立目录不带原 `.work`、原包环境或源码副本；先从本地 Git 缓存 clone 固定源码，再 instantiate 相同相对路径 Manifest。只共享下载缓存，没有删除或重建用户现有环境。重建后的 Manifest 校验和与主目录一致。

## FAIL / BLOCKED / NOT RUN 与剩余边界

- 旧回归的 FAIL 是必要的旧问题证据；对应新分类断言已通过。
- 首次受限运行中，MPI 在 DFTK 预编译时被系统拒绝，环境检查退出 6。相同依赖配置在获准的本机环境重试后通过；没有把首次运行写成 PASS。
- 开发中发现并修复了包在函数内加载引起的 Julia world-age 错误、过滤器自身失败时错误处理再次调用过滤器的问题，以及构造栈帧关键字方法名的匹配问题。CLI 测试曾把参数错误预期写成 BLOCKED，已按明确的 ARGUMENT_ERROR 合同修正。最终结果以本报告列出的 run_id 为准。
- 参数错误、缺失输入/源码、解析错误、错误元数据、错误环境与错误 checksum 的负例自身仍为非通过状态；“负例测试通过”仅表示正确拒绝。
- 上游 minimal、QE 版本验证、QE baseline、SOC 实现和数值对拍均 NOT RUN；没有自动进入这些阶段。
- 未支持的缺失 index/剪枝映射及不明确 relativistic 字段仍返回 UNSUPPORTED。未来扩展需单独给出格式依据和测试。
- Mg 再分发许可仍未核实；UPF 未提交。没有上游源码修改、issue/PR/评论、main 提交或历史改写。

交付前检查两个工作副本的 DFTK 和 PseudoPotentialIO 均处于要求的 commit 且 clean。source lock 以及 base 中全部历史 results 文件逐字节保留；未跟踪 UPF、下载源码、包缓存或私人绝对路径。可重复运行产生的完整临时记录位于忽略的 `results/runs/`；本报告所需脱敏证据单独保存在 `results/phase4a/`。

AI 协助：OpenAI Codex 执行了 workbench 实现、测试、源码检查和报告整理；维护者仍负责人工审查和后续科学解释。本轮停止于普通提交及指定分支推送，不创建 PR，不自动合并。
