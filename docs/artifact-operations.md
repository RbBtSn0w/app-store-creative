# 产物生命周期运营操作说明

负责人：产品发布负责人；生产执行由 Creative agent 承担，远端操作由 ASC agent 承担。按每次物料发布执行。本文覆盖当前可用命令，完整目标及未完成事项见 [ADR 实施状态](adr/ADR-002-implementation-status.md)。本文不是一次真实产品发布的执行记录。

## 操作前提

确认项目、版本、平台、语言及所需截图、视频、封面矩阵；记录真实设计授权和独立上传授权。检查仓库现有改动，不覆盖他人的文件。使用插件自带运行时，先查看各层 `--help`。下文变量由执行者填写，所有 ID 必须来自实际命令返回值。

```sh
CREATIVE_RUNTIME=/absolute/path/to/plugin/runtime
CREATIVE_REPO=/absolute/path/to/product
creative() {
  "$CREATIVE_RUNTIME/scripts/app-store-creative" "$@"
}
creative storage --repo "$CREATIVE_REPO" inspect
creative storage --repo "$CREATIVE_REPO" git-policy --media-mode lfs
```

预期：四类存储根符合项目配置，正式归档及发布记录可跟踪，临时对象不会进入普通 Git。规则输出先审查；不自动修改 Git 历史或提交。路径冲突、权限或跟踪策略失败时先修正配置，再开始生产。自定义根及迁移详见 [存储迁移](storage-relocation.md)。

## 项目目录与本机覆盖

`creative.config.json`保存可共享制作配置；相邻的`creative.config.local.json`只保存本机存储覆盖。自定义配置文件名也使用同目录的`.local`后缀。优先级为内置默认值、共享项目配置、本机逐根覆盖。未指定objectRoot时，从最终workspaceRoot派生objects目录；相对路径始终以产品项目根解析，不依赖启动目录。

本机文档示例（project_id必须与共享配置的project.id一致，实际目录由执行者选择）：

```json
{
  "schema_version": 1,
  "project_id": "demo",
  "storage": {
    "workspaceRoot": "/Volumes/Creative Work/demo/work",
    "releaseRoot": "creative-releases",
    "publicationRoot": "creative-publications"
  }
}
```

本机文档不能覆盖卡片、配方、审批或发布参数。Git仓库必须实际忽略该文件且不得跟踪它；在现有`.gitignore`中审查后添加精确规则，例如`/creative.config.local.json`。已跟踪文件不会因忽略规则自动退出索引，插件会拒绝读取，索引调整由仓库负责人明确处理。不要提交本机绝对路径；仓库外正式归档还需按交付流程导出至可跟踪位置。

生命周期CLI、受管理截图生产和Studio预览、共享条件保存、捕获导入、海报及管理查询已使用有效配置。Studio目录字段编辑共享配置，预览显示本机覆盖后的路径；清空共享字段不删除本机覆盖。两份配置变化后重新加载页面或重建运行实例，旧版本请求不会自动改用新目录。

本机拥有层已支持受管理正向计划、准备、切换，以及未激活切换中断后的续执行/回滚；使用下文及存储迁移说明的明确操作，先审查Git建议。不要直接改本机根后把旧run当作新位置读取。本机反向计划、准备、切换及其安装后中断恢复/回滚已接入，并验证多次往返；成功激活目标后使用独立反向计划，不把中断回滚当作反向迁移使用。全部中断点、跨文件系统及进程中断恢复验收仍未完成。旧公开验证及发布路径已退出；真实渲染及两个产品全链路验收仍未完成，不能从配置示例推断真实生产已验收。

## 业务记录审计

```sh
creative history --repo "$CREATIVE_REPO" verify
```

