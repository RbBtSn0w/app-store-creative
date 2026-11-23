# Featuring Nominations 实施方案

状态：CLI 与 Publisher 已实现；真实账户草稿和正式提交待试点。面向实现 CLI、Publisher 和验收工具的维护者。用户流程、Apple 字段、作用域和 N01–N20 的预期结果见[技术设计](../prd/featuring-nominations-design.md)。本方案给出落盘、分派和恢复的具体做法，以及每个增量可以合入的条件。

## 1. 接入现有运行时

下表中的 Python 文件均位于插件主 skill 的 runtime/scripts 下。新增接口使用 Python 3.11 标准库。CLI、后续 Studio 和 Agent 均调用同一组领域操作。

| 文件 | 改动与边界 |
| --- | --- |
| app_store_creative.py | 在 build_parser() 内通过现有 cmd 工厂注册 nomination；在 run(args) 中把 root 和 project_path 传给 nomination_commands.execute。子命令共享参数用 argparse.SUPPRESS，保留已有 PPO、CPP 与发布入口 |
| nomination_commands.py（新增） | 实现 add_arguments(parser) 与 execute(args, root, project_path)。解析路径、参数及机器可读输出；用 Lifecycle.from_configuration(root, config_path) 加载有效配置。只读操作不触发工作区初始化 |
| nomination_lifecycle.py（新增） | 对现有 Lifecycle 实例提供 draft、review、plan、authorize、claim、observe、status、reconcile。所有读改写在同一 core.transaction() 中完成；远端调用在锁外执行 |
| nomination_asc.py（新增） | 实现 build_argv(plan)、parse_view(response, scope)、compare(expected, actual)。纯函数返回 argv、类型化观测或逐字段差异。字段名和 CLI 参数使用显式映射，未知状态保留原值 |
| operation_history.py 及存储相关登记点 | 在 CATEGORIES 登记 nomination-events；验证 history 扫描、commit 修复、迁移清单、回滚和打包能识别新记录与证据。避免让提名记录的标识触发生产 attempt 的所有者查询 |
| 主 skill、publisher skill、.github/package_plugin.py | 主 skill 负责组稿和草稿审阅；Publisher 新增提名交付入口。运行时打包后从解压目录执行命令，证明新模块、参考文档和 fixture 测试入口均可用；fixture 本身只用于测试 |

## 2. 数据契约与原子写入

首版使用单提名的追加式事件记录。项目间通过有效 workspace 隔离，项目内使用 localId 标识提名。主线不维护可变 current.json；status 和 review 从已提交记录重建。以每条提名的事件数量为扫描范围，不遍历所有产品媒体。

| 数据 | 具体约定 |
| --- | --- |
| 记录地址 | core._record('nomination-events', data, suffix)；data.id 为 localId，suffix 为八位十进制顺序号，从 00000001 起。目录按后缀排序，每条经 core._read 验证。顺序断裂、前驱摘要不匹配时返回 integrity_error，禁止分派 |
| 事件信封 | 沿用 schema_version、created_at、_commit_event_id；增加 seq、kind、parent_event_digest、project_id、actor、body。actor 非空；业务动作 ID 使用 body.attemptId，与生产 attempt 域隔离。外部 JSON 的 schemaVersion 在 CLI 边界显式转换 |
| 事件种类 | revision_saved、plan_created、authorized、attempt_claimed、write_acknowledged、write_rejected、outcome_unknown、observed、remote_bound。每次状态转换只追加一个事件；首次收到完整 view 时由同一个 observed 事件同时推进验证状态并结束原尝试 |
| 摘要 | 对规范化业务值使用 SHA-256(canonical(value))；revisionDigest 包含目标、有效文案、上下文与证据引用；planDigest 再绑定动作、精确发送字段及远端基线。排除处理时间、随机执行 ID。parent_event_digest 单独覆盖上一个完整落盘记录 |
| 证据原件 | 位于有效 publicationRoot 下的 nominations/<localId>/evidence/<sha256>。通过仓库现有安全暂存与同卷发布方式写入原始字节，读回核验后才追加引用事件。跨根崩溃最多留下未引用原件；恢复时按摘要复用。清理流程须保留未知／引用中证据 |
| 去重 | 相同 base 上同一 revisionDigest 返回已有修订；同一 plan、动作和授权的再次 claim 返回旧尝试状态且不再返回可执行 argv；同一读回证据按 attempt、阶段、scope 和原始字节摘要去重 |
| 历史修复 | commit-intent 已写、目标事件未落盘时，先进入现有 commit 恢复流程。发生显式 abandonment 时保留废弃槽位凭证，并用新的顺序号继续；投影器仅在验证相应 abandonment 后允许跨过该槽位。单独测试首次事件中断及最后事件中断 |

