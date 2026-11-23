# Agent 驱动的 App Store 自定产品页面（CPP）

设计稿 · 2026-11-23 · [实施计划与测试矩阵](../sprints/custom-product-pages-implementation.md)

## 产品决策与试点

由现有 agent 读取活动简报、默认页、既有 CPP 和已验证素材，提出复用默认页、复用现有 CPP、更新 CPP 或新建 CPP 的建议。Creative Engine 负责验证证据、生成差异预览和可恢复的交付。远端操作复用 ASC 插件及开源 asc CLI。借鉴 AppTweak 按关键词观察创意和默认页对照的方式。付费竞品数据属于可选输入，无法证明效果。当前没有需要维护 CLI fork 的已知缺口。

首个用例选 Levelory 的「分享保存」教程，假设教程受众希望看到如何保存和找回一段文字。先验证发布版本确实支持所描述的分享方向，再校验画面顺序；从 App 向外分享的截图不能证明从其他 App 导入。如果找不到入口证据，返回补拍任务。以一个渠道、一种已有素材的语言和一个 iPhone 规格作为试点。多语言、iPad 和视频进入合同及回归用例。付费投放只交付获批页面的标识及链接，广告组、预算和竞价不属于本次执行范围。

## 数据流与接入点

| 组件 | 输入 → 输出 | 实施位置与复用 |
|---|---|---|
| Agent 编排 | 活动简报、页面快照、素材索引 → 有证据的推荐、排序、推广文案、缺口 | 扩展主 skill 的任务路由。模型由宿主选择。Python 接收结构化提案，支持无模型回放 |
| CPP 领域逻辑 | 提案、快照、配置 → 校验后的计划、差异、操作依赖及原因码 | 新增 runtime/scripts/cpp_campaign.py，在 app_store_creative.py 接线。project_path() 解析相对路径，父子共享参数使用 argparse.SUPPRESS |
| 素材与预览 | 卡片选择、语言、设备、已封存素材 → 按序媒体、对照清单、证据 | 复用 studio_contract.py、现有渲染、Validator、Delivery 封存。为活动派生独立工作区，按既有 target 规格和 DPI 导出。新增 CPP 血缘，保留原始素材 ID |
| Studio | 同一份计划及 revision → 默认页与 CPP 对照、缺口、选择回写 | studio_server.py 读取与 CLI 相同的合同。复用 CandidatePreviewMedia、PublicationHandoff 的交互方式。组件按语言和设备切换，键盘可重排，用文本描述差异 |
| Publisher | 封存交付、确切目标、授权 → 远端回执与状态 | 扩展 publication_lifecycle.py 的目标验证、计划校验和 asc_observation_adapter.py 的归属判断。保留归档取回、设计批准、精确上传授权及观察证据 |
| Analytics | Apple 详细报表、页面映射、日期范围 → 指标、覆盖情况、下一步建议 | 新增独立报表解析器，由 cpp report 调用。只读导入与发布操作可分别交付 |

## 持久化与接口

以下为拟实现的 v1 合同。产品仓库以 .creative/cpp/<campaignKey>/brief.json 保存可编辑意图。目录名仅接受小写字母、数字、连字符，拒绝路径穿越和越界符号链接。媒体按既有受管存储策略保存。指向封存产物的 ID 与哈希进入计划，避免在 Git 里复制媒体。远端绑定、操作回执和观察写入现有受管记录机制。旧项目缺少 CPP 配置即为空集合。