业务记录提交前保存不可变事件，绑定精确记录路径、SHA-256、记录时间、执行客户端身份、Python版本及已知actor。客户端ID是本次内核实例的执行标签，不是经过认证的人类身份；未知actor保持null。事件不保存租约令牌或本机路径。新业务记录必须包含由内核分配的_commit_event_id，与唯一事件ID及完整字节哈希绑定；缺少或损坏该字段的旧记录拒绝读取，不补写兼容事件。记录落盘后审计派生COMMITTED，事件已落盘但记录缺失为INCOMPLETE，字节或时间不同且无另一份有效提交证明为CHANGED。写入失败后由合法接管生成另一份完整提交时，先前意图为NOT_COMMITTED并列出实际提交事件，不误报篡改。同一位置及同一预期哈希的重复声明仍使审计FAIL。CLI失败时返回非零退出状态。

Studio GET /api/history与CLI共用同一审计结果，拒绝任意工作区查询参数。审计使用已有写锁的共享锁与严格普通文件读取，不创建、修复或补写历史事件。保存事件失败不提交业务记录；提交业务记录失败保留未完成意图。产物和终止结果在事件持久化后再次复查租约，避免落盘期间过期的执行者继续提交。审计覆盖run、attempt/lease、artifact/import、输入及候选处置、验收、批准、交付、publication、远端观察及事故记录。迁移、清理和存储fence使用已有操作日志，目前不在这项审计覆盖内；完整执行工具身份、这些操作日志的统一查询与进程中断及文件系统错误恢复验收仍需完成。该审计验证本机提交证据，不代替设计授权、媒体真实性或ASC远端验收。

## 生产与候选验收

```sh
creative run --repo "$CREATIVE_REPO" start --target "$CREATIVE_TARGET_JSON"
creative run --repo "$CREATIVE_REPO" status --id "$CREATIVE_RUN_ID"
```

目标文件按当前配置与运行合同准备，不以文件名推断目标或状态。截图生产、视频制作和原生录制按各 producer skill 的受管理流程执行：登记来源、输入依赖、逻辑路径、租约及终止结果。已有独立文件必须登记后才能进入候选。失败、取消和中断保留原尝试及原因，重试建立新尝试；不得改写失败结果为成功。

对已登记且成功的视频提取封面：

```sh
creative preview --repo "$CREATIVE_REPO" poster --run-id "$CREATIVE_RUN_ID" --preview-id "$CREATIVE_PREVIEW_ID" --timestamp "$CREATIVE_POSTER_SECONDS" --owner "$CREATIVE_OWNER" --confirm EXTRACT
creative candidate --repo "$CREATIVE_REPO" select --run-id "$CREATIVE_RUN_ID" --artifact "$CREATIVE_SCREENSHOT_ID" --artifact "$CREATIVE_PREVIEW_ID" --artifact "$CREATIVE_POSTER_ID"
creative candidate --repo "$CREATIVE_REPO" validate --id "$CREATIVE_CANDIDATE_ID"
```

示例选择三类媒体；实际按完整语言和设备矩阵重复 `--artifact`，保持展示顺序。验证必须为当前候选绑定的 `media-v1` PASS 且错误列表为空。验证失败先检查实际媒体与来源，修正后建立新候选。向人展示精确候选及验收结果，视觉质量不能由媒体格式检查替代。

## 设计批准与封存

```sh
creative approval --repo "$CREATIVE_REPO" record --candidate-id "$CREATIVE_CANDIDATE_ID" --validation-id "$CREATIVE_VALIDATION_ID" --actor "$CREATIVE_HUMAN" --authorization-reference "$CREATIVE_DESIGN_AUTHORIZATION" --confirm APPROVE
creative delivery --repo "$CREATIVE_REPO" seal --candidate-id "$CREATIVE_CANDIDATE_ID" --validation-id "$CREATIVE_VALIDATION_ID" --approval-id "$CREATIVE_DESIGN_APPROVAL_ID"
creative delivery --repo "$CREATIVE_REPO" status --id "$CREATIVE_DELIVERY_ID"
```

预期：本地状态 PASS，包、配方和来源验证均通过；远端仍为 UNKNOWN。批准引用必须来自真实人类授权，非空字符串本身不能证明同意。批准范围过期或封存失败时保留记录，重新验证或重新批准；不得手工编辑封存包。内容变更生成新候选和修订。

