# iOS 产品页优化实验与 Agent 工作流

**状态**　P0 已有离线实现，真实账户验收待完成，2026-11-23。适用默认 iOS 产品页，涵盖以 IOS 标识的 iPhone、iPad 素材。工程拆分和验证命令见[实施计划](../sprints/ppo-agent-implementation.md)。

## 产品决策

用户应能提出一个问题，例如“英文首图改为搜索结果，是否更容易让商店访客下载？”，得到可审核的单变量实验。实验结束后，Agent 能指出哪个交付包被测过、Apple 观察到什么、是否达到事先约定的收益，以及下次交付具体会改哪些素材。成功指标是历史实验可重放、结论可核对、素材可追溯。下载提升由每次真实实验衡量，工具本身不承诺提升幅度。

| 路线 | 得到什么 | 取舍 |
|---|---|---|
| 复用 Apple PPO 与现有 asc | 原生分流、审核、统计和实验管理 | Apple 的数据粒度、可见期限和可用字段约束自动化 |
| 接入商业竞品情报 | 从已观察到的竞品素材变化发现选题 | 可选输入，注明出处；竞品采用的素材不能证明本 App 的转化表现 |
| fork CLI | 可自行发布缺失的命令 | 还需跟踪 Apple 与上游版本。只有出现可复现、影响交付且上游无法及时修复的缺口时再评估 |
| 在本仓库扩展 CLI 与 Agent 指引（选定） | 把创意假设、实际素材、评估和复产连接起来 | 需维护数据契约与回放测试。首版可离线运行；无需服务、凭据或模型供应商 SDK |

## 实现基线与改动位置

下文保留设计时的接口和取舍。当前命令、绑定方法及快照字段以[运行说明](../../plugins/app-store-creative/skills/app-store-creative/references/ppo-assessment.md)为准。源码基线包含当前工作区的未提交修改；合入前先确认依赖已进入目标分支。历史背景见 [PRD-006](PRD-006-ppo-winner-variant-reproduction.md)。

| 位置（runtime/scripts 下） | 当前行为 | 计划改动 |
|---|---|---|
| app_store_creative.py | 分派 plan、handoff、result、reproduce；result 接收人工观察 | plan 增加可选策略，新增 assess；保留原有 result 调用和显式 variant |
| ppo_experiment.py | 派生主题、卡片字段和文案，编译 handoff，记录一次性结果，按项目范围生成复产计划 | 增加实验范围与卡片顺序；固化实际交付内容；让预览和执行共用同一份限定范围配置 |
| 新 ppo_assessment.py | 待实现 | 纯函数解析快照、验证映射、计算建议。只读文件适配与业务判断分开，判读可重复运行 |
| creative.config.schema.json 与 Agent 操作说明 | 配置已有 hypothesis、treatments | 同步可选策略与排序定义；加入选题、采集、等待和交付范例 |

## 从假设到真实素材

1. Agent 从已上架素材、用户反馈或竞品观察提出候选。每项附来源、目标语言、预期方向、唯一改动、会影响的发布决定。选一个能用现有素材验证的问题。多项同时改变时，仅能声明整个组合的影响。
2. 在配置里为该实验增加可选 policy，包含 locales、targets、testedChange、minRelativeLiftPct、durationEstimateDays（可空，来自 ASC 估算）、estimateSource。阈值是相对原版转化率的百分比，例如 20% 到 21% 是 +5%，由产品目标设定。金额、下载量和绝对百分点不能代入。真实测量前封存策略摘要；历史实验没有事前门槛时保留为探索性观察，禁止事后包装为预注册结论。
3. plan 输出 ready、needs-input 或 defer 及原因。校验一至三个变体、语言和设备属于当前交付、总分流为 1–100 的整数，分别报告 control 和各组分流。目标假设需要原版对照时，100% 分流提示无法形成有曝光的同期原版；不改写旧命令的合法值。估算超过 90 天时建议减少变体或重新选择值得检测的效果；缺少估算时报告未知，允许离线草案。线上已有实验时保存候选供后续选择。
4. 首个试点仅交换两张已批准截图。新增 treatment.cardOrder，要求是基线卡片 ID 的完整排列，保留卡片内容、其余顺序和语言映射。派生配置与验证实际交付顺序共用同一序列。对每个 locale × target 检查素材哈希的有序列表，换序之外有变化则提示调整假设或重做。图标涉及已上架二进制，首个试点限截图。
5. handoff 继续支持无交付的草案。已测素材的绑定要求真实 control、每个 treatment 的 delivery ID、可读清单和有序素材摘要。iOS 的 create 模板明确选择 version-id 或已验证的 v2 App ID + IOS，不使用项目 slug 代替远端 ID。区分“在 ASC 重排已批准素材”和“按设备上传新素材”；首版可以把重排作为 Publisher 的界面步骤，核对实际顺序后写入绑定。交接清单不直接执行远端操作。

