# 受管理物料的维护与恢复

本说明对应统一生命周期内核的当前实现。维护只操作内容寻址对象库中已登记的本地试制物料，不处理正式归档、Git历史、LFS远端或外部存储。不要通过删除目录代替这些操作。

所有命令使用消费项目的creative.config.json解析storage配置。相对路径相对消费项目根；CLI与Studio共享内核。以下命令中的ID必须来自实际返回记录，不能用目录名猜测。

```sh
python3 app_store_creative.py storage inspect --repo /path/to/project
python3 app_store_creative.py inventory --repo /path/to/project
```

## 弃用候选

候选不再使用时，记录操作者和具体原因。弃用记录不可修改，原候选仍保留；需要重新选择时创建新的候选。弃用后不能再次验收或封存，Studio当前候选查询会排除它。

```sh
python3 app_store_creative.py candidate discard --repo /path/to/project \
  --id CANDIDATE_ID --actor OWNER --reason "Incorrect locale" --confirm DISCARD
```

候选弃用不撤销审批或归档引用。有审批或交付引用的候选继续保护其物料及依赖。相同字节只要仍有受保护引用，就不能回收。

## 计划、隔离与恢复

未选用且已终止的媒体采用项目 artifactPolicy.trialRetentionDays，未声明时为30天；已弃用候选从弃用记录时间起也保留相应时长。活动尝试、现有候选、审批、交付、未结事故、当前配置及未退役输入库引用持续保护。保留参数属于显式项目维护策略，不能为了腾空间随意缩短。

```sh
python3 app_store_creative.py cleanup plan --repo /path/to/project
python3 app_store_creative.py cleanup quarantine --repo /path/to/project \
  --id CLEANUP_PLAN_ID --actor OWNER --reason "Expired unused trials" --confirm QUARANTINE
python3 app_store_creative.py cleanup restore --repo /path/to/project \
  --id QUARANTINE_OPERATION_ID --actor OWNER --reason "Recover trial" --confirm RESTORE
```

先审查计划的对象、大小、来源artifact列表与保留期限，再执行隔离。执行前重新检查生命周期记录和文件哈希；新增引用或文件变化使计划失效，必须生成新计划。未知文件不进入计划。

记录树或对象库读取不完整时，计划及执行都拒绝继续；不把读取失败当作零个对象或零个引用。inventory中的null及observation_errors表示观察缺口，需要修复后重新检查和规划，不能据此授权清理。

隔离操作意图先登记，再逐对象建立隔离副本并移除活动位置。隔离副本位于配置对象库内，以支持同一文件系统操作。中断后可以按隔离操作ID恢复；恢复前检查全部可用字节，不覆盖损坏的现有对象。恢复保留隔离副本，支持重试。

恢复在首次对象修改前保存并同步不可变restore-intent，绑定原隔离操作、清理计划及存储范围。恢复中断后以相同QUARANTINE_OPERATION_ID继续，不重写原意图；独立状态为INCOMPLETE/RESTORING。完成回执绑定意图哈希，完成核验同时检查活动对象和保留副本。缺失意图、记录范围变化或损坏字节拒绝继续，不自动补造历史。恢复一旦开始，新的永久清理计划和此前建立的永久清理计划均拒绝执行。

## Studio维护入口

Storage maintenance面板与CLI共用上述保留、引用与哈希检查。Create plan仅保存计划，不移动字节；面板列出每个对象完整SHA-256、字节数和总容量。填写Operator与Reason后仍须勾选明确确认才可隔离；隔离后确认自动清除，恢复需再次确认。历史支持分页，恢复后的记录在刷新后仍可读取。

请求失败时不自动重试写操作，需先重新读取记录，避免把响应丢失误判为未执行。界面的recorded status来自保存日志，execution_verified仍为false，不替代独立文件核验。永久删除使用独立Create permanent deletion plan入口及Quarantine days（默认7日）。审查计划后，必须填写操作者和原因、勾选授权，并准确输入PURGE；执行前内核重新检查保留期和引用。失败或响应丢失仍须先读取记录，不自动重试。搬迁副本使用独立面板及维护接口，详见下文。

## 永久删除隔离副本

