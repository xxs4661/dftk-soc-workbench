K6 的预算状态为 `INSUFFICIENT_EVIDENCE`，新峰值为 `null`，K6 context/SCF 均为 `NOT_RUN`。旧估算 12,614,633,984 B、8 GiB 上限与 2 GiB 预留保持不变。整数项及保留余量的小计为 6,788,850,928 B（6.322610 GiB），它不是峰值上界。

| 静态案例 | REF 采样 RSS / B | CORE 采样 RSS / B | REF 关闭阶段唯一 payload / B | CORE 关闭阶段唯一 payload / B |
|---|---:|---:|---:|---:|
| B0 | 3,212,132,352 | 2,117,042,176 | 498,751,472 | 148,972,672 |
| K4 | 4,603,723,776 | 3,590,062,080 | 3,002,204,752 | 497,577,824 |

静态观测验证了每个 k 点仅持有一套 P/D，以及 14 个有界 workspace 的实际 backing 大小；B0/K4 打开时 P/D 各为 8/64 个 owner，关闭后为 0。旧静态测量末尾保留了 7 个 context，不能把独占 runtime 作用域关闭带来的收益当成一次真实 SCF 的峰值降幅；没有清空旧全局注册表来制造下降。CORE 的 context-ready payload 反而因预分配 workspace 高于 REF；分配量、存活 payload 和采样 RSS 分别报告。

唯一 OPT-B0-SCF 尝试在驱动初始化前解析失败：native exit=1、recorder exit=9。741,703,680 B / 3.720085417 s 只描述失败启动，不能用来校准 SCF 内存。Γ 因父任务失败而 BLOCKED_PARENT / NOT_RUN。

未界定的生命周期仍包括：最多 400 次 map 的诊断/history 容器；旧/新 X 与 all_X、energy χ 和多个 H/势的重叠；活跃 LOBPCG、QR 及临时矩阵；回调指纹与保存时 Serialization/IOBuffer 的 GC 前容量；K6 字典 spare capacity；native/JIT/allocator 与采样间隔内峰值。2 GiB 预留不能替代这些对象的上界证明。没有新 K6 数值调用，也不把静态性能门槛通过改写成 SCF 已验证。

整数账目由已提交 `benchmarks/soc-core-memory-v1/budget.py` 复算，arithmetic_status=PASS，预算结论仍为 INSUFFICIENT_EVIDENCE。完整字段、源文件 hash 与现有公共证据选择器见 `memory-budget.json`。

旧 → 新资源账目对应（只重分类，不改变旧估算）：

| 旧 K6 项 / bytes | 新账目对应 | 证据与限制 |
|---|---|---|
| retained_orbitals_and_solver / 5,443,176,960 | 当前/前次 X24、all_X30、energy χ，以及串行单 k 求解余量 | 保守共存角色仍保留；未证明所有旧估算副本必然实际存在，不能称为已节省这些字节 |
| projectors_and_snapshots / 4,256,022,528 | 一套 P、逐 k D、G/map/kinetic 与证书快照 | 单 context 的一套 P 在旧实现已存在；去掉旧 ×4 保守余量并非实测 4→1。真实静态收益是循环关闭后不再全局持有历史 context |
| bounded_fft_workspaces / 679,477,248 | 此旧余量完整保留，另列实际有界 FR/component/full-H/density workspace | 对照确认新 workspace 大小与共享，但没有无依据删除所有旧 FFT 余量；小计有意保守重叠 |
| density_core_local_fields / 88,473,600 | 此旧 100-field 余量完整保留，另列可能共存的三代 common-H 局域势 | 不能从静态关闭测量推断求解/能量/回调峰值完全不重叠 |
| runtime_library_margin / 2,147,483,648 | 同额 Julia/JIT/native/allocator margin | 未降低；仍不构成严格峰值保证 |

可取最大值的范围限于单线程、非重入的串行 k/RHS workspace；各 k 的 P/G、实际物理轨道与当时仍存活的原/新 raw、历史记录不能按最大单 k 替代其总和。JSON逐项列出公式与确定性，`unpriced_or_unbounded` 单列未界定项，不将它们默认为零。