仅在用户授权 Git 操作后持久化配置、必要来源、封存清单及媒体；按 git/LFS 策略处理，不提交工作根、租约令牌、认证信息或未经脱敏日志。记录实际完整提交 SHA 和可信清单哈希，再执行独立取回验证：

```sh
creative archive --repo "$CREATIVE_REPO" verify-git --commit "$CREATIVE_ARCHIVE_COMMIT" --remote "$CREATIVE_ARCHIVE_REMOTE" --path "$CREATIVE_ARCHIVE_REPO_PATH" --expected-sha256 "$CREATIVE_MANIFEST_SHA256"
```

预期：从独立克隆取得该提交的完整包并验证字节。失败时排查实际提交、忽略规则、LFS 对象和远端访问；本地目录存在不能替代持久化证据。详见 [Git 归档取回](git-archive-retrieval.md)。

## 发布交接与远端验收

ASC 负责解析真实 app、version、platform 和远端资源；Creative 不持有其认证或实现其写入 API。目标 JSON 包含 `app_id`、`version_id`、`platform`。

```sh
creative publication --repo "$CREATIVE_REPO" plan --delivery-id "$CREATIVE_DELIVERY_ID" --archive-commit "$CREATIVE_ARCHIVE_COMMIT" --archive-remote "$CREATIVE_ARCHIVE_REMOTE" --target "$CREATIVE_ASC_TARGET_JSON"
creative approval --repo "$CREATIVE_REPO" record-upload --publication-id "$CREATIVE_PUBLICATION_ID" --actor "$CREATIVE_HUMAN" --authorization-reference "$CREATIVE_UPLOAD_AUTHORIZATION" --confirm APPROVE
creative publication --repo "$CREATIVE_REPO" export --id "$CREATIVE_PUBLICATION_ID" --confirm
```

将导出的精确目标、计划、清单、批准范围交给 ASC。导出不是上传。ASC 在执行前重新查询远端，核对替换范围及重复操作风险；真实写入遵循独立上传授权。

```sh
creative publication --repo "$CREATIVE_REPO" observe --id "$CREATIVE_PUBLICATION_ID" --observation "$CREATIVE_OBSERVATION_JSON" --evidence "$CREATIVE_OBSERVATION_EVIDENCE"
creative publication --repo "$CREATIVE_REPO" status --id "$CREATIVE_PUBLICATION_ID"
```

观察必须绑定计划哈希、目标、媒体及远端资源身份、门禁、时间、来源、证据引用、实际证据字节的SHA-256和事实。CREATIVE_OBSERVATION_EVIDENCE指向执行方保留的原始证据文件；登记时内核核对其字节，缺失或内容改变拒绝。分别验收上传、处理、播放及封面，不从选中时间码或上传日志推断封面可加载。已提供下文的官方ASC预览列表响应转换入口，但它只转换上传、处理及封面属性事实；应用/版本/语言关联由ASC执行方核验，播放和封面加载仍需独立证据。缺少可靠观察时保留UNKNOWN，有矛盾时处理CONFLICT，不能人工制造PASS。

## 收尾、清理与恢复

检查运行历史、交付状态和 [库存](artifact-inventory.md)，保留失败原因并报告未知文件。清理先计划再审查；候选、批准、交付、发布、事故和有效租约引用均需保护。不传保留期时使用项目artifactPolicy：普通试制和明确登记的诊断物料分别按各自保留期计算。显式覆盖仅用于已经审查的本次维护决定；不要复制固定天数替代项目策略。容量未知时不将其解释为预算通过。

```sh
creative storage --repo "$CREATIVE_REPO" artifact-policy
creative storage --repo "$CREATIVE_REPO" media-budget
creative cleanup --repo "$CREATIVE_REPO" plan
creative cleanup --repo "$CREATIVE_REPO" quarantine --id "$CREATIVE_CLEANUP_PLAN_ID" --actor "$CREATIVE_HUMAN" --reason "$CREATIVE_REASON" --confirm QUARANTINE
creative cleanup --repo "$CREATIVE_REPO" restore --id "$CREATIVE_QUARANTINE_OPERATION_ID" --actor "$CREATIVE_HUMAN" --reason "$CREATIVE_REASON" --confirm RESTORE
```

