# 存储目录搬迁

目录搬迁保持物料身份、业务记录和源字节。当前支持计划、准备、正式切换及中断后的向前恢复/回滚，源数据不自动删除。PREPARED不等于搬迁完成。已激活目标支持独立反向计划、准备、切换及显式续执行；反向中断撤回及重复访问同一存储根已接入；备份维护、完整路径竞态及进程中断及文件系统错误恢复验收仍待完成。

## 保存前的只读目录预览

完整配置草稿可以通过以下入口检查，不保存草稿、不创建目录或维护记录：

```sh
python3 app_store_creative.py storage preview --repo /path/to/project \
  --draft draft-creative.config.json
```

Studio HTTP提供 `POST /api/storage/preview`，正文为 `{"config": <完整配置草稿>}`；CLI、HTTP与agent调用同一用例。草稿路径和目录配置都按消费项目根解析，不受调用目录影响。HTTP沿用本地来源、请求大小和JSON输入边界。

结果包含binding及四类roots：configured是项目配置的显式值，source区分project、default和派生对象目录derived，resolved是最终绝对路径。省略objectRoot时位于有效workspaceRoot的objects子目录。根重叠、相对逃逸及无效字段使用现有路径合同拒绝。

roots_changed比较当前保存配置和草稿的存储绑定；已有受管理owner时，改变绑定返回requires_relocation=true，不能通过普通保存替代迁移。受管理项目ID改变单独报告project_identity_conflict。归属记录冲突或不安全链接直接拒绝，不虚报可保存。预览不检查全部操作租约、迁移门禁或目标写入权限，也不授权写入；实际保存和迁移仍独立即时复查。

Studio的Output directories面板已支持四类项目目录编辑、留空恢复默认和显式Preview directories检查。修改草稿会清除旧结果，失败显示具体原因；预览展示最终绝对路径及默认/项目/派生来源。Save project及创建/导出之前的共用保存流程重新调用预览，用当前响应拒绝迁移要求或项目身份冲突，再由条件保存接口即时复查。较旧请求不能覆盖新草稿的预览结果。项目已有物料时需要使用显式迁移流程，界面不移动或删除物料。

项目与受保护本机配置已接入统一解析器。本机storage覆盖共享storage，搬迁计划绑定实际拥有层的完整文档、身份及另一层证据；切换只替换拥有层。本机配置必须被实际Git规则忽略且未跟踪，命名外部后端访问配置随拥有层保留，不进入便携配方。共享配置优先使用项目相对路径。

## 计划与复查

target-storage.json声明新的完整storage配置；省略项使用同一配置解析器的默认值。相对路径相对消费项目根，项目外位置需要显式绝对路径及宿主权限。

```json
{
  "workspaceRoot": "creative-work",
  "objectRoot": "creative-objects",
  "releaseRoot": "creative-releases",
  "publicationRoot": "creative-publications"
}
```

```sh
python3 app_store_creative.py storage plan-relocate --repo /path/to/project \
  --storage target-storage.json
python3 app_store_creative.py storage verify-relocate --repo /path/to/project \
  --id RELOCATION_PLAN_ID
```

计划绑定当前配置及其文件字节、源与目标根、每个源文件的SHA256及大小。现有正向计划新增configuration_change，记录共享文件原文/哈希/身份、邻接本机文件不存在状态及精确目标配置变更。复查、准备和切换前重新解析来源；本机文件出现、共享文件同字节替换或变更提案被编辑都会拒绝旧计划，不能仅凭共享JSON的内容哈希继续。嵌套对象库单独列出，不在workspace清单中重复。已有交付包必须通过完整性校验，已登记对象和隔离证据不得缺失或损坏。

仍有未结束尝试时拒绝计划，不以租约过期推断原进程退出。符号链接不跟随、不复制。目标根不得覆盖已有目录；移动目标不得位于需要复制的源根内部。仅移动对象库且工作根保留时，可以使用该工作根内的新空位置。

源文件或配置变化后旧计划失效，需要重新生成；READY只说明当前复查满足计划，不执行复制或切换。

维护操作尚未结束时也拒绝迁移计划及复查，包括未取消的隔离准备、未恢复的隔离提交和部分永久删除。开始复制前再次检查该门禁。通过维护流程完成取消、恢复或删除并核验终态后，才允许重新规划；取消准备保留全部字节，不自动回收空间。命令与限制见artifact-maintenance.md。历史维护记录可通过已验证的位置绑定链参与后续规划，历史隔离准备区库存已接入迁移回执绑定的位置证明；完整保留副本位置投影及中断期间的身份检查仍待验收。