隔离完成后采用项目 artifactPolicy.quarantineDays，未声明时为7天。永久删除需要单独生成计划和明确确认；普通导出、关闭Studio或进程退出不会执行删除。

```sh
python3 app_store_creative.py cleanup plan-purge --repo /path/to/project \
  --id QUARANTINE_OPERATION_ID
python3 app_store_creative.py cleanup purge --repo /path/to/project \
  --id PURGE_PLAN_ID --actor OWNER --reason "Quarantine retention expired" --confirm PURGE
```

执行前再次验证引用、保留期、存储绑定、大小与哈希。恢复过的隔离操作不能使用旧计划删除；需要重新生成清理流程。永久删除开始后无法恢复该隔离操作。中断重试使用原PURGE_PLAN_ID；不要新建计划掩盖部分执行状态。未知隔离文件和全部业务记录继续保留。

## 迁移源副本与备份规划

迁移保留副本使用独立的维护计划，不能交给上述试制对象的quarantine或purge执行。当前已实现规划、即时复查及隔离准备；隔离提交与恢复已接入；迁移隔离副本永久删除已接入，仍需更多跨操作协调和真实故障验收。

```sh
python3 app_store_creative.py cleanup plan-relocation-retention --repo /path/to/project
python3 app_store_creative.py cleanup verify-relocation-retention --repo /path/to/project \
  --id RELOCATION_RETENTION_PLAN_ID
```

未指定期限时采用项目artifactPolicy.trialRetentionDays；显式传入--retention-days表示本次维护已审查的覆盖值。期限从迁移切换完成回执计算。计划保护工作文件、恢复元数据、配置引用和待恢复操作；只将有独立有效活动对象的已登记CAS副本列为候选。复查同时核验路径、目录与文件身份、内容、当前配置及非维护生命周期记录快照。任何变化使原计划失效；READY只说明当前核验通过，不会执行文件移除，也不能作为之后绕过重验的凭据。记录与库存字段见artifact-inventory.md。

### 隔离准备与中断

```sh
python3 app_store_creative.py cleanup prepare-relocation-quarantine --repo /path/to/project \
  --id RELOCATION_RETENTION_PLAN_ID --actor OWNER --reason "Expired relocation copies" --confirm PREPARE
python3 app_store_creative.py cleanup resume-relocation-quarantine-preparation --repo /path/to/project \
  --id RELOCATION_QUARANTINE_OPERATION_ID --actor OWNER --reason "Resume interrupted preparation" --confirm PREPARE
```

准备先复查原计划，创建独立操作ID及受管理的工作区隔离根，登记目录身份和持久意图，再独占创建媒体文件。媒体文件通过已核验的目录FD相对独占创建，目录被替换时不会转写到替换位置。每个文件在复制前登记其inode，复制后校验大小、哈希及身份并同步文件和父目录。全部副本有效、原计划仍匹配时才写PREPARED回执。该状态的source_removal_executed为false：源副本和活动对象都仍在原位置。

中断保留操作、创建回执及首次preparation-failure状态。同步中断后已有完整字节可续执行，不重写文件；残缺、损坏、同字节替换、目录别名和未知文件均拒绝。残缺文件保持原样，必要时使用新操作ID重新准备，不自动覆盖或删除旧操作。已完成准备的续执行再次核验并返回原回执。无候选或过期计划在创建操作前拒绝。准备数据位于workspaceRoot/maintenance/relocation-quarantine，已纳入统一inventory的quarantine_preparations，包含准备阶段、实际内容状态、未知文件和容量；这些准备副本不是正式发布物料；提交、恢复及永久删除按下方独立流程执行。

### 取消隔离准备及迁移协调

尚未开始提交的准备操作可以显式取消，包括中断准备。取消只登记不可变回执，保留源文件、准备区文件、未知文件及全部历史记录；不表示释放空间。重复取消返回原回执，之后禁止续执行准备或提交。同一操作已有提交或删除意图时不能取消，应使用对应恢复或续执行流程。

```sh
python3 app_store_creative.py cleanup cancel-relocation-quarantine-preparation --repo /path/to/project \
  --id RELOCATION_QUARANTINE_OPERATION_ID --actor OWNER --reason "Keep retained copies" --confirm CANCEL
```