隔离与恢复按需选择，不连续机械执行。计划过期时重新生成；恢复后复查实际对象。永久删除使用独立计划和授权，不能复用隔离授权：

```sh
creative cleanup --repo "$CREATIVE_REPO" plan-purge --id "$CREATIVE_QUARANTINE_OPERATION_ID"
creative cleanup --repo "$CREATIVE_REPO" purge --id "$CREATIVE_PURGE_PLAN_ID" --actor "$CREATIVE_HUMAN" --reason "$CREATIVE_REASON" --confirm PURGE
```

隔离期默认采用项目artifactPolicy.quarantineDays；显式覆盖需要针对本次计划审查。永久删除不能承诺可恢复；未知文件不在清理范围。工作文件/日志的完整保留策略和孤立对象处置仍待实现，不能据此删除整个自定义目录。

## 故障处理与责任

| 情况 | 下一步与成功证据 | 责任 |
| --- | --- | --- |
| 租约过期或生产中断 | 查看原尝试，按 `attempt recover --help` 明确接管；保留中断记录及新尝试结果 | Creative 执行者 |
| 包或来源损坏 | 停止发布；以可信清单哈希验证独立归档或恢复副本，不原地改写批准包 | Creative 与仓库负责人 |
| 封面无法加载 | 保留远端 ID、查询时间及真实处理/封面响应；由 ASC 诊断并在授权范围内修正 | ASC 与发布负责人 |
| 远端结果不确定 | 重新查询同一操作及资源；取得证据后再决定重试，避免重复上传 | ASC |
| 清理引用图缺失或循环 | 停止清理并保护有关对象；修复登记关系后重新计划 | Creative 内核维护者 |
| 目录迁移中断 | 按迁移说明从原工作根续执行或回滚未激活目标；复查哈希和绑定 | Creative 与存储负责人 |
| 已切换目录需要撤回 | 先核对原副本，按存储迁移说明建立反向计划、准备、切换；中断从反向操作开始前的工作根显式续执行，保留备份 | 内核维护者 |

事故需要长期保护时使用 `incident open` 绑定有关 artifact、candidate 或 delivery；解决后用 `incident close` 记录处理结论。联系负责人由项目提供，插件不编造联系人或自动发送消息。

## 完成记录

每次执行记录实际运行与交付 ID、可信清单哈希、Git 完整 SHA、设计/上传授权来源、发布 ID、各远端门禁证据，以及异常和恢复结果。凭据和租约令牌不进入共享记录。只有本地和要求的远端门禁均有可信证据才能宣布发布完成。本文尚待两个真实产品的完整执行演练，命令存在不等于运营验收已完成。

### ASC Preview 响应转换

`publication normalize-asc-preview --id <publication-id> --response <asc-response.json> --scope <executor-scope.json>`读取现有发布计划，输出`observations`数组，不写入观测记录或远端。响应来自官方ASC插件执行的`asc video-previews list --version-localization <resource-id> --output json`。执行方必须先核对该本地化资源属于计划指定的应用、版本及物料语言；响应本身不能证明应用/版本归属。

scope必须包含且仅包含target、artifact_id、localization_id、remote_id、observed_at、evidence_reference。target必须与计划完全相同；artifact_id必须为计划内Preview物料；时间必须带时区，证据引用为不含凭据或资源URL的执行方标识。将输出数组中的每项保存为独立JSON，再使用既有`publication observe --id <publication-id> --observation <observation.json> --evidence <original-response.json>`登记。

转换分别提取上传校验和、处理状态和封面时间码/尺寸。0尺寸形成封面失败事实；正尺寸或视频URL都不能证明图片加载或播放成功，仍需独立浏览器或媒体验证。2026-10-07实际只读查询Levelory 1.5英文Preview返回COMPLETE与0×0封面，转换结果保留这两个独立事实。该查询不等于新合同发布全流程验收。

### Studio 记录检查