## Git暂存门禁

```sh
python3 app_store_creative.py storage relocation-git-policy --repo /path/to/project \
  --id RELOCATION_PLAN_ID
```

该入口按真实Git仓库位置返回精确暂存路径、对应.gitignore文件位置及建议规则，不修改规则或索引。多个目标属于不同仓库时，分别审查repositories中的规则；不能把一份规则只写进源仓库就认为所有目标已受保护。

prepare-relocate在复制前读取实际Git忽略及索引状态。未被忽略、被反向规则取消忽略、仍有已跟踪条目或Git状态无法确认时拒绝复制。已完成准备的重试也重新检查当前规则。无Git仓库的普通本地位置无需伪造忽略规则。

存储路径允许空格和Unicode，但拒绝换行、制表符及其他控制字符，避免生成多行或含歧义的规则。现有用户规则保持不变；规则合入仍由项目维护流程审查执行。

## 复制准备

```sh
python3 app_store_creative.py storage prepare-relocate --repo /path/to/project \
  --id RELOCATION_PLAN_ID --actor OWNER --reason "Move managed local storage" --confirm PREPARE
```

准备操作先记录意图及专属暂存位置，再创建暂存目录。按目标根层级分组复制，目标文件使用排他创建，拒绝覆盖检查后出现的内容；文件完成写入并同步后逐项校验；复制完成后再次检查源计划和全部暂存文件。重复调用验证已有PREPARED结果，不覆盖暂存内容。发现篡改、额外文件、路径变化或复制错误则拒绝准备并保留失败记录。

暂存目录在目标根的父目录中，名称由操作ID确定。如果父目录位于Git工作树，实际忽略和索引门禁必须通过，不应把暂存内容stage或commit。未知普通文件随完整源目录的快照列入计划供审查，不被重新登记成正式物料；未知符号链接阻止搬迁。准备不会删除源文件，不创建最终目标根，不改变配置及已有存储绑定。

## 准备失败恢复与取消

```sh
python3 app_store_creative.py storage recover-relocate --repo /path/to/project \
  --id RELOCATION_PLAN_ID --actor OWNER --reason "Retry failed preparation" --confirm RECOVER
python3 app_store_creative.py storage cancel-relocate --repo /path/to/project \
  --id RELOCATION_PLAN_ID --actor OWNER --reason "Keep current storage" --confirm CANCEL
```

恢复先复查原计划，源数据或配置改变时拒绝。成功返回关联的新retry_plan_id，保留原失败暂存；新批次需要重新审查Git规则并执行准备。重复恢复返回同一关联批次。

取消先验证所有现存暂存根的所有权标记及实际Git状态，再清理清单中大小与哈希匹配的文件。未知、被修改或链接内容保留并报告CANCELLED_PARTIAL；缺失所有权标记时拒绝删除。取消不会触及源文件或配置，已取消计划不能继续准备。

## 历史位置绑定解析

内核通过不可变storage-bindings记录解析历史位置。每一步绑定源位置的规范化哈希，并核对对应SWITCHED回执的完整哈希、源与目标、项目身份和配置路径；缺失、篡改或循环链拒绝使用。旧run记录不重写，读取时通过链确认是否到达当前根。

正式切换会生成并安装位置链与回执；不能手工写入绑定文件替代搬迁验收。归档本机定位、源写入封锁和中断恢复已接入该事务。

## 当前未完成边界

可恢复切换、位置绑定链、原位置写入封锁及中断回滚已接入公开CLI。剩余验收包括完整路径替换和跨文件系统矩阵、重复搬迁后的维护闭环、Studio搬迁操作及真实产品工作流；当前局部验收不能支持整体完成。

归档位置改变还需要保持原Git归档提交的取回定位，不能把本机路径变更当作新媒体批准。源目录最终清理是单独授权维护，普通搬迁不会自动删除源数据。

## 归档本机位置与Git位置

交付记录保存封存时的storage及local_path；读取时先验证位置链，再按原归档根中的相对位置定位当前包，并验证manifest_sha256。发布计划使用原Git提交中的归档路径，上传审批、交接导出和远端状态复查均按计划的archive_path验证Git字节，不把搬迁后的本机路径当作新的提交路径。位置改变不改写交付记录、清单或设计批准。