| 对象 | 必备内容与约束 |
|---|---|
| Brief | schemaVersion、稳定 campaignKey、appId、bundleId、platform、audience、channel、intent、releaseEvidence、locales、targets。platform 在入口规范为 IOS。iPad 用设备 target 表达。至少一个语言和规格 |
| Proposal | decision、rationale、比较过的页面及快照来源、按 locale 的文案与 keywords、按 locale × target 的有序媒体引用、claims 与 evidenceRefs、可选 deepLink 与落点证据、gaps。每项新增功能主张必须指向发布版本证据 |
| Plan | baselineRef、proposalDigest、输入快照摘要、按项目列出的 before/after、决策理由、blockers、nextAction、计划操作及依赖。固定规范化 JSON 与 SHA-256，数组顺序参与哈希，时间戳单列。模板继承/保留、显式替换和移除分别表示 |
| Binding | appId、bundleId、pageId、pageVersionId、每种 locale 的 cppLocalizationId、每种媒体/设备的 setId、可选 reviewSubmissionId。保留 Apple 原始状态、获取时间与响应摘要；一张页面可迭代多个版本 |
| Receipt | operationId、planDigest、目标、状态、远端标识、尝试序号、原始响应证据引用及摘要。媒体级记录 artifactId、sha256、顺序；独立记录页面 URL、可见性与验证时间 |
| Report | reportType、schemaProfile、源文件摘要、时间窗/粒度、关联页面、地区/来源/设备、metric/unit/value、coverage、缺失原因。脱敏输出；原始报表存入本地受管路径 |

拟定 CLI 示例，所有命令支持 --repo 和 --json。CLI 和 Studio 消费同一个 planDigest。

```sh
app_store_creative.py cpp plan --campaign share-save --proposal proposal.json --inventory snapshot.json
app_store_creative.py cpp preview --campaign share-save --plan plan.json --out review/
app_store_creative.py cpp handoff --campaign share-save --plan plan.json --out handoff.json
app_store_creative.py cpp status --campaign share-save
app_store_creative.py cpp report --campaign share-save --input reports/ --from 2026-11-01 --to 2026-11-15
```

plan 默认只读并向 stdout 输出，显式重定向可得到 plan.json。preview 只写指定预览目录。handoff 生成本地计划，由既有 publication 流程完成精确授权及导出。status 展示最后观察时间和证据。JSON 包含 schemaVersion、status、reasonCode、data、nextAction。成功或复用返回 0，非法输入返回 2，证据不足或冲突返回 3，可重试的执行故障返回 4。每个命令显示同等信息的人类可读摘要。

## 决策和生成

1. 读取默认页与现有 CPP 的完整分页清单。比较同一语言、规格下的首图、前三个叙事步骤、渠道承诺及功能落点。agent 提出语义判断并引用画面或文案；代码检查快照完整性、ID、媒体归属、声明证据可取回性。保留人工更改推荐的理由。
2. 默认页已表达活动意图且渠道无需独立 URL，选 reuseDefault。已获批且可见的 CPP 满足目的，选 reusePage 并返回其 URL。现有页面受众、落点相同且确需改动，选 updatePage 并列出使用旧链接的渠道影响。独立渠道链接确有价值且无可复用页面，选 createPage。缺页清单、多个候选归属不清、关键素材不足时返回 needsEvidence。
3. 本地校验语言覆盖、素材 SHA、方向、尺寸、顺序、推广文案长度与当前 Apple 字段约束。关键词取自最新已获批 App 版本对应语言，检查页面间关键词组合；可选深层链接取自已验证路由，附兼容系统和旧系统体验。按 Apple 配额预检，执行前刷新。证据不足可先展示草图，被阻塞的内容不进入可执行交付。
4. Preview 逐项显示继承、替换、删除、重排和文案变化，呈现视频及封面。所有对照使用同一份默认页快照，标明快照日期。编辑顺序或字句生成新摘要，使旧批准过期。竞品、用户粘贴文案和报表仅作为数据输入，不能产生可执行命令。

## 远端目标、审核与恢复

现有 publication_lifecycle.check_remote_target 校验 app_id、version_id、platform、bundle_id，尚不足以验证 CPP。将目标扩展为带 kind 的联合类型。缺 kind 的历史记录按 appStoreVersion 解释，按原字节验证既有摘要。customProductPageVersion 分支必须携带 app_id、bundle_id、platform、page_id、page_version_id，媒体操作另带 cpp_localization_id、display_type 和媒体种类。计划、审批准入、导出、观察、恢复统一分派。任何一层遇到未知 kind 都应报错。通过远端关系逐级校验 app → page → pageVersion → localization → set；刚创建的 ID 仅通过已核对响应或唯一可证实的远端关系绑定。