Studio的Record verification面板通过Check records显式查询/api/history，与CLI history verify共用内核。重新检查时清除旧结果，错误不会保留旧成功状态。面板分别显示提交完成、写入未完成、内容变化、已证明未提交的意图，以及缺失事件和重复引用；展开Check scope查看实际覆盖范围。该检查不代表迁移/维护操作日志或远端物料就绪，后两者仍由各自门禁判定。

### 发布计划与远端门禁查看

CLI publication list和Studio Publication verification面板读取相同的计划列表，支持limit/cursor。GET /api/publications/<id>与publication status共用内核：上传、处理、媒体/播放、封面各自保留PASS、FAIL、CONFLICT或UNKNOWN，归档完整性、取回验证及上传批准单独呈现。界面仅检查已保存且符合新鲜度门禁的观测；Check saved evidence again不会执行远端请求，也不会上传。缺失或过期时交由官方ASC执行方重新查询并登记观测。

### Studio 设计批准与封存

生产后选择当前候选，在Approve and archive this candidate中先Validate candidate。仅PASS才显示批准表单；填写批准人和授权依据，并主动勾选设计审阅确认后，Record design approval将候选与准确验证ID绑定保存。再点击Seal release archive生成不可变归档。配置有未保存改动时该流程不显示；切换候选重置表单。批准人字段是操作方声明，不是身份认证。设计批准不授权上传，上传仍要求绑定发布计划的独立批准。HTTP动作只接受明确字段，保留本地来源/跨域限制，调用与CLI相同内核。请求超时可能已经提交，不应自行生成另一份授权依据；可通过记录和交付历史核对。

候选审阅可通过candidate review --id <candidate-id>或GET /api/candidates/<id>/review重新读取。Studio初始化先读取已有状态；请求失败后暂停新的批准/封存，使用Check saved review核对保存结果。读取选择已封存链或已批准链，并重新核验候选、准确验证和批准绑定，已封存归档必须通过本地检查。该查询不新增批准，不迁移旧记录。

### 迁移与维护日志查询

history operations、GET /api/history/operations及Studio Load operation journals共用只读查询。覆盖relocations、maintenance、storage-fences与storage-fence-releases，显示记录身份、创建时间、操作、声明状态及记录哈希。查询持有已有读锁并拒绝符号链接和非法记录布局，不改写日志，也不追加事件导致迁移快照失效。OBSERVED与execution_verified=false明确说明仅观察记录事实；操作特定验证、恢复及删除授权仍须独立执行。

### 明确放弃缺失提交

history abandon --event-id <id> --actor <operator> --reason <reason> --confirm ABANDON只处理目标记录当前缺失且没有其他业务记录引用的提交意图。持有写事务重新核验意图，保存哈希绑定且不可变的commit-abandonments决定及其提交事件；原意图保留，文件不删除，未知或已提交目标拒绝。审计ABANDONED表示操作方明确放弃该缺失提交，不证明目标过去从未存在，也不证明产物生产成功。若记录意外丢失，应优先调查并恢复准确备份，不能用该命令代替数据恢复；引用保护失败必须先处理所属业务链。该决定属于账目闭环，候选、批准及远端门禁仍独立。Studio只展示该状态，不自动放弃。

明确放弃后，该类别/身份/后缀对应的提交位置不再允许重新发布，内核在写入事件前拒绝。后续工作必须创建新的运行或尝试身份，不能借重试复活已放弃的位置。

### 命名外部文件系统媒体后端

archive persist-media --artifact-id <id> --backend <name> --backend-root <absolute-root> --confirm PERSIST持久保存已登记物料，并从后端独立取回校验后记录external-media引用。引用仅保存provider、后端名称、内容寻址对象ID、不可变版本、SHA-256及字节数，不含本机路径、凭据或URL。当前provider为filesystem，可指向项目之外的持久目录或挂载存储；该实现不自动创建云服务或处理其认证。后端根必须与四类受管理目录不重叠。

archive restore-media --reference-id <id> --backend <name> --backend-root <absolute-root> --confirm RESTORE核验准确外部版本，恢复缺失CAS并保存external-retrievals记录。原物料元数据不改变；已有本地字节仍必须通过完整性检查，不覆盖损坏或用户文件。缺失外部版本拒绝，不回退到本地生产源或ASC资源。未知文件和失败后未引用对象不自动删除。单对象存取已进一步接入下述external交付元数据及克隆恢复；publication归档门禁已接通，实际持久后端仍待验收。