普通Git模式验证准确提交中的归档路径；external模式已支持便携元数据导出、版本化媒体保存及独立Git取回后的完整包恢复，使用命名本机后端解析访问位置。临时配置远端的Git/LFS/external演练不证明生产持久后端或实际上传完成，详见artifact-operations.md。

## 切换前写入封锁合同

统一事务入口在获取源工作区锁后检查该存储绑定的不可变storage-fences记录。安装封锁前必须复查计划、Git门禁和全部已准备副本；随后旧绑定的新run、维护写入及准备重试均拒绝，独立CLI进程也受同一检查约束。封锁不会把读操作报告成搬迁成功。

封锁由正式切换事务安装，中断回滚通过绑定证据解除；没有独立安装或删除封锁命令。不能手工修改记录代替恢复。

## 目标启用与对象库归属

目标绑定带有storage-activations记录时，统一事务核对指定SWITCHED回执的完整哈希、目标根、项目及配置权限范围。回执缺失或不匹配时禁止新run和清理；正式事务安装待启用记录，并在全部步骤完成后生成回执。

对象库_owner.json保存首次归属的项目身份和完整存储绑定；后续写入通过已验证位置链确认当前归属。工作区搬迁不改写该记录，无位置链的其他工作区仍拒绝共享对象库。该设计仍限定单项目本地后端。

## 内部切换事务

内部switch_relocation串联准备复查、源写入封锁、证据转移、目标待启用、目录排他发布、逐项字节复查、配置原子替换、位置链及最终SWITCHED回执。切换意图保留原配置精确字节和文件权限，用于后续恢复。源数据始终保留；仅移动对象库也经过同一事务。

5项测试覆盖成功后旧run读取及新run写入、配置替换失败后的双端保护、准备副本篡改、工作根保留时对象库移动、已有批准与归档继续封存。切换通过switch-relocate开放，中断通过显式原工作区恢复。

## 中断切换回滚

rollback_relocation使用原工作区锁及计划权限范围，校验原配置备份哈希、当前配置和完整源快照。当前配置只允许为原始字节或本次目标字节，用户的其他编辑不会被覆盖。恢复原配置后追加ROLLED_BACK回执和精确绑定该回执与封锁哈希的解除记录；不删除源、目标或暂存副本。封锁按批次追加，回滚不移除历史记录。

5项测试覆盖配置替换失败、配置已切换但位置链未完成、部分目录发布、源被修改和用户配置编辑。目标一旦生成SWITCHED回执，此入口拒绝回滚，后续需单独的反向搬迁及目标写入冻结。已激活目标使用下述独立反向迁移流程，残留副本维护仍未完成。

## 中断切换向前恢复

resume_relocation在原工作区锁下复查源快照、配置、封锁和本批次标记；分别识别已经发布的根和剩余暂存根。清单中的副本与操作证据逐项验证，未知文件、链接、冲突根和配置编辑均拒绝续执行，不删除或覆盖它们。剩余根以排他方式发布，最后完成配置、位置链和原切换回执；已回滚批次禁止向前恢复，重复完成请求返回同一回执。

恢复通过resume-relocate/rollback-relocate开放，并显式校验原位置上下文。反向迁移使用独立入口，整体端到端验收仍未完成。

目标启用前窗口：工作区保留时，即使storage-activations尚未安装，事务也会检查本工作区的switch-intent目标绑定；匹配的待切换目标拒绝写入。缺失启用元数据不会被当作普通新配置放行。该检查不替代跨工作区及父目录竞态验收。

## 中断恢复CLI

```sh
python3 app_store_creative.py storage resume-relocate --repo /path/to/project \
  --source-workspace /path/to/original/workspace --id RELOCATION_PLAN_ID \
  --actor OWNER --reason "Resume interrupted switch" --confirm RESUME
python3 app_store_creative.py storage rollback-relocate --repo /path/to/project \
  --source-workspace /path/to/original/workspace --id RELOCATION_PLAN_ID \
  --actor OWNER --reason "Rollback interrupted switch" --confirm ROLLBACK
```

恢复必须显式指定原工作区；相对路径相对项目根。入口在任何写入前验证真实路径、原配置备份哈希、完整配置身份、计划原绑定、项目所有权及配置权限范围，不从已改变的当前配置猜测原工作区。恢复命令不解除已激活目标，也不删除残留副本。

跨进程边界验收：独立目标客户端在根已发布、配置提交前被拒绝；独立源客户端等待源锁后被封锁。统一事务另在创建工作区前及获取锁后比对权威配置的存储绑定，阻止未生效目标配置提前创建目录。这两项测试不覆盖所有文件系统父目录替换竞态。