## 数据契约与来源

以下名称为拟议 JSON 字段。每个新记录标记 schema_version、generated_by 和 project_id。分别保存作者输入、远端观察、规则输出。时间用带时区的 ISO 8601，数量为非负整数，百分比为有限十进制数，拒绝布尔值、NaN 和无穷。null 表示 Apple 尚未给值，不能补零。阈值比较使用十进制运算，采用源中显示的精度。

| 记录 | 必需内容 | 核对关系 |
|---|---|---|
| 实验交接与绑定 | 本地 experiment_id、policy_sha256、handoff_sha256、ASC app / experiment ID、平台、版本、纳入的 locales / targets；每组含本地 ID、远端 treatment ID 或 original、delivery ID、按语言与设备排序的资产清单与摘要 | 交接时封存策略和素材；取得远端 ID 后追加独立绑定，避免回写改变原 handoff 哈希。名称只用于显示。无法核实 ID 映射时请求核对 |
| 快照 snapshot/v1 | binding_sha256、远端 app / experiment ID、observed_at、running / ended、来源文件引用和原始字节 SHA-256、分析基线、观察范围；每组含 ID、unique_impressions、conversion_rate_pct、relative_lift_pct、confidence_pct、apple_status | 保存原始来源和标准化输入。首版支持人工从 App Analytics 表格转录为 JSON，原截图或导出供复核。来源展示名称时用已核对的绑定映射；无法唯一对应则停止 |
| 判读 assessment/v1 | 快照、绑定、策略及来源摘要、规则版本、各组观测、action、reason_codes、可选 selected_treatment、观察范围、人工可读说明 | 相同输入与规则得到相同结果。可追到源记录；聚合实验的结论只适用于整个被测组合，不能把整体 lift 分配给各语言 |
| 新式 result | 沿用现有 decision、selected_delivery 和证据字段，增加 assessment、绑定、快照摘要与 measured_scope | 仅已核对的终局决策生成。旧版自由文本记录可继续读取，呈现为人工判断。新版复产重新验证整条引用、配置和实际素材 |

快照格式片段（虚构，只展示一个变体行，比例均为百分数）：

```json
{"treatment_id":"remote-search-first","unique_impressions":10000,
 "conversion_rate_pct":21.2,"relative_lift_pct":6.0,
 "confidence_pct":93,"apple_status":"Performing Better"}
```

同一快照须包含 original 行且仅出现一次，原版 lift/confidence 可空。缺字段、未知枚举和零曝光需分别报告。原始数据只保存在项目既有工作区，测试仓库只存脱敏或合成 fixture；原截图可能含账号或其他 App 信息。Apple 报表接口接入前用同一实验和时点逐字段对照 UI；缺少 confidence、baseline 或 treatment 标识时保留手动采集路径。

## 判读与状态转换

先验证来源、所有组、范围、采集时间和基线。术语与 Apple 展示一致，保留原始状态。以下规则针对 original 为比较基线的设计。Agent 可以解释规则输出，决策由确定性代码产生。

