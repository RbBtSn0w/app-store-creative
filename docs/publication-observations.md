# 发布观察与完成门禁

Creative负责绑定、保存和评估证据；官方ASC插件负责远端执行和采集。当前内核接受执行者提供的规范化观察，不自行登录、上传、请求ASC API或采集浏览器播放结果。测试中的观察是合同样例，不能当作真实发布证明。

## 观察入口

执行者从实际响应、解码检查或人工复查中提取事实，保存为JSON，再登记。plan_sha256必须与实际发布计划的规范化哈希匹配，target必须完整一致；artifact_id来自该计划，remote_id是对应远端媒体资源身份。

```json
{
  "plan_sha256": "FULL_PLAN_SHA256",
  "target": {"app_id": "123456", "version_id": "VERSION_RESOURCE_ID", "platform": "MAC_OS"},
  "artifact_id": "ARTIFACT_ID",
  "remote_id": "REMOTE_MEDIA_RESOURCE_ID",
  "gate": "processing",
  "source": "asc-cli",
  "observed_at": "2026-10-03T10:00:00+00:00",
  "evidence_reference": "asc:request-receipt-id",
  "evidence_sha256": "FULL_EVIDENCE_SHA256",
  "facts": {"processing_state": "COMPLETE"},
  "supersedes": []
}
```

```sh
python3 app_store_creative.py publication observe --repo /path/to/project \
  --id PUBLICATION_ID --observation normalized-observation.json --evidence executor-response.json
python3 app_store_creative.py publication status --repo /path/to/project \
  --id PUBLICATION_ID
python3 app_store_creative.py publication export --repo /path/to/project \
  --id PUBLICATION_ID --confirm
```

evidence_sha256必须为实际非空证据字节的SHA-256。登记时使用--evidence提供原始证据文件，内核核对哈希后才写入观察；缺失、格式错误或内容改变均拒绝。ASC预览转换对输入响应文件的原始字节计算哈希，不重新序列化JSON。观察登记只保存哈希及受限事实。原文可由执行者保管，也可通过下文受管理保存及私有后端持久化入口保存；发布导出不复制原文或私有路径。登记时匹配不证明证据长期可取回或来源真实。

evidence_reference使用可追溯的执行记录身份，不能填本机绝对路径、带查询参数URL或凭证。内核仅接受规定的事实字段，不存储任意原始响应。执行者需要保留原始证据的可信定位；通用原文保存和独立取回入口见下文；各类ASC回执自动适配及真实执行者来源认证仍需独立验收。

## 独立门禁

| 门禁 | 接受事实 | 判定 |
| --- | --- | --- |
| upload | found、source_checksum | ASC API/CLI确认资源存在且源MD5匹配才通过；缺失或不匹配失败 |
| processing | processing_state | COMPLETE通过，FAILED失败，处理中或未知保持未知 |
| media/playback | media_verified | browser/media-probe/human-review的实际验证通过；API处理完成不替代解码或播放 |
| poster | poster_verified、poster_frame_time_code、poster_width、poster_height | 解码或复查通过、尺寸非零、时间码与计划一致才通过；尺寸存在本身不足 |

截图需要upload、processing、media；Preview需要upload、processing、playback、poster。所有物料及门禁都必须满足；单一上传回执不会让整套发布完成。未配置明确海报时间码时海报门禁保持未知，需要先修正生产配方和交付计划。

默认观察有效期24小时，可通过publication status的--max-age-seconds使用明确的复查策略。缺失或过期证据保持UNKNOWN。同一门禁存在PASS和FAIL会形成CONFLICT；不同远端资源身份也形成CONFLICT。PASS与UNKNOWN同时存在仍为UNKNOWN，不按最后一条记录自动覆盖。

观察不可修改。复查解决问题时，新观察通过supersedes明确列出被取代的观察ID；被取代记录仍保留。取代必须属于同一计划、物料和门禁，新观察不能早于被取代观察。更换远端媒体身份时，各门禁都需要重新绑定并消除旧身份冲突。

整体PASS还要求绑定同一计划的上传批准和可校验的Git归档。状态分别返回remote_media_verified、archive_verified、upload_approval和最终remote_verified；归档损坏阻止整体完成。

## 发布记录归档