## 正式切换CLI

```sh
python3 app_store_creative.py storage switch-relocate --repo /path/to/project \
  --id RELOCATION_PLAN_ID --actor OWNER --reason "Switch verified storage" --confirm SWITCH
```

先完成计划、Git规则审查及准备，再切换；切换期间禁止生产及维护。失败后保留现场，通过显式原工作区选择续执行或回滚；SWITCHED之后不使用中断回滚命令撤销。源数据最终处置属于独立维护授权。


## 配置替换的持久化顺序

正式切换、回滚与续执行在临时配置文件fsync和原子替换后，对配置父目录执行fsync，再继续写入位置绑定或解除封锁回执。目录同步失败时操作仍按中断处理，保留源与目标数据供恢复。测试验证替换和登记之间的同步顺序；进程退出后的恢复及相关路径替换场景仍需独立验收。

恢复流程不能以配置字节已相同推断目录同步成功。配置替换后fsync失败时，续执行和回滚均会再次同步父目录；失败保持目标未激活或源封锁，存储恢复后才允许提交相应回执。

## 只读迁移状态

```sh
python3 <runtime-root>/scripts/app_store_creative.py storage status-relocate --repo <project-root> --id <relocation-id>
```

返回操作阶段、当前存储绑定、激活和写入封锁检查结果及恢复方式；查询不写入记录，源存储已封锁时仍可读取。已切换状态要求独立反向迁移；本命令不实现撤回，也不验证所有媒体字节。中断后配置已指向目标时，从原工作根执行恢复仍按前述 source-workspace 流程；不从状态字符串推断切换可安全重试。

已切换操作另报 target_activation_status：VERIFIED 表示目标配置哈希、存储绑定、激活记录和源/目标切换回执一致；缺失、损坏、链接或不一致返回 FAIL 和原因。历史操作阶段仍可为 SWITCHED，这不表示目标当前可用。查询不会创建缺失目标；激活校验不等于媒体字节校验，也不证明目标仍是后续迁移后的当前写入位置。

## 已激活目标的反向计划

在当前有效存储上执行：

```sh
python3 <runtime-root>/scripts/app_store_creative.py storage plan-reverse-relocate --repo <project-root> --id <activated-relocation-id>
python3 <runtime-root>/scripts/app_store_creative.py storage verify-reverse-relocate --repo <project-root> --id <reverse-plan-id>
```

计划可引用当前已激活的正向或反向操作，绑定当前配置及完整运行、对象、归档和发布记录快照，并核对其激活证据。待恢复的原根必须仍符合该操作开始前的快照，原封锁回执必须与复制证据一致，并绑定相同项目、操作、配置路径和准备清单哈希；新增未知文件、修改、缺失或符号链接阻止计划。未移动的根不按旧快照回退，当前新增记录继续保留。复查发现配置或当前数据改变时要求重新计划。

计划复查通过后，可执行独立准备命令：

```sh
python3 <runtime-root>/scripts/app_store_creative.py storage relocation-git-policy --repo <project-root> --id <reverse-plan-id>
python3 <runtime-root>/scripts/app_store_creative.py storage prepare-reverse-relocate --repo <project-root> --id <reverse-plan-id> --actor <human> --reason <reason> --confirm PREPARE
python3 <runtime-root>/scripts/app_store_creative.py storage status-relocate --repo <project-root> --id <reverse-plan-id>
```

先审查并落实暂存目录的 Git 忽略规则。准备复制当前数据到独立暂存目录并核对每个文件哈希，不覆盖原根、不解除原封锁、不切换配置。重复准备校验已暂存数据，损坏时拒绝。已登记的前次迁移归属标记按控制信息处理，未知同名文件不会静默丢弃。

READY/PREPARED 都不表示反向迁移已经执行或完成；正向 switch 命令拒绝反向计划。正式反向切换与续执行使用下述独立入口。

### 反向准备失败与取消

准备失败用 `recover-relocate` 创建新反向计划，再执行 `prepare-reverse-relocate`；旧暂存及未知文件保留，失败记录不覆盖。按需用 `cancel-relocate` 取消，清理仍限定为已证明归属且字节未改变的暂存文件。返回 CANCELLED_PARTIAL 时查看 `status-relocate` 的 retained_paths，逐项人工处理；部分取消不表示全部暂存已删除。准备阶段的恢复不会撤回已激活的正向迁移。