| 步骤 | ASC 7.1.0 的接入与验收 |
|---|---|
| 准备草稿 | Publisher 在获授权的准备计划内创建页面或选择既有可编辑版本。custom-pages create 自动创建初始版本和主语言 localization。先枚举再补缺。模板来源记录为已验证的 App 版本或已批准 CPP |
| 生成精确媒体交付 | 取得真实 ID 后重新构建绑定具体对象的 publication plan，按语言和设备复核封存清单，沿用精确上传授权。首阶段计划中的占位 ID 不可用于媒体上传 |
| 写草稿与验证 | 通过 localizations update、screenshot-sets、preview-sets、search-keywords 及 versions 命令按差异执行。媒体删除/替换须出现在授权差异中；将 sync 的全部副作用与差异核对。校验图序、校验和、视频处理、可播放性及封面解码 |
| 审核交接 | 输出 appCustomProductPageVersions 类型和准确 pageVersionId。首版由操作者在 ASC 确认提交，Publisher 记录回执并观察。已有获批 App 支持独立提交；首次上架时交接给同一 App 版本提审流程。处于审核锁定时只观察 |
| 分发 | 读取 Apple 返回的页面 URL、审核状态和可见性。验证相关 storefront 的链接指向预期 app 与 CPP。保存核验时间。被拒返回原因与修订入口；修订版审核中独立显示上一已发布版本的状态 |

为每一项写操作持久化 intent 和操作键（app、campaign、操作类型、目标槽位、预期内容摘要）。本地单写者使用已有租约，写前再读远端快照。新建、上传或提交观察超时时，标记 outcomeUnknown，恢复时先读回，唯一匹配则补回执并跳过，否则报告歧义。多个独立工作区操作同一页需共享执行记录或由同一 Publisher 串行处理；本地租约不能跨主机提供互斥。429 按 Retry-After 限次退避，401/403 转权限诊断，409 重新读取状态。部分成功从首个未证实操作恢复。停止活动时保留已发布链接和资产；停用页面属于独立显式变更。

## 分析与产品反馈

先做文件导入。依据 Apple Discovery and Engagement 与 Downloads 详细报告分别映射浏览事件、首次下载、重新下载。按报告版本识别列与粒度。优先用稳定 ID 关联，如源文件仅有 Page Title，使用 app、历史名称、日期有效期的唯一映射，歧义进入待匹配。幂等键包含报告类型、实例、分段和周期；同周期新修订替换旧值，避免日/周重复累加。

只使用 Apple 直接提供或能按同一官方口径还原的 CPP 转化率。缺少去重访客或可比口径时，只显示已有指标并解释原因。受隐私保护的缺行、尚未到数、真零分别表示。Apple 单页数据至少五次首次下载后可见，缺行本身无法推断人数。可选基准按来源、地区、设备和同一时间窗对齐；报告注明受众自行选择页面，任何表现差异只产生后续假设。试验默认页创意可另建 PPO。跨渠道复用同一链接且报表无法拆分时只报告页面级数据。

## 依据与验证边界

本设计核对了仓库源码与 asc 7.1.0 的本地 help，包括 create 隐式创建资源、媒体集、关键词和 review items add 的 CPP 类型。真实账号权限、远端响应、报表样本及真实审核结果须按实施计划取证。Apple 允许每 App 最多 70 个 CPP；页面支持 iOS/iPadOS 15 起，页面深层链接支持 18 起。

- [Apple 配置、可见性与关键词](https://developer.apple.com/help/app-store-connect/create-custom-product-pages/configure-multiple-product-page-versions/)
- [Apple 提交与审核锁定](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-a-custom-product-page/)
- [Apple 页面分析与隐私门槛](https://developer.apple.com/help/app-store-connect-analytics/acquisition/custom-product-pages/)
- [Apple 详细报表目录](https://developer.apple.com/help/app-store-connect-analytics/overview/analytics-reports-api)
- [ASC CLI 命令](https://github.com/rorkai/App-Store-Connect-CLI/blob/main/docs/COMMANDS.md)
- [AppTweak CPP Explorer 的覆盖范围](https://feedback.apptweak.com/en/help/articles/8266803-cpp-explorer-custom-product-pages)