正向及反向迁移的计划、复查和准备共用维护门禁。未终结的试制对象隔离，以及迁移副本准备、隔离提交和部分删除都会阻止迁移；不能仅通过重新规划绕过。经验证的取消、恢复或永久删除终态允许再次规划。迁移后再次规划通过已验证的位置绑定链核验历史维护元数据，不能把当前目录名当作原操作证据。

已完成迁移后的隔离准备区库存使用迁移准备及激活回执核验当前位置和新副本身份，包括反向返回原目录；原维护记录不改写。完整保留副本位置投影仍未完成；迁移中断续执行及反向回滚已核验日志定位的隔离副本和保留备份身份，全部父路径竞态及真实断电仍待验收。未核验内容继续报告异常，不能用于新清理授权。

### 隔离提交与恢复

```sh
python3 app_store_creative.py cleanup commit-relocation-quarantine --repo /path/to/project \
  --id RELOCATION_QUARANTINE_OPERATION_ID --actor OWNER --reason "Expired copies" --confirm QUARANTINE
python3 app_store_creative.py cleanup restore-relocation-quarantine --repo /path/to/project \
  --id RELOCATION_QUARANTINE_OPERATION_ID --actor OWNER --reason "Recover retained copies" --confirm RESTORE
```

提交在同一事务中复查计划和准备副本，先登记并同步commit-intent，再把每个原文件独占移动到同父目录的.creative-quarantine-<operation-id>-<index>位置。目录FD和文件身份验证避免覆盖既有目标；文件inode保留，准备区的独立复制也保留。该阶段移除原路径但不释放媒体容量；字节永久移除必须经过后续单独purge计划，不复用试制对象purge。

多文件中断时只允许原位置或登记隔离位置之一持有确切文件身份和字节。续执行重新核验完整原计划，新增引用或未知变化会阻止剩余移动；恢复不要求旧引用快照仍有效，但验证操作、准备回执、提交意图、根和文件身份，并在任何移动前检查全部恢复位置。恢复不覆盖用户文件，恢复中断可重试，成功后禁止再次提交同一操作。已完成提交的重试核验确切隔离位置及回执后返回原结果。QUARANTINED、COMMIT_STARTED、RESTORING、RESTORED纳入隔离库存，部分执行source_removal_executed为null。

relocation_backups已识别经核验的源处置：含隔离文件的根在没有其他异常时返回QUARANTINED，并列出quarantined_files及对应操作、原相对路径、隔离路径、大小和哈希。原始清单不被改写，库存通过有证据的位置视图核验同一字节；未知文件及损坏继续报告。处置证据异常进入disposition_errors并阻止新副本回收候选。恢复后回到VERIFIED；反向迁移前仍需要先恢复隔离文件。后续需跨操作协调、永久删除及更多路径竞态/真实断电演练。当前验证仅使用临时消费项目，不清理真实项目。

### 迁移隔离副本永久删除计划

```sh
python3 app_store_creative.py cleanup plan-relocation-purge --repo /path/to/project \
  --id RELOCATION_QUARANTINE_OPERATION_ID
python3 app_store_creative.py cleanup verify-relocation-purge --repo /path/to/project \
  --id RELOCATION_PURGE_PLAN_ID
```

默认完成隔离后保留7日，quarantine-days必须为非负整数；不要为了腾空间缩短策略。计划只列出本操作源侧隔离文件及准备副本，绑定每个文件的大小、哈希、inode与父目录身份；元数据和未知文件不会列为待删项。每组媒体还绑定当前已登记、完整且独立的活动对象和artifact身份。

恢复已开始、永久删除意图已存在（包括断链意图）、未结事故及完整依赖、配置仍引用原路径/隔离路径、活动对象缺失或损坏、未知/未核验搬迁证据、保留根异常均拒绝规划。关闭已解决事故后可生成新计划。复查同一计划还绑定全部非维护生命周期记录、配置、搬迁库存和操作/准备/提交/隔离回执；新增引用、文件身份变化和路径篡改使旧计划失效。

该计划不能交给试制对象purge。计划生成后恢复仍可用，恢复一旦开始则原永久删除计划不可再执行。成功复查不是未来执行免重验的许可。删除执行、部分删除续执行及恢复停止边界如下。