反向计划及准备记录还绑定原根和暂存根的设备号/inode；相同字节的目录替换也会使复查失败。原先未创建的归档或发布根绑定为缺失，后续需要排他发布；已有根使用原子交换。准备记录 exchange_roots 明确各根的 EXCHANGE/PUBLISH 操作，尚不代表这些操作已执行。

### 反向切换与显式续执行

```sh
python3 <runtime-root>/scripts/app_store_creative.py storage switch-reverse-relocate --repo <project-root> --id <reverse-plan-id> --actor <human> --reason <reason> --confirm SWITCH
python3 <runtime-root>/scripts/app_store_creative.py storage resume-reverse-relocate --repo <project-root> --id <reverse-plan-id> --source-workspace <active-workspace-before-reverse> --actor <human> --reason <reason> --confirm RESUME
```

切换前保存反向操作开始时的工作根路径，用于配置已改变后的恢复。持久意图先于封锁及目录改动；随后按目录身份交换原根或排他发布缺失根，验证字节，更新位置绑定及配置，并完成目录同步后激活。旧有效存储继续封锁，原副本在回执 preserved_backups 指定的路径保留，不自动删除。

中断记录保留首个原因，状态显示 SWITCH_INTERRUPTED。目录交换完成但后续同步失败时，续执行识别已经交换的身份，只继续核验和同步，不把两份目录再次换回。配置同步失败保持目标不可写；恢复完成后才提交激活回执。封锁摘要尚未写入时可以核对已登记封锁后补齐，原数据改变仍拒绝恢复。完成后的重复恢复核对回执，保持只读。

真实临时工作区已覆盖全根返回、对象库单独返回、新增产物保留、交换后中断、意图/封锁摘要中断及配置同步失败，CLI 用真实子进程验证。反向中断撤回使用下述入口；重复访问同一根的回归见下文，进程退出和相关路径替换演练尚未完成；不能手动改配置代替恢复，也不能把备份路径交给普通暂存取消流程。

恢复在任何写入前重新核对意图的目标配置哈希及存储绑定、源配置备份、切换回执和控制证据是否与计划一致。被修改的目标配置不能引导恢复到未批准目录；不以记录文件名或相互引用代替范围核验。

### 反向切换中断后的撤回

```sh
python3 <runtime-root>/scripts/app_store_creative.py storage rollback-reverse-relocate --repo <project-root> --id <reverse-plan-id> --source-workspace <active-workspace-before-reverse> --actor <human> --reason <reason> --confirm ROLLBACK
```

仅处理尚未激活的反向切换。回滚先核对源数据、目录身份、备份字节和配置编辑情况，再持久化撤回意图；恢复目录位置后，保留新的暂存副本，恢复反向操作开始前的配置字节及权限，完成配置同步后才解除源封锁。共享工作根的待激活视图先保存在操作的 retired-controls 中，再按已验证日志恢复原视图；原计划不存在的视图才可移除。位置视图更新前后的历史与所有物料均保留。

开始回滚后只能继续同一回滚，不能改为向前续执行。目录恢复后的同步失败可以重试，不会把目录再次迁出。原备份或用户配置被修改时拒绝撤回并保留现场；已激活目标也拒绝中断回滚，且不为成功操作补写虚假中断记录。正向 resume/rollback 命令拒绝反向计划，避免跳过目录恢复。

回执 ROLLED_BACK 与源可写检查一起作为结果证据；preserved_staging 记录保留的新副本。此入口不授权删除备份、暂存或未知文件，也不替代进程中断及文件系统错误恢复验收。


## 重复目录切换的实施边界

A → B → A 后再次迁至新的 C 的固定位置索引冲突已修复。正向及反向切换、续执行及中断回滚共用位置视图更新模块：绑定计划中的精确旧值、已验证旧回执和新回执，将旧值/目标值先保存至操作专属不可变日志，再更新当前视图。重复迁移后旧运行、旧物料及历史目录绑定仍可读取；原业务记录保持不可变。

共用工作区的中断回滚会恢复原位置视图；原计划中不存在的视图，只能在验证本操作日志和精确目标值后移除，保留日志及全部物料。配置同步成功后才允许记录回滚完成并释放源封锁。外部修改或意图旧值不符合计划时拒绝覆盖。

实际回归覆盖 A → B → A → C → A，以及 A → B → A → B → A → B 的连续反向往返；完整目录和共用工作区的对象库迁移均可保留所有运行及物料。配置同步中断、索引替换后的中断续执行、旧视图恢复及意图/当前激活视图/原封锁项目范围篡改拒绝也有回归。备份保留与回收、父目录替换场景及进程退出恢复仍待完整验收；这些临时工作区测试不替代两个真实产品的端到端验收。


