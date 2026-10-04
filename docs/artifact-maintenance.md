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

默认未选用且已终止的媒体保留30天；已弃用候选从弃用记录时间起也保留相应时长。活动尝试、现有候选、审批、交付、未结事故、当前配置及未退役输入库引用持续保护。保留参数属于显式项目维护策略，不能为了腾空间随意缩短。

```sh
python3 app_store_creative.py cleanup plan --repo /path/to/project
python3 app_store_creative.py cleanup quarantine --repo /path/to/project \
  --id CLEANUP_PLAN_ID --actor OWNER --reason "Expired unused trials" --confirm QUARANTINE
python3 app_store_creative.py cleanup restore --repo /path/to/project \
  --id QUARANTINE_OPERATION_ID --actor OWNER --reason "Recover trial" --confirm RESTORE
```

先审查计划的对象、大小、来源artifact列表与保留期限，再执行隔离。执行前重新检查生命周期记录和文件哈希；新增引用或文件变化使计划失效，必须生成新计划。未知文件不进入计划。

隔离操作意图先登记，再逐对象建立隔离副本并移除活动位置。隔离副本位于配置对象库内，以支持同一文件系统操作。中断后可以按隔离操作ID恢复；恢复前检查全部可用字节，不覆盖损坏的现有对象。恢复保留隔离副本，支持重试。

## 永久删除隔离副本

默认隔离完成后保留7天。永久删除需要单独生成计划和明确确认；普通导出、关闭Studio或进程退出不会执行删除。

```sh
python3 app_store_creative.py cleanup plan-purge --repo /path/to/project \
  --id QUARANTINE_OPERATION_ID
python3 app_store_creative.py cleanup purge --repo /path/to/project \
  --id PURGE_PLAN_ID --actor OWNER --reason "Quarantine retention expired" --confirm PURGE
```

执行前再次验证引用、保留期、存储绑定、大小与哈希。恢复过的隔离操作不能使用旧计划删除；需要重新生成清理流程。永久删除开始后无法恢复该隔离操作。中断重试使用原PURGE_PLAN_ID；不要新建计划掩盖部分执行状态。未知隔离文件和全部业务记录继续保留。

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

## 当前边界

尚待实现日志分类保留、执行器自动重放、完整并发恢复和目录relocate。库存已区分已登记、改变和未知工作文件；库存报告不能直接用作删除清单。正式归档和已有批准物料保持保护；归档缓存回收需要后续远端取回证据机制。

维护成功只说明本地操作完成，不表示ASC上传、视频播放或海报复查通过。