### 执行永久删除与续执行

```sh
python3 app_store_creative.py cleanup purge-relocation --repo /path/to/project \
  --id RELOCATION_PURGE_PLAN_ID --actor OWNER --reason "Quarantine retention expired" --confirm PURGE
```

执行先核验原计划，在移除字节前同步purge-intent；开始后禁止同一隔离操作恢复。每个文件先同步purge-file-<index>检查点，再用已核验目录FD独占捕获到同父目录的.creative-purge-<plan-id>-<index>位置，核验确切身份后移除并同步父目录。不会递归删除目录，不移除业务记录、未知文件或当前活动对象。logical_bytes_removed为移除路径的逻辑字节，不能视为实际释放的物理容量。

原计划绑定全部受保护根的文件、inode与根身份。每一步重新核验计划/意图、引用、独立恢复对象和完整文件集合；引用中途变化、文件替换、未知内容或身份冲突立即停止后续删除。中断重试使用原计划ID；只有有匹配检查点的缺失文件才可当作已删除，另一份计划不能接管。捕获位置可继续处理，完成回执落盘中断也可重试。已完成重试检查回执、检查点、精确剩余文件及删除路径没有重现，再返回原结果；重新出现的文件保留并报告。

隔离库存phase/status显示PURGING或PURGED；源处置库存使用purged_files及PURGED/PARTIALLY_PURGED记录媒体处置，不将有完整删除证据的路径误报为丢失。原始清单继续保留。未知变化或缺少删除证据仍保持异常，不仅凭purge目录名猜测。永久删除后该隔离操作无法恢复；这不删除活动对象，后续反向迁移仍需要单独、显式的重建能力。跨操作协调、更多路径竞态及真实断电验收尚未完整完成。

## 执行租约与恢复

每次尝试都会创建有期限的租约，默认一小时。开始或续期返回lease_token；CLI登记产物、结束尝试及续期必须提供当前令牌。续期更换令牌，旧执行者不能再写入。令牌应留在本地执行上下文，不加入发布包或分享日志。

```sh
python3 app_store_creative.py attempt start --repo /path/to/project \
  --run-id RUN_ID --stage render --owner AGENT
python3 app_store_creative.py attempt renew --repo /path/to/project \
  --id ATTEMPT_ID --lease-token CURRENT_TOKEN
python3 app_store_creative.py attempt finish --repo /path/to/project \
  --id ATTEMPT_ID --status succeeded --lease-token CURRENT_TOKEN
python3 app_store_creative.py attempt recover --repo /path/to/project \
  --id EXPIRED_ATTEMPT_ID --owner REPLACEMENT_AGENT \
  --reason "Producer interrupted; restart from preserved inputs" --confirm RECOVER
```

实际CLI/Studio截图生产会在工作期间持续续期，结束前停止心跳。产物登记前后均检查租约，避免复制大文件期间过期后提交。租约过期仅表示写权限失效，不证明原进程已经退出，也不会终止原进程。

接管仅允许过期且尚未结束的尝试；原尝试追加interrupted结果，新的尝试带retry_of引用，不覆盖原工作目录。两个接管者并发时只有一个成功。活动尝试即使租约过期也不会直接进入清理；应先完成显式恢复或处置。

恢复入口目前建立重试身份与独立工作目录，尚未自动重放具体录制或剪辑执行器。原尝试失去有效租约后无法提交终止结果时，保留原错误并等待显式恢复，不伪造成功状态。

## 事故证据保护

发现播放、海报、来源或归档问题时，建立事故并明确引用artifact、candidate或delivery。允许引用暂时缺失或已隔离字节的已有记录，以保护恢复需要的身份；未登记ID会被拒绝。

```sh
python3 app_store_creative.py incident open --repo /path/to/project \
  --actor OWNER --reason "Poster verification failed" --artifact ARTIFACT_ID
python3 app_store_creative.py incident status --repo /path/to/project --id INCIDENT_ID
python3 app_store_creative.py incident close --repo /path/to/project \
  --id INCIDENT_ID --actor OWNER --resolution "Reproduced and replaced" --confirm CLOSE
```