### 外部交付清单与独立恢复

archive verify-external-git --commit <full-commit> --path <repository-relative-bundle> --expected-sha256 <trusted-descriptor-sha256> --backend <name> --backend-root <absolute-root> --remote <configured-remote>从配置远端独立克隆指定完整提交，取回该提交的元数据包及准确外部对象版本，验证完整交付、来源图和配方。省略remote仅验证本地仓库，输出明确区分来源。命令不依赖原生产工作区，不写远端，也不把后端访问路径加入证明。该取回证明已接入发布计划、批准及ASC本机文件准备；实际ASC远端执行仍待验收，不能据此宣布发布流程已完成。

archive externalize --delivery-id <id> --backend <name> --backend-root <absolute-root> --confirm EXTERNALIZE从已封存并核验的交付生成新的不可变元数据包，位置由publicationRoot管理。原归档不修改；媒体及全部recipe/inputs转为稳定后端引用，保留原manifest、recipe/config和其余证据。external.json绑定原清单哈希和全部外部对象路径/版本/大小；发布元数据包前先作为独立消费者完整取回并通过原归档验证。external-archives记录绑定交付ID及descriptor_sha256，记录不含后端根目录。

授权后可将该元数据包提交Git；不要提交后端对象目录或本机访问路径。archive restore-external --path <metadata-bundle> --destination <new-directory> --expected-sha256 <trusted-descriptor-sha256> --backend <name> --backend-root <absolute-root> --confirm RESTORE不依赖项目配置或原工作区。完整取回所有媒体/配方输入并验证原清单、来源图及配方后才原子发布新目录。descriptor哈希必须来自可信交付或已核验提交；不能从待验证的包自己生成哈希来替代信任绑定。缺失、损坏、额外文件、链接、覆盖目标和不完整引用均拒绝，失败不发布半成品目录。当前已用临时Git真实干净克隆验证；publication计划已接入external归档的提交/远端绑定，实际持久共享后端尚待验收。

### 外部归档发布计划与 ASC 文件准备

publication plan-external --external-archive-id <id> --archive-commit <full-commit> --archive-path <repository-relative-bundle> --archive-remote <configured-remote> --backend-root <absolute-root> --target <target.json>绑定已经登记的外部归档、可信descriptor哈希、准确Git提交及独立取回证明。目标必须明确app_id、version_id及platform。资产路径相对于hydrated-package，不是假定Git元数据目录存在媒体。上传批准和发布状态共用外部归档身份及提交检查；缺失远端观察仍为UNKNOWN。

上传批准绑定该计划后，publication prepare-external --id <publication-id> --backend-root <absolute-root> --destination <new-directory> --confirm PREPARE重新从指定提交和外部准确版本完整取回，生成ASC执行方可使用的实际文件路径及计划哈希。目标必须不存在，不覆盖已有文件。返回值是本机执行交接，包含本机文件路径，不应作为便携发布计划提交Git。该操作不上传，官方ASC插件仍负责远端执行与独立结果观察。生产持久后端、实际ASC执行和两个真实产品验收仍未完成。

外部发布计划、批准、导出及状态检查不依赖原交付目录、元数据工作副本或本机对象缓存；仍需要保存的生命周期记录和绑定准确提交的Git仓库。准备文件从指定远端提交及外部准确版本重新取回。临时远端克隆与公开CLI已验证，尚不是生产持久后端或真实ASC上传验收。

准备入口会流式核对取回文件的SHA-256和计划上传MD5；publication preparation-status --id <preparation-id>再次核对实际文件，返回files_verified不能代替远端上传或播放。计划媒体顺序、路径、身份、角色、SHA及海报时间码也必须与绑定提交的清单和配方一致。checksum不匹配时不生成准备回执，已取回目录保留供诊断；不要绕过核验把该目录交给上传方，也不要原地修改批准计划。复查错误来源后建立新的计划/批准和新的准备目标，旧目录按授权维护流程处置。