## 隔离副本在中断恢复中的身份核验

正向续执行根据各根实际位于暂存区还是最终目录定位工作区，复查迁移准备回执绑定的隔离根及逐文件身份，再继续控制记录、目录发布和配置切换。反向续执行及中断回滚使用交换日志定位当前副本，同样复查准备证据。哈希相同但inode变化也拒绝，新增未知文件保留并阻止续执行。

反向迁移还在切换前记录旧目的目录中隔离树及子根的实际身份，将证明摘要绑定到切换回执。恢复/回滚先检查已保留或尚未交换的备份位置，再进行进一步交换；不能只验证新活动副本而漏掉旧备份。完整字节、目录/文件身份及配置保持匹配时可继续，拒绝后配置及未知数据保持原样。

这些门禁已覆盖进程级中断模拟；进程退出恢复、父路径替换场景、跨文件系统及完整保留副本库存投影仍需验收。正向中断回滚只恢复源配置及写权限，保留目标字节；本门禁不把目标自动删除作为回滚成功条件。


## 配置层变化与反向恢复门禁

反向计划同样记录configuration_change：审核当前活动配置的原文、身份和本机缺省状态，绑定返回原根所需的精确目标更新。复查、准备和交换前通过完整证据比较拒绝层变化；即使共享文件字节相同，inode替换也使旧计划失效。目标提案路径不能经编辑绕过归属。

正反向中断续执行及回滚会在进一步写入、交换或配置覆盖前复查邻接本机文件是否新出现。发现未审核本机层时保留现场并拒绝，不自行删除该文件或把它静默忽略。恢复需要先核对原证据与当前配置，明确恢复已审核配置层状态后再使用原操作ID；该要求不能用作清理用户文件的授权。恢复时原共享文件可处于日志允许的源/目标状态，不错误要求原inode跨原子配置提交保持不变。

这些配置层保护已接入实际拥有层的正反向写入及安装后恢复。切换只替换拥有层文档，并复查另一层的身份及原文；不是同时改写两份配置。完整中断场景仍须按交付审计验收。当前临时工作区回归覆盖交换或配置提交中断、新本机文件拒绝、现场保留以及恢复已审核缺省状态后继续原操作；不代表进程退出恢复或全部父路径竞态已完成。


## 进程中断验收证据

`tests/test_relocation_process_crash.py`在独立测试子进程中执行正向/反向切换，在意图保存、目录发布、配置安装和切换回执写入前发送SIGKILL。父进程通过公开CLI定位源工作区，分别续执行或回滚；17项矩阵通过，包含源数据变化时拒绝补齐缺失封锁。原物料和新增运行可读，回滚恢复原配置字节。操作仅涉及临时测试项目，不终止用户应用或其他进程。正向意图与封锁之间的恢复窗口已修复：补齐封锁前必须重新验证原计划、源目录及暂存副本。该证据不等于全部中断点、硬件断电或跨文件系统验证。

`tests/test_relocation_preparation_process_crash.py`另外覆盖准备意图保存后及第一份文件复制后的真实进程终止。公开recover-relocate创建新批次，再通过prepare/switch完成搬迁；失败批次已有文件逐字节保留，不复用或覆盖中断目录。两项通过，源物料在新位置仍可验证。

## Studio状态查询

Storage relocation面板接受已保存的计划ID，调用只读GET /api/storage/relocation-status?id=ID。HTTP只接受一个id，不接受源工作区或其他路径覆盖。面板分开展示操作阶段、当前绑定可写性、目标启用、恢复方式及检查错误；媒体完整性明确保持未由此查询验证。修改ID清除旧结果，失败不保留之前的成功状态。另有Plan storage relocation面板接入正向计划、复查、复制准备及正式切换，展示四类源/目标、逐文件根/路径/哈希和容量。准备与切换分别要求操作者、原因、勾选审查及准确输入PREPARE/SWITCH；任何写请求失败都停止后续写入，先查询操作状态并解决中断。请求切换前项目保存/导出的共享保存入口即停止接受旧页面请求，响应丢失也不会解除该限制；检查状态后重新加载Studio才可继续。已有并发请求仍由服务端配置版本与事务门禁复查。反向及中断恢复写操作尚未接入界面。

HTTP专项验证PREPARED结果与内核一致、未知路径参数及重复ID拒绝、查询前后记录字节不变。该验证不代替Studio浏览器交互验收或真实搬迁演练。

