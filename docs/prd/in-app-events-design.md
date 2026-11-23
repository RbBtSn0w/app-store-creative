# iOS In-App Events 技术设计

本地 CLI 已实现，真实活动待试点 · 2026-11-23 · [实施计划与测试矩阵](../sprints/in-app-events-implementation.md)

## 产品目标与交付范围

用户可以问「下个版本有什么值得召回老用户的活动？」Agent 阅读已提供的版本说明、Issue、内容排期和 build 证据，输出 propose、defer 或 skip。propose 必须说明目标用户、限时体验、可执行动作、活动结束后要做的决定，并逐条关联可核实的出处。仅有性能优化且没有合适活动时，skip 就是一次成功交付。已有真实活动但缺少可用版本时，defer 要指出恢复条件。文案生成允许有创意，日期、权益、费用、奖励和可用地区必须来自产品事实。

产品切片为一场 iOS 活动、至少一种语言、两种静态图位、可验证的 App 内落点、ASC 交接和一次效果判读。试点用两个语言验证本地化。素材可由已有设计和捕获流程产出，事件模块消费导出文件。独立 Studio 日历、视频制作和自动拉取商业竞品数据按试点需求立项。采用上游 asc 执行远端操作，保留 ASC 界面处理特殊配置。竞品日历可帮助选题，其曝光和转化仍需以本 App 的数据验证。

## 使用路径

以下 creative 代表项目的 app-store-creative 启动器。五个 events 子命令已提供。字段与输入示例见[运行指引](../../plugins/app-store-creative/skills/app-store-creative/references/in-app-events.md)。示例使用项目相对路径。

```sh
creative events plan --repo . --brief events/winter.json
creative events validate --repo . --event winter --inventory snapshots/asc.json --routes evidence/routes.json
creative events handoff --repo . --event winter --validation .creative/events/winter/validation.json
creative events observe --repo . --event winter --snapshot snapshots/published.json
creative events assess --repo . --event winter --store reports/asc.json --product reports/app.json
```

plan 接受 agent 整理的结构化 brief，输出候选决定及证据缺口。validate 可离线运行，缺少远端或设备证据就逐项返回 unknown。handoff 只在本地验证通过时输出可执行步骤；需界面核对的字段逐项标为 manual。observe 导入 Publisher 读取的远端事实，支持重放。assess 允许任一来源缺失，输出证据足够支撑的最窄结论。所有命令输出 JSON，包含 schemaVersion、eventKey、status、findings（code、field、actual、expected、remedy）、artifacts。正常产品决定 skip/defer 返回 0；输入无效或请求交接但被阻塞返回非零，错误细节保留在 JSON。旧配置无需 events 字段。

## 工程接入与存储

在 runtime/scripts/app_store_creative.py 注册 events 子命令，父子共享的 --repo 用 argparse.SUPPRESS，路径经 project_path() 解析。新增 event_plan.py 负责 brief、规则与排期，event_handoff.py 负责封存和观察，event_assessment.py 负责报表判读。以 runtime/schemas 中的版本化契约描述输入；Python 标准库实施同样的运行时校验。复用 record_primitives.canonical、digest、safe_id 及现有项目身份，核查 publication_lifecycle.py 和 Publisher 现有授权范围后复用其机制；活动资源单独建模，不复用 screenshot set 或 PPO treatment 的资源 ID。更新现有创意、验证、发布指引与打包清单；安装包从任意工作目录均能加载模块和契约。

项目保存人工输入和原始证据，派生记录归于 .creative/events/<eventKey>/。主键为 projectId + appId + eventKey。目录名经 safe_id，输入素材与证据在解析符号链接后仍须位于项目允许的输入根。记录保存相对路径、字节 SHA-256 和角色。新记录先写同目录临时文件再原子替换；不可变内容以摘要寻址，validation.json 等便捷入口只指向已完整写入的记录。对同一事件写指针时持项目内事件锁，并核对预期父摘要；竞争者收到 conflict 后重读。远端修改仍需另做回读和冲突处理。