未结事故保护物料与完整来源依赖；即使候选已弃用，也不能隔离或永久删除。事故建立后旧维护计划失效。关闭操作追加不可变处置记录，不能改写原原因，也不能二次关闭覆盖结果。关闭事故只释放该事故引用；其他候选、审批、交付及保留期限继续生效。

## Studio搬迁副本维护接口

Studio通过`/api/relocation-maintenance/`复用CLI使用的核心操作，不能直接对库存中的路径执行删除。

| 操作 | 请求字段 | 确认值 |
| --- | --- | --- |
| `plan` | `retention_days` | 无，生成独立计划 |
| `verify`、`verify-purge` | `id` | 无，只复查 |
| `plan-purge` | `id`、`quarantine_days` | 无，生成独立永久清理计划 |
| `prepare`、`resume`、`cancel`、`commit`、`restore`、`purge` | `id`、`actor`、`reason`、`confirm` | 对应操作的大写名称 |

接口拒绝额外字段、查询参数覆盖、空操作人或理由以及非整数保留期限。隔离提交前仍由核心重新检查来源、引用和独立恢复副本。6项HTTP测试已验证中断清理后重启恢复、替代计划拒绝、计划、准备、隔离、恢复、取消、注入部分复制中断及临时项目永久清理，证明活动物料仍可验证且残缺副本不会被覆盖。界面已接入计划、准备、记录复查、隔离提交、恢复、续执行和取消。临时项目浏览器已完成计划、明确审查、准备、隔离及恢复，保存状态依次为PREPARED、QUARANTINED、RESTORED且均VERIFIED；独立核验活动物料完整、原始副本恢复。证据为`/tmp/creative-copy-maintenance-browser-proof.json`及同名PNG。中断恢复与永久清理浏览器验收仍待完成。永久清理界面已接入独立计划、完整副本与恢复对象审查、默认未授权及准确PURGE确认。HTTP专项验证错误确认不删除、正确执行仅移除两类冗余副本，并保留活动恢复对象；永久清理计划浏览器审查已验证默认7天拒绝、测试0天计划完整清单，以及填写操作人/理由/PURGE但未授权时删除按钮仍禁用；证据`/tmp/creative-purge-review-browser-proof.json`及同名PNG。未点击最终删除按钮，浏览器最终执行仍待完成。真实进程中断已覆盖清理意图保存、单文件删除完成、终态回执写入之前三个阶段，全部能够通过公开CLI复用原计划恢复，活动物料和独立恢复对象保持完整。库存同时返回原始文件清单及与清理意图校验绑定的永久清理计划；Studio对PURGING提供重新核对原计划入口，不能创建替代计划，且每次恢复都重新要求明确授权。已完成清理记录在正向搬迁及反向返回后也保留原计划，不会因历史位置投影丢失审计合同。隔离与恢复另有六项真实进程中断测试通过。

## 普通对象永久清理回执

普通对象清理的意图绑定原计划和隔离操作的完整哈希，终态绑定清理意图哈希及准确移除字节数。恢复执行复查这些身份；重读已清理结果还逐对象检查待删位置是否依然缺失。文件重新出现、回执状态/容量改变、原计划或意图改变均拒绝成功结论，并保留现场文件及记录。每个待删对象另有不可变文件检查点，绑定准确计划哈希、完整对象及路径和文件身份。检查点保存前对象缺失会拒绝续执行；保存后同字节替换也会拒绝且保留现场。终态要求全部检查点存在。合同字段缺失直接拒绝，不补写历史字段。清理回执证明该操作保存的范围；全量操作日志仍是OBSERVED，不据此推断所有执行效果已核验。

## 永久清理后取回演练

`tests/test_post_purge_retrieval.py`使用封存截图的独立测试项目，完成四类目录搬迁、冗余副本隔离及永久清理，再通过公开`archive restore`入口从仍受保护的封存包恢复到空目录。恢复包清单验证通过，媒体与活动对象逐字节一致。再次恢复到同一目录必须拒绝，保留用户追加文件与已有媒体。这证明本地冗余副本清理不会破坏受保护交付的取回能力，不代表生产远端不可用后的灾难恢复或真实产品验收。

## 按操作核验执行结果

