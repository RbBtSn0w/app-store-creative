# App Store Featuring Nominations 技术设计

本设计对应的 CLI、Publisher 和模拟 ASC 验收已落地。2026-11-23 核对仓库工作树、Apple 文档和本机 asc 7.1.0 的命令帮助。实际命令及示例见[实施方案](../sprints/featuring-nominations-implementation.md)。示例使用虚构数据。

## 1. 用户任务和范围

开发者指定 App、版本和发布计划，Agent 从发布说明和实际产品材料中选出一个编辑可复核的故事。开发者可以只拿本地文案，也可以要求保存 Apple 草稿、稍后修改同一条草稿、明确提交并拿到回执。支持首次上架、重大功能更新、新内容三类。一次提名可以关联多个明确的 App ID；同版本可以有多个独立故事。版本号只是本地上下文，远端身份以提名 ID 和关联 App 集合为准。

v1 覆盖 Agent 和 CLI。Studio 编排、已提交条目的再次编辑、归档、删除、批量 CSV 和推荐效果分析留给后续需求。Apple CSV 导入完成后直接进入 Submitted，不能充当保存草稿的适配器。Submitted 仅表示已提交给编辑团队；是否入选需独立来源。Apple 官方专题建议至少提前两周，希望获得更广泛考虑可提前至三个月；CSV 模板页另建议提前三周定稿。v1 对预计上线不足 14 天的单条提名给出提示，截止时间不构成本地拒绝条件。