| 记录 | 必填数据与关系 |
|---|---|
| brief/v1 | projectId、appId、platform=IOS、eventKey、referenceName、primaryLocale、badge、purpose、priority、purchaseRequirement、deepLink、buildRef、territories、schedule、localizations、claims、measurement。每个 claim 指向证据位置及摘要；每种语言列出 name、shortDescription、longDescription、card、details。地区与语言分别建模。 |
| schedule | 默认 publishAt/startAt/endAt；可选按 territory 覆盖整组时间。RFC3339 必须带偏移，计算用 UTC，预览保留本地时区。仅给本地时间且遇夏令时歧义时要求消歧。 |
| inventory/v1 与 routes/v1 | 前者含 appId、抓取时间、分页完整性、事件 ID、原始状态、各地区窗口、App 可售地区和版本；后者含 build 标识、bundle ID、地区、URL、启动条件、预期与实际界面标识、时间、结果和截图/XCResult 摘要。 |
| validation/v1 与 handoff/v1 | 绑定 brief、证据、规则版本、inventory、routes 的摘要；再列本地资源到 ASC 类型的映射、每个 locale × slot 的实际字节摘要、目标 App、提交方式、命令 argv 或人工步骤及预期回读值。 |
| binding/v1 与 observation/v1 | handoff 摘要、ASC app/event/localization/asset/submission ID 分字段记录。观察按时间追加，保存原始返回、脱敏证据摘要、远端状态及请求范围。未知状态保留原始值。 |
| measurement 与 assessment/v1 | 事先定义主目标、指标、单位、分子分母、有效样本下限、业务门槛、观察窗口和拟采取的动作。结果引用 binding、策略、两个来源的快照摘要、可用范围和原因码。 |

例如一次召回试点的 measurement 可以定义为下列合成片段。数值由产品方在活动开始前确定。

```json
{"goal":"reactivation","decision":"commission_next_episode","primaryMetric":"completionAmongStarters","numerator":"uniqueCompleters","denominator":"uniqueStarters","minDenominator":40,"threshold":0.5,"window":"event_start_to_end","cohort":"all_event_entrants"}
```

这个指标回答「参加者是否愿意完成」，无法单独证明老用户被召回。要回答召回问题，还需产品侧能识别的沉默期定义与回流人群计数；无此数据时，把结论限定到参与质量。

## 校验规则

1. **身份与文案。** 内部 referenceName 在 App 内唯一且最多 64 字符；各语言标题、短描述、长描述上限依次为 30、50、120。主语言必须存在，每个声明本地化的语言均要有完整图文或明确可核实的素材引用。保存输入原文，以 NFC 做本地长度预检；组合字符临界值以 ASC 返回为准，禁止自动截断。badge 从七种 Apple 类型选择；平台入库时规范为 IOS，其他平台返回 unsupported。布尔值不能代替整数。
2. **时间与名额。** 对每个地区检查 publish ≤ start < end，预热最多 14 天，时长 15 分钟至 31 天，各地区开始时刻差最多 48 小时。新建操作检查未来时间，历史观察允许过去日期。地区必须与 App 可售地区匹配。分页读取同一 App 现状，按事件 ID 去重，更新已有事件时先移除旧版本再加入候选。分别检查草稿最多 50、批准库存最多 15、展示并发最多 10、草稿与获批活动的活动时间重叠最多 10。批准库存比较区分创建草稿与申请批准的动作。展示包括预热 [publish,end)，活动并发用 [start,end)，同一时刻先移除结束项。地区窗口先按事件取区间并集，再按 App 扫描唯一 ID，同时输出受影响地区；跨区计数存在歧义时标注本地保守预测和需 ASC 确认的范围。预测碰撞与已观察到的远端占用分开列出。快照缺页、字段缺失或陈旧时显示 unknown；执行前重新读取，远端冲突后重新规划。
3. **素材。** MVP 接受 JPEG/PNG。实际解码验证类型、宽高、完整性、尺寸上限 500 MB，横卡 16∶9、1920×1080 至 3840×2160，详情 9∶16、1080×1920 至 2160×3840。交叉乘法验证比例。默认输出不透明图片。分别构图并查看缩略预览、遮挡、文字和本地化，记录审阅图版本。视频输入返回需视频工作流处理；后续启用前单独覆盖帧率、音轨及两种图位各自的 Apple 规范。
4. **深链与版本。** 模拟器或目标设备用系统入口打开 URL，等待预期 accessibilityIdentifier，并核对 eventKey 和可参与动作。覆盖冷启动、热启动、首次启动经过 onboarding 后恢复路由、地区和内容版本。预热期应进入可解释的预告页面，结束后进入已结束页面。登录或订阅条件存在时，验证完成后回到同一活动。设备结果与目标 build/内容配置绑定；仅 URL 可解析或 App 被唤醒不足以通过。试点补测真机 universal link，保存经脱敏的结果。
5. **可执行性。** 本机 asc 7.1.0 的 create/update 均只暴露一组时间，purchase-requirement 只支持 NO_COST_ASSOCIATED。付费或区域分时配置标记 manual-required，Publisher 在 ASC 界面填写并保留逐字段读回证据；无法核实则阻止提审。缺少已获批 iOS 版本时绑定首版 submission；已获批但内容依赖新版本时协调版本送审、地区可用时间和活动开始时间。