本地写入伪代码如下。序号分配、期望基线检查和 append 必须使用同一个锁；operation history 的提交意图只作为恢复线索。

```python
with core.transaction():
    current = load_verified_history(core, local_id)
    decision = decide(current, command)
    if decision.replayed:
        return decision.previous_receipt
    event = append_transition(core, current, decision)
return make_receipt(event)
```

## 3. 将授权转成精确的一次写入

1. **计划**。有绑定时先获取与目标对应的 view；将受管字段以及 App、地区和事件关系的完整快照归一化并计算 baselineDigest。计划区分 create_draft、update_draft、submit。对已验证且完全一致的草稿返回 no_change。首次创建时 baseline 为空。
2. **授权**。CLI authorize 同时接收 --actor 和 --human-reference，复用 require_human_authorization。保存 action、planDigest、reviewedRevisionDigest、目标及人类授权出处；CLI 保留调用者声明的出处，不能把自由文本引用视为经过认证的签名。Agent 从用户对当前版本的授权取得这些值。
3. **认领**。Publisher 先做只读预检（账号、CLI 能力、App 权限和即时基线），然后 claim 将核对结果绑定到 attempt。仅首次成功认领返回 one-shot argv。草稿与提交各有独立认领；同一 localId 上有未决写入时，继续允许只读恢复。
4. **执行**。Publisher 在对应的 ASC 配置下用 argv 调用 asc，保留结构化结果；不得自动重发写请求。重放 claim 的响应不含 argv。执行方也需要按 attemptId 持久化已消费标记，在调用前写入，避免把已导出的同一指令再次派发；标记写入后崩溃按未知结果处理。这一保证的范围是受管执行端和单一工作区。
5. **登记与核对**。首次 create 响应含 ID 时立即登记 write_acknowledged；它只提供 readback 的目标。后续执行 view，按 ID、账户、App 集合、全部受管字段和目标状态比对；一致才返回 verified。执行结果丢失时继续使用原 attempt。跨客户端并发依然可能发生，写前基线及写后回读只能发现可观测到的差异。

| 输入与当前状态 | 应返回的结果 | 接下来允许的动作 |
| --- | --- | --- |
| 新建本地稿，目标字段未齐 | needs_input，附字段路径 | 补充草稿和再次 review |
| 已分派，无回执或连接中断 | outcome_unknown，附 attemptId | 只读 reconcile；未知创建禁止盲目再次 create |
| 更新返回 ID，但 view 缺 relatedApps | unverified，附缺失关系 | 获取含完整关系的 view；读取失败可继续原尝试 |
| 原 attempt 未完成，view 显示已提交且字段吻合 | verified，附 remoteId、scope 和 evidenceDigest | 重跑 status 仍是同一回执 |
| 检测到网页端改动或账户切换 | conflict，附差异字段 | 重新读取目标并审阅新的计划 |
| 收到较早观测或无法确定新旧 | 保存证据，不覆盖较新已验证结果；矛盾时标 conflict | 获取新的完整 view。按服务端修改时间及读取阶段比较，禁止仅凭本地到达顺序裁决 |