| 条件（先判断输入，再判断整场实验） | action | 可执行后续 |
|---|---|---|
| 映射、来源或摘要矛盾，缺组、重复、换了比较基线、显示“更好”但 lift 为负等 | needs-review | 列出待核实字段，修正后重放 |
| 正在采集，样本不足，或还有未决变体 | wait | 显示当前读数；在下一份新快照到达时重判 |
| Apple 显示 Likely to be Inconclusive | 运行中提示低把握；已结束且无足够证据则 inconclusive | 保留历史与原版，可提出更大差异或更少变体的新假设 |
| 已结束，全部变体结果可判，唯一一组 Performing Better、置信度 ≥90%、正向 lift 达到预设业务门槛 | use-treatment | 记录选定整组并预览复产 |
| 已结束，全部变体均明确较差或正向效果低于门槛且有充分证据 | keep-control | 保存原因和数据，保留原版 |
| 已结束，仍有未决组、关键指标缺失或没有事前门槛 | inconclusive | 记录可支持的观察；允许人工另附判断 |
| 多个变体均达标，仅有各自对原版的比较 | needs-review | 并列列出；不根据相对原版的点估计宣布组间胜者 |

运行中已达到采用条件时展示候选与读数，action 仍为 wait（首版产品选择）；同一快照同时满足“缺乏证据”和“没有组达到门槛”时优先 inconclusive。决策不修改线上状态。Apple 原生应用 treatment 属于单独发布动作，图标更新随版本提交。

## CLI、持久化与故障恢复

示例使用项目 CLI 的 ppo 子命令；以下接口在实施后提供。

```text
ppo plan --experiment search-first
ppo handoff --experiment search-first --baseline-delivery D0 --treatment-delivery B:D1 --output handoff.json
ppo assess --handoff handoff.json --binding binding.json --snapshot snapshot.json --json
ppo assess --handoff handoff.json --binding binding.json --snapshot snapshot.json --output assessment.json
ppo result --handoff handoff.json --assessment assessment.json --output result.json
ppo reproduce --experiment search-first --result result.json --json
```

- handoff 为策略和清单提供摘要；Publisher 在核实远端部署后按公开的 binding/v1 模板记录绑定。首版提供可编辑 JSON 模板、字段级验证和错误定位。plan 仅预检；默认 assess 和 reproduce 均无写入。
- 新 result 模式与旧的人工输入参数互斥。wait 或 needs-review 可保存评估，不能产出终局 result。退出码沿用 CLI 约定：合法业务结果返回成功，由 action 分派；无效输入、I/O 或证据损坏返回失败，仅输出明确诊断。
- 证据路径相对项目根解析，内容摘要随记录保存；恢复时依摘要定位。对历史输入重放允许旧时间，推进当前决策时禁止较旧快照覆盖较新快照。同输入写同目标应返回已有一致记录，不同输入冲突时报错。复用同目录临时文件及不可覆盖的原子发布方式；并发写入测试覆盖崩溃、重试和冲突。
- 新式 result 的预览与 execute 共用 measured_scope；只导出实测语言和设备，并比较获选原始交付的有序资产摘要。配置继承、卡片内容或源素材变化时中止等价复产，显示具体差异。需要扩展到其他市场时另建生产任务并标注未经该市场验证。执行阶段发现产物不一致时保留失败回执，禁止提升为发布交付。
- 每次运行输出 action、reason_codes、来源引用、规则版本、计划交付范围。首版无后台轮询。回滚方式为停用新增 assess 路径，保留所有原始快照、旧 CLI 和生产素材；禁止通过回滚删除证据。

## 外部依据

Apple 负责分流与 App Analytics 统计。实验最长 90 天，可设置至多三个 treatment；五次归因首次下载是可见性条件，不能作为选胜门槛。应用 treatment 的操作不可撤销。参考 [Apple PPO 配置与时长估计](https://developer.apple.com/app-store/product-page-optimization/)、[App Analytics 指标与状态](https://developer.apple.com/help/app-store-connect-analytics/acquisition/product-page-optimization)、[应用 treatment](https://developer.apple.com/help/app-store-connect/create-product-page-optimization-tests/apply-a-test-treatment-to-your-product-page/)。
