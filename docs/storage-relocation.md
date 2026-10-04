# 存储目录搬迁

目录搬迁保持物料身份、业务记录和源字节。当前支持计划、准备、正式切换及中断后的向前恢复/回滚，源数据不自动删除。PREPARED不等于搬迁完成；已激活目标的反向搬迁及完整路径竞态防护仍待完成。

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

计划绑定当前配置及其文件字节、源与目标根、每个源文件的SHA256及大小。嵌套对象库单独列出，不在workspace清单中重复。已有交付包必须通过完整性校验，已登记对象和隔离证据不得缺失或损坏。

仍有未结束尝试时拒绝计划，不以租约过期推断原进程退出。符号链接不跟随、不复制。目标根不得覆盖已有目录；移动目标不得位于需要复制的源根内部。仅移动对象库且工作根保留时，可以使用该工作根内的新空位置。

源文件或配置变化后旧计划失效，需要重新生成；READY只说明当前复查满足计划，不执行复制或切换。

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

后续必须补齐可恢复的切换事务、位置绑定链、审批与内容身份保持、原位置写入封锁和失败回滚。

归档位置改变还需要保持原Git归档提交的取回定位，不能把本机路径变更当作新媒体批准。源目录最终清理是单独授权维护，普通搬迁不会自动删除源数据。

## 归档本机位置与Git位置

交付记录保存封存时的storage及local_path；读取时先验证位置链，再按原归档根中的相对位置定位当前包，并验证manifest_sha256。发布计划使用原Git提交中的归档路径，上传审批、交接导出和远端状态复查均按计划的archive_path验证Git字节，不把搬迁后的本机路径当作新的提交路径。位置改变不改写交付记录、清单或设计批准。

当前Git模式要求原归档位置在项目仓库内；外部归档首次进入Git的显式导出与LFS/external取回验证仍待完成。

## 切换前写入封锁合同

统一事务入口在获取源工作区锁后检查该存储绑定的不可变storage-fences记录。安装封锁前必须复查计划、Git门禁和全部已准备副本；随后旧绑定的新run、维护写入及准备重试均拒绝，独立CLI进程也受同一检查约束。封锁不会把读操作报告成搬迁成功。

封锁由正式切换事务安装，中断回滚通过绑定证据解除；没有独立安装或删除封锁命令。不能手工修改记录代替恢复。

## 目标启用与对象库归属

目标绑定带有storage-activations记录时，统一事务核对指定SWITCHED回执的完整哈希、目标根、项目及配置权限范围。回执缺失或不匹配时禁止新run和清理；正式事务尚需负责安装待启用记录及在全部步骤完成后生成回执。

对象库_owner.json保存首次归属的项目身份和完整存储绑定；后续写入通过已验证位置链确认当前归属。工作区搬迁不改写该记录，无位置链的其他工作区仍拒绝共享对象库。该设计仍限定单项目本地后端。

## 内部切换事务

内部switch_relocation串联准备复查、源写入封锁、证据转移、目标待启用、目录排他发布、逐项字节复查、配置原子替换、位置链及最终SWITCHED回执。切换意图保留原配置精确字节和文件权限，用于后续恢复。源数据始终保留；仅移动对象库也经过同一事务。

5项测试覆盖成功后旧run读取及新run写入、配置替换失败后的双端保护、准备副本篡改、工作根保留时对象库移动、已有批准与归档继续封存。切换通过switch-relocate开放，中断通过显式原工作区恢复。

## 中断切换回滚（内部入口）

rollback_relocation使用原工作区锁及计划权限范围，校验原配置备份哈希、当前配置和完整源快照。当前配置只允许为原始字节或本次目标字节，用户的其他编辑不会被覆盖。恢复原配置后追加ROLLED_BACK回执和精确绑定该回执与封锁哈希的解除记录；不删除源、目标或暂存副本。封锁按批次追加，回滚不移除历史记录。

5项测试覆盖配置替换失败、配置已切换但位置链未完成、部分目录发布、源被修改和用户配置编辑。目标一旦生成SWITCHED回执，此入口拒绝回滚，后续需单独的反向搬迁及目标写入冻结。已激活目标回滚和残留副本维护仍未完成。

## 中断切换向前恢复（内部入口）

resume_relocation在原工作区锁下复查源快照、配置、封锁和本批次标记；分别识别已经发布的根和剩余暂存根。清单中的副本与操作证据逐项验证，未知文件、链接、冲突根和配置编辑均拒绝续执行，不删除或覆盖它们。剩余根以排他方式发布，最后完成配置、位置链和原切换回执；已回滚批次禁止向前恢复，重复完成请求返回同一回执。

恢复通过resume-relocate/rollback-relocate开放，并显式校验原位置上下文。已激活目标反向搬迁及整体端到端验收仍未完成。

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