publication export将计划、独立观察和脱敏上传审批摘要追加到配置的publicationRoot。文件以不可变ID命名，重复导出不覆盖已有证据；授权来源只导出哈希，不导出原始授权文本。工作区仍是运行事实源，导出目录用于版本管理和复查。

当前提供`publication normalize-asc-preview`适配官方ASC Preview响应；这不代表所有ASC回执均有适配器。独立导出目录重建运行记录的完整恢复入口、Studio观察编辑界面及实际远端全链路验收仍未完成。

公开`publication observe`的观察JSON及证据文件必须为普通文件，读取期间身份及内容变化拒绝，单文件上限30MiB；原始视频不作为此入口的证据文件，应由媒体探测执行方提供绑定媒体身份与验证结果的证据回执。文件输入核验在创建登记事务前完成，非普通文件拒绝不生成工作区。此约束不提供原始证据长期存放能力。

`publication normalize-asc-preview`的响应与scope输入也使用同一普通文件、身份及30MiB读取边界；文件检查先于登记事务，保留响应原始字节用于证据哈希，不重新序列化响应。无效输入不创建工作区。

## 本地受管理原始证据

```sh
python3 app_store_creative.py publication retain-evidence --repo /path/to/project \
  --observation-id OBSERVATION_ID --evidence executor-response.json --actor EXECUTOR_ID
```

此入口匹配原观察证据哈希及确切计划，独立attempt登记私有原文并追加不可变关联；原观察与封存包不变。登记对象纳入清理引用保护，不导出原文到publicationRoot。输入采用普通文件及30MiB限制。它仅完成本地保管；长期存放须继续执行下文持久化、定位导出和独立取回流程。保存被KeyboardInterrupt或SystemExit取消时，attempt记为cancelled，已写出的工作回执保留，不生成证据关联。证据关联写入成功后才结束attempt为succeeded；关联失败时attempt为failed。关联已经写入但生产未成功的证据保留诊断，持久化及发布定位导出拒绝消费。强制杀进程及绑定提交阶段完整恢复仍待验收。

## 原始证据外部版本存放

```sh
python3 app_store_creative.py publication persist-evidence --repo /path/to/project \
  --evidence-id RETAINED_EVIDENCE_ID --backend PRIVATE_BACKEND
```

backend通过本机受保护配置解析；显式调试可使用`--backend-root`。入口核验观察与受管理artifact关系，复用现有external-media不可变版本记录，持久写入后独立读回核对字节再返回。原文留在选定私有后端，不进入publicationRoot。返回reference包含backend、对象身份、版本、哈希和大小，不包含本机root。当前仅文件系统provider，临时后端已验收；Studio命名后端接口及便携定位取回已接通；生产持久性、权限策略及Studio新交互实际浏览器验收仍待完成。

受管理证据已有external-media持久记录时，publication export向`evidence/<external-record-id>.json`追加观察/计划关系、原始哈希和严格版本定位；不复制原文、actor、本机路径或任意响应字段。非法定位在任何交接文件写出前拒绝。没有外部版本的本地证据不会被标记为持久可取回；导出定位本身不证明后端当前在线，消费端仍须实际独立取回核验。

## 干净消费端取回

```sh
python3 app_store_creative.py archive retrieve-evidence --repo /path/to/clean-consumer \
  --path locator.json --expected-sha256 TRUSTED_LOCATOR_SHA256 \
  --backend-root /private/backend --destination receipt.bin
```

可信locator哈希应从审查过的Git完整提交或独立可信清单取得，不能把待验证文件自身哈希当作来源认证。入口无需creative.config或运行数据库，先核验定位文件哈希、schema及观察/计划身份，再从指定私有后端取回准确版本并核验字节，不覆盖已有目标。输出retrieved只证明字节恢复，remote_verified保持false。当前文件系统provider及临时后端已验收；生产持久性、权限与Studio仍待完成。

临时Git合同验收已实际提交locator、从完整提交Git对象取得可信定位哈希，并通过禁用本地共享的独立克隆检出准确SHA；公开CLI无需配置/运行数据库即可恢复原始字节。该测试证明临时本机Git与文件系统后端的组合链路，不证明托管PR审查、远端持久性或真实执行者来源认证。