统一历史入口`history inspect-maintenance --repo /path/to/project --id OPERATION_ID`和只读HTTP`GET /api/history/maintenance/OPERATION_ID`复用同一核心。Studio历史列表可显式检查当前执行结果，展示准确操作ID、阶段、核验状态和错误；更换选择或请求写操作会清除旧核验结果。

普通隔离检查原清理计划/当前存储绑定、完整恢复对象及活动位置缺失；恢复检查活动对象完整性；永久清理检查完整回执绑定和全部待删位置缺失。搬迁副本复用已有身份、内容和历史位置投影检查。返回PASS、FAIL、INCOMPLETE、NOT_EXECUTED或UNKNOWN；只有当前作用域PASS才返回execution_verified=true。计划本身不证明后续执行。检查持读锁，不改写记录、不补写旧格式、不授权后续操作、不自动恢复。该入口不覆盖全部搬迁和封锁执行效果，全量日志仍为OBSERVED。

## 响应丢失后的检查顺序

1. 保留原操作ID和现场文件，先读取对应历史；不根据请求失败推断操作未执行。
2. 使用 `history inspect-maintenance` 检查该维护操作的实际文件效果。日志列表的 OBSERVED 与效果核验的 PASS 分开解释。
3. FAIL 或 UNKNOWN 时检查错误、缺失证据和路径身份，保持现场；不能将其转成新的删除授权。
4. INCOMPLETE 时进入该操作已有的恢复或续执行入口。永久删除开始后不能转为恢复；按原计划续执行，不另建计划隐藏部分执行。
5. PASS 只证明本次核验范围。再次写操作仍重新检查引用、配置、策略及文件身份；正式归档、远端可用性和 ASC 各自验收。

## 当前边界

已登记的 diagnostic 产物采用项目诊断保留策略；未登记日志的自动分类与回收、执行器自动重放及完整并发恢复尚未实现。目录relocate及专用中断恢复已接入，完整历史位置投影、全部父路径竞态及真实断电验收仍未完成。库存已区分已登记、改变和未知工作文件；库存报告不能直接用作删除清单。正式归档和已有批准物料保持保护；归档缓存回收需要后续远端取回证据机制。

维护成功只说明本地操作完成，不表示ASC上传、视频播放或海报复查通过。

## 项目保留策略配置

项目共享配置可声明`artifactPolicy`，必需`schema_version: 1`，支持非负整数`trialRetentionDays`、`diagnosticRetentionDays`、`quarantineDays`及`mediaBudgetBytes`。未知版本、未知字段、布尔值和负数直接拒绝，不升级旧策略。未声明策略时选择新合同当前默认值：试制30天、诊断14天、隔离7天，预算未配置。

普通对象`cleanup plan`未提供retention-days时读取项目trialRetentionDays；显式参数形成本次计划的retention_days。普通试制清理、搬迁副本保留、普通及搬迁副本永久清理均在省略参数时读取项目策略；CLI不再覆盖为固定默认值。普通清理/永久清理计划保存解析后的artifact_policy，执行和续执行时拒绝策略变化。显式参数仍为本次操作的选择并保留在计划中。Studio通过storage artifact-policy同源的只读接口读取策略，三个维护界面用显式Use project retention settings入口读取天数并清除旧审查状态；未读取时不填猜测默认值，可显式填写本次天数。显式role=diagnostic的登记产物按diagnosticRetentionDays计算完成尝试后的保留期，其余产物按试制期限计算；引用保护、依赖闭包和同字节别名保护优先于期限。计划固定观察时间，隔离与永久清理复核同一策略，不会因重试推进截止时间。未登记的日志不会自动分类或清理。媒体预算通过只读报告提示风险，不执行清理。


媒体预算通过`storage media-budget`及GET `/api/storage/media-budget`读取；可提供candidate-id估算再封存一个修订。Studio提供独立检查入口。报告累计已登记且完整验证的本机归档修订中实际物化的产物载荷，包括选用媒体、输入和渲染证据；不同修订的副本分别计数，排除元数据，不推断实际磁盘块占用。缺失或损坏归档使总量与预计总量保持UNKNOWN，已观察量仅是下界。Git历史及远端占用保持未知。预算未配置、超预算和范围内是不同结果；报告不自动清理，也不证明远端成本或完整容量策略已经验收。