## 4. 可独立验收的开发批次

| 批次 / 依赖 | 交付与工作顺序 | 合入证据 |
| --- | --- | --- |
| A 本地草稿 | 注册命令；实现事件存储、摘要及修订并发检查；实现 draft/review；补写真实材料与推断的编辑指引 | N01–N09；从不同 cwd 和解压目录起草；两个进程编辑旧 base 仅一个成功；验证重定位后仍能回读 |
| B 草稿交付，依赖 A | 实现 plan/authorize/claim 和 ASC 参数映射；再接 Publisher 的草稿创建、修改；保存中间回执及首次完整回读 | N10、N11、N13、N18；假 ASC 捕获 argv，断言 create 一次、同 ID 更新一次、相同内容零写；草稿与截图上传两种授权互不通用 |
| C 恢复与提交，依赖 B | 实现 reconcile、状态投影和提交前基线；接入中断恢复与重复观测；最后开放 submit | N12、N14–N17、N19；在 claim 后、创建成功后、回读落盘前分别终止进程。检查重启后结果、调用次数及证据完整性 |
| D 安装包与试点，依赖 C | 集成主 skill 和 Publisher 调用示例，运行包内 smoke 及媒体发布回归；按真实版本做草稿试点 | N20，四个 CI 分片报告、打包日志、同 ID 的两次真实草稿观测；实际决定提交时补充独立提交回执 |

其中 A 可单独交付为离线起草能力。B 合入前必须具备“发生未知写入时保留 attempt、阻止重复写”的最小保护；C 补齐交互式恢复和提交。真实试点不足时分别报告模拟结果、草稿试点与正式提交三项状态。

## 5. 测试实现及交付检查

- **领域单测**。test_nomination_lifecycle.py 用 TemporaryDirectory 建实际消费项目、配置及工作根。覆写时钟；测试可复核引用、canonical 摘要、事件重放、提交意图中断和能力边界。至少一项并发测试通过真实子进程争抢相同工作区。
- **ASC 契约单测**。test_nomination_asc.py 用去标识化 JSON:API fixture 验证 fields、relationships、分页缺失、缺 data.id、未知 state 和 omitted/clear 的差别。适配器不接受账号或目标未知的输入作为成功证据。
- **安装态集成**。test_nomination_cli.py 使用解压后的 launcher 和临时 PATH 中的假 asc；假执行器独立持久化远端状态与写调用次数，可在写成功后故意丢弃 stdout。断言第二次启动后的 view 能恢复首次结果。真实素材语义用人工评审 fixture 验收，记录句子与证据位置。
- **CI 与故障定位**。每批先跑相应 unittest；交付前使用仓库现行四片 unittest、validate_plugin.py 及 package_plugin.py。保留脱敏错误、状态、attemptId、写入次数与证据摘要；禁止 CI 依赖开发者的 ASC 账号。正式试点的凭据留在 ASC 环境中。
- **回退**。执行适配出现回归时暂停 Publisher 的新认领，继续允许 status 和 reconcile。升级或回退均保留原始证据和在途记录；旧运行时无法读取新增 schema 时，使用兼容版本先核对未决写入再恢复执行。

首项垂直切片从实际 launcher 执行 draft，重启后用 review 找回相同的 localId、revisionDigest、正文和来源。该路径同时用于安装包 smoke。

## 已实现接口

内置 Publisher 入口为 `nomination execute --plan PLAN`。外部执行器可使用 claim 和 observe；需要认领的进程使用同一工作区。事件使用 revision、plan、authorization、claim、ack、rejected、conflict 和 verified；从未关闭的 claim 投影 outcome_unknown。字段适配在 nomination_asc.py 的 command 和 snapshot 中，测试集中在 tests/test_nominations.py。安装包内包含 JSON Schema、示例 brief 与从 draft 重启到 review 的 smoke 检查。