正向HTTP全链路专项验证计划、READY复查、错误确认拒绝、PREPARED配置不变及SWITCHED后新位置媒体可验证、源字节保留。此结果来自临时消费项目，不表示浏览器验收或真实产品搬迁完成。

界面读取搬迁计划时核对完整四类目录、每个文件根/相对路径/哈希/大小、唯一文件身份及总容量一致性。无效或不完整响应不作为可审查执行计划；专项回归包含缺项、重复路径、路径越界和容量错误。

## 正向Studio浏览器验收

独立临时消费项目在真实浏览器完成四类目录计划、READY复查、PREPARED复制及SWITCHED切换。未勾选审查时准备按钮禁用，每次执行清除确认；切换后旧页面Save project被拒绝，重载得到四类新目录，按同一计划ID读取SWITCHED及VERIFIED目标启用。独立内核从新配置再次验证原测试产物。证据保存在/tmp/creative-relocation-browser-proof.json及截图/tmp/creative-relocation-browser-proof.png；临时页面与服务器已关闭。本验收不涉及真实项目、跨文件系统、反向操作或并发写入。

## Studio中断恢复入口

Recover interrupted relocation面板要求计划ID、切换前保存的原工作区、正向/反向与续执行/回滚方向、操作者和原因。勾选审查且准确输入RESUME/ROLLBACK后才可执行。HTTP与公开CLI共用recovery_source权限范围核验，不从当前配置猜测原工作区；错误源目录、额外字段及错误确认拒绝。

恢复请求前停止本页面共享保存/导出，执行后面板保持停止状态，先核对保存的操作状态，再重新加载项目。失败不自动重试，也不允许通过手改目录或配置解除限制。正向中断回滚HTTP专项通过，错误源位置拒绝、原配置及源写权限恢复；反向恢复HTTP与浏览器交互尚待独立验收。

## Studio反向计划

Plan storage relocation面板的Activated relocation ID to reverse要求已激活操作ID，Create reverse relocation plan调用独立反向计划。该计划共用完整目录/逐文件审查，不根据输入路径猜测旧位置。准备、复查和切换根据返回计划operation调用对应反向入口，仍使用独立PREPARE/SWITCH确认及旧页面保存保护。

反向HTTP全链路专项完成正向切换、登记新增测试产物、独立反向计划/复查/准备/切换；返回原根后原产物与新增产物均可验证。4项Studio搬迁HTTP测试通过。反向界面浏览器验收、反向中断恢复HTTP矩阵和其他异常输入仍待完成。

反向Studio真实浏览器验收已完成独立计划、READY复查、PREPARED复制、SWITCHED切换及重载原配置。同一反向ID查询目标启用VERIFIED；独立内核核验原测试产物通过。证据/tmp/creative-reverse-browser-proof.json及/tmp/creative-reverse-browser-proof.png。该演练没有新增真实产品物料，不代替中断恢复或跨文件系统验收。

反向中断恢复HTTP验收在目录交换后注入错误，再分别从显式原工作区续执行和回滚。错误的正向接口拒绝反向计划；对应反向接口恢复成功，原产物与新增运行可读且新运行可写。回滚恢复切换前配置原文。2项专项通过，不替代真实进程中断矩阵或浏览器恢复交互。

Studio中断续执行真实浏览器验收：独立测试项目注入配置提交错误，查询显示SWITCH_INTERRUPTED/不可写；明确原工作区、RESUME及勾选审查后恢复至SWITCHED/目标启用VERIFIED。旧页面保存被拒绝，独立新配置媒体核验通过。证据/tmp/creative-recovery-browser-proof.json及截图。该场景是错误注入，不称为真实进程崩溃；回滚和反向恢复浏览器仍待验收。

Studio正向中断回滚真实浏览器验收：选择明确回滚方向、原工作区及ROLLBACK确认，返回ROLLED_BACK/源可写/目标未启用。独立核验原配置字节、原产物、新运行写入及目标副本保留。证据/tmp/creative-rollback-browser-proof.json及截图。配置错误注入不称为真实进程崩溃；反向恢复浏览器仍待验收。

## 真实跨文件系统验收证据

2026-10-07使用独立临时APFS映像验收，源与目标st_dev分别为16777234、16777247。正向搬迁后活动物料核验、冗余副本隔离及恢复通过；另一独立试制完成跨文件系统正向后新增物料、反向返回原绑定、两份物料核验及新增运行。证据`/tmp/creative-crossfs-proof.json`和`/tmp/creative-crossfs-reverse-proof.json`。两次测试后均卸载临时卷。该证据不覆盖权限失败、路径替换及跨文件系统进程中断矩阵。