### 本机命名后端配置

在与项目配置同名的受保护local文件中声明mediaBackends，文件必须由真实Git规则忽略且未被跟踪。名称是归档内的稳定标识；root是该机器的访问位置，不进入配方配置或便携发布计划。例如creative.config.local.json：

```json
{
  "schema_version": 1,
  "project_id": "your-project-id",
  "storage": {},
  "mediaBackends": {
    "team": {
      "provider": "filesystem",
      "root": "/Volumes/CreativeArchive"
    }
  }
}
```

受管理persist-media、restore-media、externalize、publication plan-external及prepare-external可省略backend-root，由同一内核配置解析。明确传入backend-root仍表示本次指定访问位置；未配置且未传入时拒绝，不自动猜测或使用生产路径。独立restore-external/verify-external-git仍要求显式访问位置，使干净消费者不依赖项目配置。搬迁四类存储根保留mediaBackends，本机文件整体内容仍参与配置版本复查。当前只支持filesystem，不接受凭据、未知字段或相对根目录。

ASC本机准备结果保存为不可变publication-preparations记录，包含准备ID、准确计划哈希、取回证明和实际资产路径，并进入提交事件审计。publication preparation-status --id <preparation-id>持有读锁重新核验记录与计划绑定、完整归档及资产列表，媒体缺失或变化为FAIL，不更新原记录。PASS仅证明该次准备文件当前有效，不代表上传、处理或远端可播放。准备记录含本机路径，不能作为便携发布清单提交Git；重复准备需新的不存在目录，不覆盖之前结果。

## Studio发布交接接口

Studio HTTP已接入上传批准和交接导出，分别为POST /api/publications/approve-upload与POST /api/publications/export。批准必须提供publication_id、actor、authorization_reference及confirm=UPLOAD；导出提供publication_id及confirm=EXPORT。额外字段或查询覆盖拒绝。内核核对原归档和独立取回证据，批准绑定具体计划哈希和远端目标。

导出仅写本地不可变交接材料，明确uploaded=false、remote_write=false。没有批准时交接仍标记pending，不能据文件存在授权上传。ASC插件负责实际远端执行和复查。2项HTTP回归通过，包含错误批准确认拒绝及批准/导出后远端仍未验证；前端协调表单及真实ASC验收尚待完成。

发布状态面板选择计划后，可用Load bound upload plan加载经过归档复查的具体目标、计划哈希和完整资产列表。填写真实批准人与授权引用、勾选审查后才可批准上传；导出另需审查确认。执行后清除旧预览并要求重新加载，失败不会自动重试。前端选择其他计划时重建表单，不沿用旧批准勾选。表单已接入；真实浏览器及远端执行验收仍待完成。

发布交接真实浏览器验收在明确模拟媒体/批准的独立测试项目完成：加载计划与具体目标/物料、默认未勾选审查、保存测试上传批准、重新加载及独立确认导出，最终状态批准已保存但远端仍未验证。独立内核核验本地plan.json存在、uploaded=false与remote_write=false。证据/tmp/creative-publication-browser-proof.json及截图；不代表真实人类产品批准或ASC上传。

## 维护操作执行核验

```sh
python3 app_store_creative.py history inspect-maintenance --repo /path/to/project --id OPERATION_ID
```

该命令及GET /api/history/maintenance/OPERATION_ID、Studio历史列表的Check current execution使用同一读锁核验。确认准确操作ID，查看phase、status、execution_verified和errors。计划返回NOT_EXECUTED；未终结操作返回INCOMPLETE；损坏或身份变化返回FAIL；不支持的作用域为UNKNOWN。只有具体作用域PASS才证明该次检查时的执行效果；全量history operations仍是记录观察。

普通对象清理核验完整计划/存储绑定及字节；永久清理终态核对意图、逐文件检查点、准确容量和待删位置缺失。搬迁副本核验身份、内容和历史位置投影。错误时保留现有记录和现场，使用原计划的明确恢复入口处理，不重新创建替代清理计划，不把状态检查当作删除授权。