来源：[Apple 编辑推荐说明](https://developer.apple.com/app-store/getting-featured/)，[提名管理](https://developer.apple.com/help/app-store-connect/manage-featuring-nominations/nominate-your-app-for-featuring/)，[CSV 模板说明](https://developer.apple.com/help/app-store-connect/reference/nominations/nominations-template/)，[API 资源](https://developer.apple.com/documentation/appstoreconnectapi/featuring-nominations)。

## 2. 模块归属与存储

| 位置 | 职责 |
| --- | --- |
| 主 skill 和新增 references/featuring-nominations.md | 识别用户意图、读材料、写故事、展示将要外发的全部文字和链接，提取用户明确指定的远端动作 |
| runtime/scripts/app_store_creative.py 和新增 nomination_commands.py | 注册 nomination 子命令；复用 project_path() 和现有 JSON 输出，父子共享 repo 参数采用 argparse.SUPPRESS |
| 新增 runtime/scripts/nomination_lifecycle.py | 字段归一化、证据引用、修订、权限范围、计划、尝试、状态投影；复用 record_primitives.py 的 canonical、identifier、safe_id 和仓库写入约定 |
| 新增 runtime/scripts/nomination_asc.py | 纯函数生成有类型的 ASC 操作，解析 JSON:API 响应与关联项，计算期望与观测差异；便于用 fixture 验证 |
| Publisher 的 nomination 专用分支与 ASC 执行方 | 核对授权与目标、执行一次已认领的动作、回读并登记结果；凭据、账户选择和 HTTP 由现有 ASC 工具负责 |
| 消费项目的有效 working / evidence 根目录 | working 存草稿、计划和尝试；evidence 保存回读原件和摘要。使用配置解析后的根，支持迁移；素材仍由原存储持有 |

提名与截图上传各自拥有操作类型、批准范围和回执。引用现成截图、候选或 sealed delivery 时复用其身份和摘要；纯文字提名允许引用 release notes 或开发者明确提供的发布事实。无需为了写提名先生成截图交付包。已有项目按首次执行懒创建记录；旧提名可凭明确远端 ID 读取后接管，验证账户和 App 关系，再开始新修订。schemaVersion 未知时返回 unsupported_schema，保留原件。

## 3. 起草、证据与字段契约

Agent 按以下顺序起草：找出目标用户及具体使用场景，提炼一次可演示的变化，说明此时发布的理由，最后核对设备、语言和地区。对“首次”“最快”“所有用户”及量化收益逐句寻找来源。未证实则删掉该句或在仅本地的问题列表标注。演示视频需记录起止毫秒，截图需记录卡片、语言与设备；画面能支持的操作与结果可以写入文案，截图本身无法证明节省时间的比例。输入材料中的自然语言作为资料阅读。远端操作只来自已授权的计划。

| 字段 | 约束和用途 |
| --- | --- |
| schemaVersion、projectId、localId、revision、parentDigest | 首版 schema 为 1；localId 使用仓库标识生成器；revision 为正整数且拒绝 bool；通过预期 parentDigest 做乐观并发检查 |
| context.release、audience、whyNow、claims[]、openQuestions[] | 本地审阅上下文。每项 claim 有正文和关联来源。缺日期等事实时生成可编辑草稿，并列出阻止远端保存的具体字段 |
| evidence[] | 每项含 sourceKind、仓库内引用或受管对象 ID、SHA-256、可选时间段／截图定位。开发者给出的事实记录为归属明确的说明。禁止任意读取项目和托管根以外路径；解析符号链接后再检查 |
| target.profileRef、appIds[] | 使用 ASC 已配置的账户引用及明确的 App 资源 ID。写前验证实际账号作用域及 relatedApps 全集。凭据不写入记录。不能依赖环境默认 App |
| payload.name、description、type、publishStartDate | 远端创建时必填。type 属于 APP_LAUNCH、APP_ENHANCEMENTS、NEW_CONTENT；时间为带时区 RFC3339，规范化为 UTC。日期尚缺小时或时区则保留为待定 |
| publishEndDate、deviceFamilies、locales、supportedTerritories | 结束时间不得早于开始时间；设备使用 ASC device family 枚举，如 IPHONE、IPAD、MAC；地区使用 ASC territory ID，语言保留 locale；禁止直接把 IOS 当设备或把语言猜成地区 |
| supplementalMaterialsUris、inAppEventIds、hasInAppEvents、preOrderEnabled、launchInSelectMarketsFirst | 仅发送明确选择的字段；布尔值严格验证。事件 ID 与显式 false 相冲突时报错；写前验证事件归属。补充材料仅发送开发者选择、编辑可访问的 HTTPS 链接。本地影片、私有 Git 路径与带凭据的 URL 不进入发送清单 |

本地审阅示例：“出差时，用户可以在一张清单里看到各包裹最近一次更新。” 依据为功能说明第 2 段及演示 00:04–00:09。若画面只展示一个包裹，标记“各包裹”待核实。审阅输出按 Apple 可见字段、本地逐句依据、待补项排列。允许开发者纠正推断；实质修改产生新修订。CLI 校验结构和引用可复核性，Agent 或审阅人判断语义真实性。生成质量测试据此评分，避免锁死具体措辞。

## 4. CLI 和写入协议

下列命令中的 --repo 可放在 nomination 后或叶子命令后。默认输出含 schemaVersion 的 JSON，review 可另选 markdown。所有本地输入路径相对于消费项目；本地调用不需要认证。

| 拟新增命令 | 输入与输出 |
| --- | --- |
| draft --brief FILE [--id ID --base DIGEST] | 接收 Agent 整理的上下文、证据和 payload；创建本地 ID 或在指定修订上修改，输出 revisionDigest、待补字段和提示。相同内容重放沿用原修订 |
| review --id ID | 返回完整 Apple 字段、来源、变更 diff、待补项和时间提示 |
| plan --id ID --action save-draft 或 submit | 确定 create/update/submit、账户、目标 ID、修订、预期远端基线、明确字段和 digest；只生成交付计划。submit 必须已绑定且读到内容一致的 DRAFT |
| authorize --plan PLAN --human-reference REF | 保存用户明确授权的动作、计划摘要和来源；沿用现有授权证据规范。一次“保存草稿”请求可作为该次保存的授权；引用已有授权前核对精确计划。授权提交必须指向已审阅的具体版本 |
| claim --plan PLAN | 原子核对当前修订、授权、目标和在途尝试，持久化唯一 attempt，再向执行方返回动作、argv 数组和读回要求；重复调用返回既有状态，禁止再次分派 |
| observe --attempt ATTEMPT --response FILE --scope FILE | 登记执行结果或随后独立获取的 ASC JSON，记录证据摘要、来源、目标、账户与时间。同一份回执重放幂等；冲突或截断保留差异 |
| status --id ID | 展示本地修订、最后一次已验证的远端状态及观测时间、未完成尝试与恢复动作。离线可读 |
| reconcile --id ID [--remote-id RID] | 创建 read-only attempt 并导出核对请求。执行方获取新证据，经 observe 登记；接管既有远端草稿时先展示差异并明确绑定。该入口不能再次发送写请求 |

计划摘要对 schema、项目、账户、目标 App 集合、远端 ID、动作、修订摘要、基线和实际发送字段取规范 JSON 后计算 SHA-256。集合去重排序；保留正文换行和有意义的展示顺序。字段使用显式 patch 语义：省略保留旧值，有值则替换；若本机 ASC 无法无歧义清空某字段，计划阶段返回 unsupported_clear 和字段名，禁止静默保留。多值参数使用 ASC 定义的逗号列表；遇到无法无损传递的值返回具体字段错误。调用使用 argv 数组，不拼接 shell。更新前先比较完整预期结果，已一致则返回 no_change。

典型调用从本地评审开始。PLAN、ID 和 DIGEST 取上一步真实输出。以动作参数区分保存和提交，后者单独生成计划。

```sh
creative nomination --repo "$REPO" draft --brief nomination-brief.json
creative nomination --repo "$REPO" review --id "$ID"
creative nomination --repo "$REPO" plan --id "$ID" --action save-draft
creative nomination --repo "$REPO" authorize --plan "$PLAN" --human-reference "$AUTH_REF"
creative nomination --repo "$REPO" claim --plan "$PLAN"
# Publisher uses ASC and stores the returned response and executor scope.
creative nomination --repo "$REPO" observe --attempt "$ATTEMPT" --response "$RESPONSE" --scope "$SCOPE"
creative nomination --repo "$REPO" status --id "$ID"
```

scope 必须绑定 projectId、profileRef、appIds、attemptId、planDigest（写尝试）、操作阶段和 observedAt。首次创建响应只确立候选远端 ID，随后独立 view 才能标记 verified。命令成功输出结果对象；失败沿用 CLI 非零退出约定，给出稳定 reason、field（如适用）、retryableRead 与 nextAction。status 查询本身可成功返回 outcome_unknown。CI 依据业务状态断言。

## 5. ASC 操作映射及恢复

| 意图 | 实际执行 | 确认证据 |
| --- | --- | --- |
| 首次保存草稿 | asc nominations create --app IDS --name NAME --description TEXT --type TYPE --publish-start-date UTC --submitted=false，加明确的可选参数 | 保存返回的 data.id；再按 ID 执行 view，确认资源类型、App 集合、字段和 DRAFT |
| 保存新修订 | 对绑定 ID 使用 asc nominations update --id RID --submitted=false，附变更字段 | 新鲜基线检查后操作；回读同一 ID 和全部受管字段 |
| 正式提交 | 先回读草稿与已审阅修订一致，再执行 asc nominations update --id RID --submitted=true | 新回读为同一目标、内容一致且 state=SUBMITTED；记录 submittedDate（如响应提供） |
| 核对或恢复 | asc nominations view --id RID --include relatedApps,inAppEvents,supportedTerritories；未知 ID 时用 list 按 App、状态和分页检索，再逐个 view | 比较账户、资源 ID、关系全集、状态和受管字段；缺关系分页或证据过旧时显示 unverified |

写前探测所需命令与参数支持情况，缺项时给出版本与缺失能力。本机已验证 CLI 帮助，真实账户字段响应形状在试点采样后冻结。Apple 支持 Account Holder、Admin、App Manager、Marketing 等角色；以实际账号对目标 App 的权限为准。正式提交后 Apple 限制修改类型和关联 App；v1 对 Submitted、Archived 仅核对与展示。来源：[Apple 提名权限与编辑规则](https://developer.apple.com/help/app-store-connect/manage-featuring-nominations/nominate-your-app-for-featuring/)。

本地工作状态、执行尝试状态和 Apple 状态独立持久化。每条提名同时只允许一个未决写尝试。claim 在项目共享的同一存储锁内检查基线、写入 attempt 并原子提交，再返回执行指令。锁只保护本机协作；不同克隆操作同一 Apple 对象时采用单一执行工作区，写前、写后均回读。尚无已核实的 Apple 条件写或创建幂等键；最后一次回读和远端写之间仍存在跨客户端竞争，检测到差异后保留双方版本供审阅。

| 故障点 | 行为及恢复条件 |
| --- | --- |
| 写前发现 App、账户、状态或远端摘要变化 | 返回 conflict；展示字段 diff，重新生成计划。即使仍然叫同一名字也不能绑定 |
| 401/403 或明确参数拒绝 | 记录 rejected 和可修复原因。修复账户或输入，重新检查基线；变更计划时取得对应授权 |
| 网络超时、写调用 5xx、分派后进程退出 | 记录 outcome_unknown，保留在途尝试；只重试读取。已知 ID 直接 view，未知 ID 检索所有相关状态及分页；时间窗口、内容和 App 集合帮助缩小候选 |
| 创建结果未知且缺远端 ID | 列表零项不能证明创建失败，唯一相同文案也不能证明归属。保留待核对；需从原执行回执补回 ID 或由用户选定并确认绑定。只有查清原请求未执行才解除创建阻塞 |
| 返回了 ID 但业务回读失败 | 先落盘 ID；后续仅重试 view，限次退避并尊重 429 的 Retry-After（若可取得）。用尽后仍可凭原 attempt 继续 |
| Apple 已是 Submitted，本地停在提交中 | 新鲜且完全匹配的回读结束尝试；内容不一致则返回 conflict；均不再次提交 |
| 用户在 ASC 网页归档或删除 | 归档记 ARCHIVED；404 保留最后已知状态并报告目标不可见，提示核对账号与权限。禁止自动新建替代项 |

登记 observation 时保留响应原件摘要和受限存储引用，常规日志只含动作、匿名关联 ID、错误代码、耗时。原件可能含未公开发布计划；只请求必要字段，避免 include actor；公开 CI 输出与可分享报告排除原始文案、联系信息及私有 URL。传输结果、读回状态、是否获推荐分别报告。

## 6. 测试场景和验收证据

在 tests/ 使用 unittest.TestCase、TemporaryDirectory、固定时钟与最小 fixture。CLI 集成测试从实际 launcher 进入。用临时 PATH 的假 asc 返回 JSON、记录 argv、模拟调用中断；测试执行器使用相同的动作契约。每个写路径同时断言命令次数、目标 ID、外发字段、落盘状态及可重放结果。

| 编号 | 场景与注入 | 可判定的通过条件 |
| --- | --- | --- |
| N01 | 新发布、重大更新、新内容分别从 brief 起草 | 类型映射正确；同版本两个故事有独立 ID；缺日期亦能本地 review，远端计划指出缺项 |
| N02 | 中英文混合、多行、emoji、引号、shell 特殊字符 | review、argv、回读正文一致；执行器仅发一条预期命令 |
| N03 | 不存在的证据、替换文件、越界视频时间、路径穿越或外指符号链接 | 指出具体来源或范围；不能作为已核实依据生成写计划 |
| N04 | 明确的发布事实、未经证实的数字、仅有未来原型的演示 | 评审逐条比对“用户、动作、结果、时机”，已实现和计划中用语准确；外发稿中虚构结论为零 |
| N05 | 日期带偏移、无时区、逆序区间，固定时钟在 14 天边界及边界前一秒 | 等价时间得同一 UTC；不确定时间要求补全；短窗口只提示 |
| N06 | 设备与平台混用、地区当 locale、事件归属错误、真假值传字符串 | 字段级校验失败；没有远端写入；缺选填项不误报 |
| N07 | 本地路径、私有链接、带账号凭据 URL、未选择的材料 | 发送清单仅含已选可共享链接；内部证据和审核意见不出现在 argv |
| N08 | 同一草稿反复运行；随后从旧 base 并发修改 | 前者返回相同摘要；后者只有一个新修订成功，另一方收到可读 diff |
| N09 | 在不同 cwd 和带空格的根目录运行，repo 放在父或子命令 | 访问同一项目；旧配置懒初始化；未知 schema 不被重写 |
| N10 | 缺授权、用上传审批替代、把草稿审批用于提交、批准后改正文／App／材料 | 所有错误范围均拒绝分派；只需因真实变更重审；重复 status 不消耗授权 |
| N11 | 首次保存后修改已绑定草稿，重复保存相同内容 | create 恰好一次；更新使用原 ID 和显式 false；第三次零写入 |
| N12 | 两进程并发 claim、claim 后崩溃、写成功后丢失本地回执 | 仅首次 claim 可分派；重启可看到未决 attempt；未知结果时不会自动再次创建 |
| N13 | 提交前网页修改、归档或换账号；关系分页只返回部分 App | 检测目标或内容不一致，阻止写入；缺失关系不能当作空集合 |
| N14 | 正常提交；提交时超时但 Apple 实已接受；重新运行 | 最终由 view 证明 SUBMITTED；整个恢复过程中 submit 仅一次；无获推荐标记 |
| N15 | 同名多项、唯一同名但 App 不同、匹配项在第二页、暂时零项 | 查全分页，无法确认归属时维持 unknown；手动绑定必须核对完整目标 |
| N16 | 400、401、403、404、409、429、5xx、畸形 JSON、未知 state | 区分拒绝、冲突、读限流及写结果未知；保留最后可靠观测并给出下一动作 |
| N17 | 篡改证据字节、旧观测晚到、互相矛盾的响应、重复登记 | 拒绝摘要不符；旧观测不回退状态；冲突可见；同一证据重复登记幂等 |
| N18 | 远端选填字段省略、显式清空、集合顺序变化、URI 内含逗号 | 保留未编辑值；可表达的修改精确执行；不支持的清空或有损编码在发送前失败 |
| N19 | 两个工作区轮流修改同一 ID | 新鲜基线可发现先行变更；模拟读后竞争时检测可观测差异，报告剩余竞态 |
| N20 | 打包后从解压的 plugin 运行；CI 无凭据；日志扫描 | 可起草并走完模拟保存、修改、提交、恢复；零真实 ASC 流量；敏感 fixture 值不出现在常规日志 |

建议测试文件为 test_nomination_lifecycle.py、test_nomination_cli.py、test_nomination_asc.py 和 tests/fixtures/nominations/。发布前验证包括四片 macos-15 unittest、插件校验、解包 smoke。若第二阶段加入 Studio，执行 npm test、npx tsc --noEmit、npm run build 并核对跟踪的 dist。已有截图 publication 的批准、导出和状态测试必须原样通过。

## 7. 实现顺序与真实验收

1. **本地草稿**。先实现 draft、review 和 schema，交付三种类型的脱敏 fixture。用一个真实版本审阅“是否能从每条主要文案定位到同版本材料”。验收保存审阅结果及尚缺事实。此阶段离线可用。
2. **远端草稿**。实现 plan、authorize、claim、observe、status 和 reconcile；先通过 N08–N13、N15–N20。选定一个有权限的 App，在明确授权下保存 DRAFT，修改描述后再次保存。从 ASC 网页和 CLI 分别确认是同一 ID，留存脱敏响应 fixture。如返回格式与帮助不同，先修正归一化契约。
3. **正式提交**。实现 submit 专属范围、前置回读和超时恢复。假 ASC 完成 N14；真实提名仅在有实际发布计划且用户明确决定提交时验收。保存时间、远端 ID、授权修订摘要与独立回读。没有真实提交时标记为“模拟通过／真实提交待验证”。
4. **交付判定**。一次试点需回答四个问题：草稿是否基于可复核的产品体验；Apple 草稿是否可重复更新；发生不确定写入时能否恢复且无重复；已提交结论能否指向 Apple 回执。分别记录结果，避免将 CLI 退出码或编辑最终是否选中用于替代工程验收。

已有消费者按需启用该命令。发现适配器回归可暂停 Publisher 的 nomination 分派，继续读取本地记录及凭远端 ID 在 ASC 核对。回退版本保留新增记录与回执，避免失去未知写入的恢复线索。