Studio本地HTTP `POST /api/publications/retain-evidence`接入同一核心：exact字段`observation_id`、`actor`、`confirm: RETAIN`及`evidence_base64`；保留既有同源、Host及30MiB请求限制，不接受客户端本机文件路径。证据字节仍须匹配原观察。文件选择与持久化界面已接通，合成夹具的浏览器专项证据保留在ADR历史记录中；真实产品的完整浏览器运营验收仍未完成。


## Studio 私有后端持久化

Studio 的 Persist original evidence 使用已登记的 evidence ID 和本机配置中的 backend 名称。HTTP 请求只接受 `evidence_id`、`backend`、`confirm=PERSIST`；不能通过浏览器提供或覆盖文件系统路径。未配置后端直接拒绝。

保存复用受管理外部版本接口，并在返回成功前独立读取核对原始字节。界面显示版本；该结果不证明后端长期可用，也不证明 ASC 媒体通过。成功或未知结果后禁用直接重发，重新请求前需核对已有记录。

```http
POST /api/publications/persist-evidence
Content-Type: application/json

{"evidence_id":"<retained-evidence-id>","backend":"evidence-team","confirm":"PERSIST"}
```


## 强制终止后的证据保存恢复

保存进程被强制终止后，先检查生产历史中的 attempt、已写工作回执及关联。没有成功 outcome 的证据不能持久化或作为发布定位导出；不能根据关联文件存在推断保存已成功。

1. 保留原 attempt 与工作回执。有效租约期间不得接管；确认进程已经终止并等待租约到期。
2. 使用公开 `attempt recover`，提供原 attempt ID、恢复执行者、原因和 `RECOVER` 确认。原 attempt 结束为 interrupted，接管创建独立工作目录并记录 retry_of。
3. 当前通用接管不自动继续原始回执绑定。用接管返回的 lease token 将新 attempt 明确结束为 cancelled，说明将重新执行回执保存。
4. 对同一个原观察使用 `publication retain-evidence` 和原始回执重新保存。新 attempt、artifact 与关联独立生成，不覆盖原失败产物。
5. 核对新关联及原文哈希，再执行私有后端持久化和独立取回。

真实子进程SIGKILL专项覆盖artifact登记后与关联写入后两个中断点；核验有效租约拒绝接管、到期接管、旧回执保留及重新登记。该证据不覆盖所有落盘中断点，也不证明Studio具有一键恢复入口。


## 证据关联的提交核验

读取 observation-evidence 时，核对其原提交事件的类别、身份、后缀、项目及完整记录哈希。执行者或关联字段被改写，或提交事件缺失时，持久化和实际发布导出拒绝执行，保留损坏记录供诊断。该检查保证记录与已有提交事件一致；不等同于第三方签名或真实ASC来源认证。


## 未知请求的只读复查

publication status及Studio发布复查展示evidence_custody：受管理关联ID、观察ID、artifact身份/哈希、生产是否成功及已登记外部版本。查询核对记录、原文对象和范围，不写入任何文件；损坏或未完成证据保留诊断，不列为可消费的外部版本。字段不包含原文或后端访问路径。

登记或持久化请求结果未知时，先选择对应发布计划并检查这些身份，再决定是否发起新请求。保存的外部版本只证明过去完成的独立读回，不证明后端当前在线。远端状态仍由上传、处理、播放和封面各门禁决定。

## 独立脱敏摘要合同

`retain-evidence`在同一独立生产attempt登记原始`observation-evidence`和`observation-summary`物料，各有独立身份、SHA-256及字节大小。摘要仅包含观察/发布/计划/产物身份、来源类别、时间、门禁、受许可事实及原始字节哈希；不包含actor、证据引用、本机路径或原始响应全文。摘要依赖原始证据，关联记录固定两者身份及哈希；引用保护同时保留两者。

持久化及导出重新核验摘要字节、依赖、范围和生产完成状态。版本定位文件内嵌受许可摘要及`summary_sha256`，独立取回先验证可信定位哈希、摘要哈希、范围和字段值，再读取原始后端版本。摘要不冒充原文，`remote_verified`仍为false。缺失摘要的新合同记录拒绝，不自动回填历史数据。

当前37项观察/依赖回归及7项独立取回测试通过（`/tmp/creative-summary-expanded-regression.log`及本地专项输出）；仍需当前安装包复验、完整失败/维护矩阵、生产后端和真实ASC验收。912项历史全量结果发生在摘要实现之前。
