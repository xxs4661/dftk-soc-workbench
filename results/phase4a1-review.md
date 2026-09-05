# Phase 4A.1 — 记录器审查修复

2026-09-05。分支 `codex/phase4a-validation-hardening`。
本轮 base / 已审查提交：`a37de03c6ddcaa154b43b4d349affcf2a77cafa7`。
开始时工作区干净，HEAD 等于该提交，并通过祖先检查；保留既有提交，不改写历史。

**结果：原有记录器测试 7/7、新增测试 21/21、真实 CLI 7 项及真实 Mg 严格验收全部通过。**
新增 21 项包含原附件的 5 项；附件独立重跑不重复计入总数。

已阅读 CONTRIBUTING.md 和人工审查的 REVIEW.md、测试脚本、reviewer-contract-tests.log；没有适用的额外 AGENTS.md。附件作为审查证据，执行范围以用户本轮要求为准。

| 发现与复现 | 旧行为 | 本轮修复 |
| --- | --- | --- |
| R1：运行附件的 FAIL/0、PASS+parse FAIL、schema 999、严格动作收到 INFO_ONLY 四个反例 | 都返回成功；已在 base 实际复现 | 按动作校验 schema 2、字段类型/状态、实际退出码、阶段顺序与总体状态。严格成功须环境/解析/元数据 PASS 和 EXPECTED_SOC_REJECTION；矛盾返回 ERROR/9。 |
| R2：附件将 environment 设为 null | 先写 PASS，随后 AttributeError，实际复现 | environment/input 若存在必须是对象；缺少成功环境不得放行。先完成 JSON/摘要构造和临时写入，发布摘要后最后原子替换 result.json。失败生成不含异常嵌套字段的新 ERROR。 |
| C1：CLI ledger 父目录未创建 | 代码依赖预先 mkdir，静态核实成立 | 写 ledger 前 mkdir；真实 CLI 从父目录不存在的状态运行成功。旧忽略目录证据临时移开后原样恢复，并逐文件校验未变。 |

identity/tests/minimal/bootstrap 各自校验对应 worker 动作，成功时 UPF 阶段均为 NOT_RUN。合法 JSON worker 的失败码 2–9 保留；文本 bootstrap setup 的已知失败保留 BLOCKED/7，意外退出转 ERROR/9，并保留 worker_exit_code。开发审查中发现的 bootstrap 状态不一致也加入回归并修复。

新增测试覆盖 environment/input 的 null、错误类型、缺失成功环境、字段类型/状态、动作混用、失败码保留、摘要生成和写入失败、发布顺序及无法写盘。摘要故障在最终 PASS 阶段注入，确认此前结果仍为 BLOCKED，失败后当前结果为 ERROR；没有提前发布 PASS。完全无法写盘时返回 9，并在 stdout/stderr 明确报告持久化失败。原附件 5 个测试与拒绝断言的 AST 与仓库版本完全一致。

## 本轮执行证据

命令从 workbench 根目录运行。Julia 使用既有固定缓存 `JULIA_DEPOT_PATH=<existing-cache>`、`JULIA_PKG_OFFLINE=true`，以新进程执行；本机权限用于固定 DFTK 的 MPI 初始化。没有更换依赖。

| 实际命令 / 检查 | 退出码 | 结果与日志 |
| --- | ---: | --- |
| base：`python3 <review-evidence>/test_phase4a_recorder_contract.py --repo "$PWD" -v` | 1 | 5/5 反例暴露旧问题；[red 日志](phase4a1/reviewer-red.log)。旧 recorder Git blob 为 `12e8cf6ee58c3b69607627a16280a09ed6296dd3`。 |
| 修复后执行同一附件命令 | 0 | 5/5 通过；[green 日志](phase4a1/reviewer-green.log)。 |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_recorder*.py' -v` | 0 | 原 7 + 新 21 = 28 个测试方法通过（另有参数化子例）；[日志](phase4a1/recorder-tests.log)。仅 synthetic worker 记录器协议测试，不代表 Julia/环境/赝势验证。 |
| `python3 tests/test_cli.py` | 0 | 7 项及历史文件不变检查通过；[日志](phase4a1/cli-tests.log)、[退出码与 run_id](phase4a1/cli-ledger.json)、[父目录与历史恢复记录](phase4a1/cli-execution.json)。负例退出码依次为参数 2、缺输入 7、解析 3、缺源码 7。 |
| `bash scripts/run_upf_inspection.sh` | 0 | 真实 Mg 严格验收 PASS；[运行日志](phase4a1/mg-run.log)、[完整权威 JSON](phase4a1/mg-20260905T030611379883Z-0094f2da.json)。 |
| `git diff --check` | 0 | 交付前通过。 |
| 保护范围与来源检查 | 0 | [记录](phase4a1/scope-check.log)：35 个既有 results/environment/config/原记录器测试文件逐字节不变，Julia 验证/运行/环境/setup 脚本不变，上游 checkout 均 clean。 |

Mg run_id：`20260905T030611379883Z-0094f2da`；environment PASS、parse PASS、metadata PASS、construction EXPECTED_SOC_REJECTION、overall PASS。
输入实测与锁定 SHA-256 均为 `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`。
该 PBEsol Mg 仍仅用于元数据侦察，不是 LDA/LSDA 数值对拍基准。

新 Julia 进程实际身份：Julia 1.12.7；active project 为 `<workbench>/environment/workbench/Project.toml`，Manifest 为同目录 `Manifest.toml`，SHA-256 `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`。
实际加载 DFTK 0.8.0（UUID `acf6eb54-70d9-11e9-0013-234b7a5f5337`）来自 `.work/DFTK.jl/src/DFTK.jl`，commit `2f51b91213e26726fb9c6a17e5fae235a1412d01`；PseudoPotentialIO 0.3.3（UUID `cb339c56-07fa-4cb2-923a-142469552264`）来自 `.work/PseudoPotentialIO.jl/src/PseudoPotentialIO.jl`，commit `fec942781560c391f20214ba4cd85fb2431deb84`。真实路径/版本/UUID/提交与原锁定要求一致，两 checkout 均 clean；完整脱敏身份见 Mg JSON。

## 未执行与停止范围

- base 上的 5 项 FAIL 是旧缺陷证据；修复后无未解决的 FAIL/BLOCKED。负例自身仍保持非通过状态，测试通过只表示正确拒绝。
- Workbench Julia 单元测试、独立目录重建、实际 identity/tests/minimal/bootstrap 单独动作：本轮 **NOT RUN**；其中动作协议只做 synthetic worker 检查。实际环境检查已随 CLI/Mg 运行。
- DFTK 上游 minimal / 完整测试套件、QE baseline、SOC、MLP：**NOT RUN**。历史 1387/1387 不计为本轮结果。
- 没有改 source lock、Project/Manifest、DFTK/PseudoPotentialIO 源码或 Phase 4A 历史报告/日志；没有提交 UPF、源码副本、缓存、凭证或私人绝对路径。
- 剩余边界：磁盘确实不可写时无法保证错误记录落盘，只能保证非零返回及明确的 stdout/stderr 错误。完成普通提交及当前分支推送后停止，等待人工审查；不创建 PR、不合并、不发布上游留言。

AI 协助：Codex 完成记录器修复、测试和报告；最终由维护者人工审查。