## 搬迁复制对象的独立核验

`storage inspect-relocated-objects --id PLAN_ID`、只读GET `/api/storage/relocated-objects?id=PLAN_ID`及Studio的Check copied object integrity复用同一核心。查询验证原计划与切换意图哈希、目标激活、目标计划一致性，并在目标读锁下核对计划中对象文件的准确路径、容量及SHA-256。目标没有已建立的读锁时返回UNKNOWN，不创建锁或修改目录。

结果仅覆盖本次计划复制的对象文件；新增媒体、归档、所有历史执行及后续维护效果不在该结论内。已激活目标中对象损坏返回FAIL；未切换操作为INCOMPLETE；空检查范围不返回PASS。明确维护后对象不再存在会使原复制范围检查失败，应结合维护记录解释，不撤销原搬迁回执。该查询独立于状态接口的目标激活门禁，不替换全部搬迁执行核验。

目标激活的只读复查同时核对switch-intent中的plan_sha256与当前计划，以及意图中的receipt与源端switched回执；任一改变均报告FAIL，不凭目标激活标记跳过绑定核验。这仍只证明该激活证据范围，不能替代物料字节核验或全部封锁执行核验。

源端写入门禁同时检查从当前绑定切出的switch-intent；若对应storage-fence缺失，普通写入仍拒绝并要求搬迁恢复。封锁文件缺失不构成重新启用旧位置的授权。该约束也在只读status-relocate中反映，不会自动补写封锁。

目标激活复查重算storage_controls的before/after范围，并将目标实际storage-activations和storage-bindings逐项与意图绑定的after记录比较。改变日志或实际发布绑定均为FAIL。此处核验当前切换关联的两类控制记录，不把全部控制日志观察升级为全局execution_verified。

已完成正向resume-relocate及反向resume-reverse-relocate的幂等读取仍复查目标激活及关联控制记录；即使switched回执字节正确，目标控制损坏也拒绝返回成功。不会静默修补或覆盖损坏记录。

真实操作系统写入权限验收使用独立临时目的父目录chmod撤销写入：prepare失败登记PREPARATION_FAILED，源物料和配置不变；恢复权限后recover生成新计划，完成prepare/switch，原批次prepare-intent保持不变。该证据仅覆盖暂存创建权限，不代替配置安装、恢复及跨文件系统的其余权限验收。

配置父目录无写入权限时，配置暂存创建失败发生在switch-intent及源端封锁之前；配置和源物料不变。配置准备意图包含父目录权限模式，恢复权限后旧意图仍拒绝，不能放宽身份检查以强行重试。确认切换尚未开始后使用cancel-relocate，再建立新plan并prepare/switch；临时项目已验证这条恢复路径。若已有switch-intent，则按resume/rollback恢复，不能使用取消准备。

## 独立卷中断矩阵

已挂载且由验收人员拥有的独立测试卷可用于同一公开CLI恢复矩阵；每个用例创建独立临时目录并检查源目标st_dev不同。未指定卷或设备相同明确跳过，不生成跨文件系统通过结论。

```sh
CREATIVE_TEST_CROSSFS_ROOT=/path/to/test-volume PYTHONPATH=tests:plugins/app-store-creative/scripts python3 -m unittest -v test_cross_filesystem_process_crash.CrossFilesystemProcessCrashTests
```

2026-10-08临时APFS卷实际17项通过，覆盖正反向意图、目录发布、配置安装、终态回执前进程中断及公开续执行/回滚、源变化拒绝。日志`/tmp/creative-crossfs-crash-matrix.log`，设备与日志指纹`/tmp/creative-crossfs-crash-matrix-proof.json`。测试卷已卸载，镜像保留。本机同文件系统测试及未提供独立卷的跳过不能替代此证据。

取消准备在任何删除前核对暂存创建证明及实际设备/inode；已完成准备还核对证明哈希。即使归属标记及载荷逐字节相同，同字节替换目录也拒绝删除，替换目录和原目录均保留。未持久化创建证明的暂存目录不自动认领或清理。

取消意图持久化后会重新核对全部待处理根，逐文件/目录删除前继续复核目录身份及标记。已复现的意图提交后同字节目录替换现在拒绝，原目录和替换目录保留，不写CANCELLED终态。此验收覆盖该明确替换时点，不声称穷尽所有并发父路径竞态。