## 发布、恢复与状态

handoff 本身无远端副作用。现有 Publisher 按用户授权范围执行，草稿写入、素材上传和提交覆盖哪些资源必须明确。执行器锁定 handoff 摘要，重新验证素材、远端 appId、活动资源归属和实际 CLI 能力。先读取 app-events list/view、localizations、screenshots 和 review items，再按差异执行，始终解析 JSON。远端修改时记录 intent → receipt → readback 三种事实；日志仅保留资源标识及经脱敏错误。

| 观察或故障 | 下一步 |
|---|---|
| 创建超时，未知是否成功 | 按 appId + 唯一 referenceName 回查候选，验证时间、语言、类型等身份字段；确认唯一后绑定 eventId。尚不可见时有限重读，仍不明则保留 pending-reconciliation。 |
| 上传中断或两台机器并发 | 按 eventId、localizationId、slot 查资产和处理状态；已交付且内容一致则跳过，处理中等待，内容冲突或无法确认摘要则要求核实。覆盖前重读远端；本地锁只解决同一工作区竞争。 |
| 提审中断 | 查现有 submission 及全部 item。已有相同活动且等待审核则记录观察；可用草稿先核实 App、平台与该提交中所有项目，再继续剩余步骤。首次版本复用对应草稿。 |
| 审核拒绝、审核中、已批准待发布、已发布、已结束 | 拒绝时保存理由并生成修订计划；审核中只跟踪。待发布和已发布分别来自远端观察。按 Apple 当前状态限制可修改字段，开始后仅调整结束时间；修改计划生成新摘要。 |
| 403、429、服务异常或新状态 | 403 保留权限诊断；幂等读取对 429/暂时性错误有限退避并尊重 Retry-After。写入结果不明先回查。未知状态输出 needs-review。 |

## 效果判读

asc 观察与产品聚合各自保留 eventId/eventKey、地区、时间、来源、粒度及覆盖范围。首版导入结构化 JSON 和可核对的原始来源；逐事件 Apple 批量导出应使用详细报告。Apple 侧至少 5 个首次下载才显示活动数据，延迟、隐私抑制、未采集和报告中的实际零分别编码。保留展示、详情浏览、提醒、打开、首次和重复下载的原单位；不得把打开次数当作独立参与者。产品侧记录 event_opened、event_started、event_completed，汇出按活动和目标人群去重的聚合值，原始用户标识留在 App 的分析系统。按共同窗口并列展示，不做跨来源逐人拼接。

以示例策略为例，40 位独立开始者、20 位完成者达到参与质量门槛；39 位开始者即使全部完成也只能标记 insufficient-data。主指标充分且达标时建议续作，低于门槛则列出最早有证据的流失步骤；分子大于分母、跨人群或口径漂移则标为 needs-review。若缺少召回人群口径，结果单独标明召回目标未验证。仅用活动前后变化不能归因增量。终止或复办由产品负责人决定，保存理由及关联快照，后续活动引用该结论。

## 依据

- [Apple 活动配置、地区和排期](https://developer.apple.com/help/app-store-connect/offer-in-app-events/offer-in-app-events/)
- [Apple 图片和音视频规格](https://developer.apple.com/help/app-store-connect/reference/in-app-events/in-app-event-media-and-audio-specifications/)
- [Apple 审核流程](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-in-app-event/) · [活动状态](https://developer.apple.com/help/app-store-connect/reference/in-app-events/in-app-event-statuses/) · [可编辑范围](https://developer.apple.com/help/app-store-connect/offer-in-app-events/manage-events/)
- [Apple 活动分析与导出](https://developer.apple.com/help/app-store-connect-analytics/acquisition/in-app-events)
- [上游 asc](https://github.com/rudrankriyam/App-Store-Connect-CLI)；CLI 能力基线为本机 7.1.0 的命令帮助，远端响应契约留待授权试点验证。
