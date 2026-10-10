# ADR-002 实施状态

更新日期：2026-10-10。**核心能力已实现；完整审查、真实产品验收与发行未完成。**

本文件是当前进度的唯一权威；需求以 [ADR-002](ADR-002-artifact-lifecycle-and-release-archive.md) 为准。实现、专项验证、完整产品验收分别记录，不按测试数或模块数计算整体完成率。采用完整重新设计，不提供历史兼容、旧格式读取或自动回填。

## 当前交付状态

- 分支：`feat/unified-artifact-lifecycle-v2`；已推送提交 `1caf481f95f4a6e8c0b187fcb81b0c40cf86ea5d`；后续6份专项审查证据及本清单更新尚未提交。
- [PR #11](https://github.com/RbBtSn0w/app-store-creative/pull/11)：OPEN / DRAFT，目标 main；未合并、未推送 main、未更新安装插件。
- 待发布版本：0.3.0；不提供历史兼容、旧格式读取或自动回填。
- 当前提交完整 CI：[run 38048749906](https://github.com/RbBtSn0w/app-store-creative/actions/runs/38048749906)，本次查询 in_progress；上一提交afe98d42的run 38028580826已成功。
- 已保存的详细CI证据绑定3c200dc；最新远端成功状态与最终发行门禁分别核对，不能提前关闭最终发行门禁。

## 能力实现 checklist

这里的勾选仅表示实现与专项验证已有证据，不表示最终验收完成。

- [x] 不可变记录、内容寻址对象、身份、运行、输入快照及提交意图。
- [x] 四类存储根、自定义目录、本机覆盖和统一配置解析。
- [x] 截图、录屏、视频、封面生产及依赖、失败和部分产物记录。
- [x] 候选验证、精确批准、不可变封存和独立交付包。
- [x] 显式 Git/LFS/external 策略、媒体预算、归档配方及独立取回校验。
- [x] 私有原始证据、便携脱敏引用与命名存储后端。
- [x] 官方 ASC 交接，以及上传、处理、播放、封面分别观察的门禁。
- [x] 库存、保留、隔离、恢复、清理计划、永久删除及正反向搬迁。
- [x] CLI、Studio、技能合同、使用说明与运营流程。

## 完整验收与发行 checklist

| 状态 | 验收项 | 关闭条件 / 当前缺口 |
| --- | --- | --- |
| [x] | 批准配置与归档配方绑定 | 必需证据及统一路径转换检查；96项调用方与29项独立分发验证已通过 |
| [x] | 正式交付显式预算 | 实现、专项及实际浏览器保存/刷新验证已通过 |
| [ ] | 完整差异及敏感证据审查 | 源代码静态审查已完成；测试差异94/177，完整人工敏感信息审查未关闭 |
| [ ] | 最新源码完整 CI | 最终源码的具体运行成功，并核对测试、类型、构建和分发结果 |
| [ ] | 最新完整独立安装验收 | 使用最终分发包，证明不依赖源码运行时；此前包证据不能覆盖所有后续修复 |
| [ ] | 长期持久存储 | 确定项目后端、访问控制与成本；完成真实媒体保存和干净环境取回 |
| [ ] | Levelory 全链路 | 新配置下重新生产；审核中文残留英文与截断；精确批准、封存、提交绑定、干净取回 |
| [ ] | 第二个不同真实产品 | 确定产品后完成独立工作区完整生命周期；合成夹具不能替代 |
| [ ] | 自定义目录端到端矩阵 | 两个真实产品中覆盖生产、封存、发布交接、维护、恢复及取回；CLI/Studio结果一致 |
| [ ] | 真实维护与恢复演练 | 失败、取消、重试、隔离、恢复、正反向搬迁和跨文件系统；永久删除需当次授权 |
| [ ] | 实际 ASC 闭环 | 精确上传计划批准后，经官方工具上传并验证处理、播放和封面；原0×0封面故障尚未关闭 |
| [ ] | 真实归档提交/PR绑定 | 按最终归档提交绑定清单哈希，合并后重新核对身份 |
| [x] | 独立分支及 Draft PR 保存 | 已提交并推送 PR #11；不代表发行完成 |
| [ ] | 合并、安装与复验 | main合并/推送，`adg plugins update -g`，安装版本与真实工作流复验 |

## 当前证据与边界

| 范围 | 当前状态 | 权威证据 |
| --- | --- | --- |
| Python运行时静态审查 | 58/58模块；当前文件哈希绑定 | [清单](evidence/ADR-002-runtime-review-inventory-c98edbc.json) |
| 前端运行源码静态审查 | 46/46文件；另有1个测试专用夹具 | [清单](evidence/ADR-002-frontend-review-inventory.json) |
| 测试差异审查 | 94/177文件；剩余83个新增测试文件 | [清单](evidence/ADR-002-test-diff-review-inventory.json) |
| 凭据模式筛查 | 历史98个变更ADR文档/证据已筛查；不是完整人工审查，也不覆盖后续新增文件 | [证据](evidence/ADR-002-sensitive-evidence-screening.json) |
| 完整前端验证 | 最近执行98项/33文件通过，类型检查和构建通过；本机Node25 | [旧入口退休证据](evidence/ADR-002-studio-obsolete-toolbar-review.json) |
| 独立分发包 | 622d224包烟雾检查及59项回归通过（15.078秒），加载路径来自独立解压目录；实际adg安装另行验收 | [证据](evidence/ADR-002-independent-package-622d224.json) |
| 最新专项测试 | 发布顺序7项通过；真实SIGKILL租约确定时钟边界单项通过 | [发布](evidence/ADR-002-test-delivery-publication-review.json)、[租约](evidence/ADR-002-test-remote-observations-review.json) |

测试通过、模块审查和哈希匹配各自证明其明确范围，不能替代真实产品、浏览器、长期后端或ASC验收。既有测试修改与删除、全部前端测试差异均已审查；新增运行时测试仍需继续审查。旧测试退休不允许丢失租约所有权、源完整性、批准分离和不覆盖用户文件等现行约束。

## 真实产品与待决策项

- Levelory已有10张真实设计截图、20秒视频及封面候选，技术检查通过；候选早于新归档/预算要求，必须新配置重新生产，不能回填冒充新闭环。
- 第二个真实产品及长期持久后端尚未确定。
- 原ASC视频处理和播放已观察；0×0封面问题尚未关闭，不能以处理成功替代封面验收。
- 人类输入：第二产品及后端选择、精确候选内容批准、精确上传计划批准。永久删除需要当次授权。
- 独立可推进工作不等待上述输入：剩余测试差异审查、最终CI/包验证、可逆维护与浏览器验证。

## 接下来的交付顺序

1. 完成剩余测试差异与人工敏感证据审查，修复发现的问题。
2. 核对最终提交完整CI、独立分发包和实际浏览器；完成自定义目录与维护恢复矩阵。
3. 完成两个真实产品的新配置生产、精确批准、持久归档、干净取回与实际ASC闭环。
4. 绑定最终归档提交/PR，合并并推送main，更新插件，复验安装后的真实流程。

只有全部显式需求有匹配范围的当前证据，才能宣布完成。审查过程与旧观察保留在[历史快照](evidence/ADR-002-progress-history-through-3c200dc.md)中；历史快照不是当前状态权威。

旧入口退休后的租约约束补验：现行租约测试完整审查，9项实际回归通过（0.912秒）。独立客户端身份、过期前提交检查、续租旧令牌隔离及并发唯一恢复均有断言。[证据](evidence/ADR-002-test-lease-contract-review.json)。该文件相对origin/main无差异，不增加94/177审查计数；不替代跨卷或真实进程崩溃验收。

录屏规范化与媒体探测两个新增测试完整差异审查，7项回归通过（0.631秒），包含实际ffmpeg/ffprobe媒体。原始素材不可变、禁止补帧伪造时长、目标不覆盖及最终格式拒绝均有断言。[证据](evidence/ADR-002-test-recording-media-review.json)。不替代真实产品捕获和ASC验收。

录屏执行者与托管录屏测试完整审查，6项回归通过（0.623秒），编译driver别名、SDK/target、隐私字段拒绝、并发收据保留及原始/部分素材依赖有明确断言。[证据](evidence/ADR-002-test-recording-executor-review.json)。真实Swift编译及窗口替换门禁不由夹具证明。

截图采集依赖导入测试完整审查，8项回归通过（0.822秒）：失败/部分/损坏采集及无效上游在创建新运行前拒绝，原始采集依赖在生产链保持。[证据](evidence/ADR-002-test-capture-dependency-review.json)。尺寸与重名导入属于独立范围，未由本文件证明。

记录完整性两个测试文件审查及5项回归通过（0.394秒）：提交后字节篡改、FIFO阻塞替换、锁身份替换及对象目录符号链接替换均拒绝且保护外部文件。[证据](evidence/ADR-002-test-record-integrity-review.json)。重复意图消费不由该范围证明。

工具、实现和产品身份三个测试完整审查，7项通过（0.853秒）：工具替换拒绝、位置无关实现哈希、封存逐尝试身份及无效产品身份写前拒绝均有断言。[证据](evidence/ADR-002-test-portable-identity-review.json)。对象失败注册及重复意图消费仍是独立范围。

普通恢复意图测试完整审查，12项通过（0.634秒），包括真实子进程SIGKILL后保留原意图恢复、拒绝篡改/缺失意图及恢复期间阻断旧删除计划。[证据](evidence/ADR-002-test-restore-intent-review.json)。使用隔离夹具，不替代跨卷与两产品验收。

配置内容/放置身份与回滚两个测试文件完整审查，11项通过（6.918秒），同字节inode替换、临时文件替换及验证后替换均阻止回滚覆盖，自己的安装证明支持中断恢复。[证据](evidence/ADR-002-test-configuration-identity-review.json)。

外部交付身份测试完整审查，7项通过（2.326秒）：目标/项目/资产篡改阻断批准交接，实际大媒体流式校验、错误checksum与FIFO拒绝有断言。[证据](evidence/ADR-002-test-external-identity-review.json)。不替代真实长期后端、目录替换或ASC验收。

交付定位与外部引用合同两个测试完整审查，5项通过（0.517秒）：搬迁映射不改原记录、越界/损坏包拒绝、非法引用写前拒绝。[证据](evidence/ADR-002-test-archive-location-review.json)。测试中的historical指现行设计搬迁前位置，不是旧格式兼容；符号链接替换仍需独立覆盖。

外部媒体存储测试完整审查，7项通过（0.310秒）：源删除后独立取回、精确版本拒绝回退、目录符号链接替换拒绝并保留外部文件、CLI恢复不改原元数据。[证据](evidence/ADR-002-test-external-store-review.json)。实际长期后端及跨卷/两产品仍待验收。

归档清单与来源图两个测试完整审查，12项通过（1.712秒）：重算哈希不能绕过原批准配置/审批语义，别名语义与来源闭包拒绝不完整/失败图，1200节点无递归验证通过。[证据](evidence/ADR-002-test-archive-contract-review.json)。真实封存及完整隐私审查仍独立验收。

合并后归档绑定测试完整审查，真实本机Git squash/裸远端推送与独立取回1项通过（1.199秒）：新提交新发布范围不复用旧上传批准，原记录保留。[证据](evidence/ADR-002-test-post-merge-binding-review.json)。不替代真实GitHub归档PR绑定与发布。

Git独立取回测试完整审查，2项通过（0.532秒）：移除工作树归档后实际clone取回明确提交/清单，未提交路径拒绝。[证据](evidence/ADR-002-test-git-retrieval-review.json)。未删除全部生产配置/源，不能据此声称完整生产环境隔离。

独立取回策略测试完整审查，1项通过（0.324秒）：声明LFS但提交普通媒体字节会被独立取回拒绝。[证据](evidence/ADR-002-test-retrieval-policy-review.json)。文件名不代表正向LFS/外部恢复或完整生产目录隔离；这些门禁仍未关闭。

分层归档可移植性测试完整审查，2项通过（1.227秒）：本机覆盖不进入归档JSON，重算哈希仍拒绝私有层字段，恢复后配方校验通过。[证据](evidence/ADR-002-test-layered-portability-review.json)。未执行恢复配方重新渲染，不记为独立再生产验收。

原生Preview归档集成测试完整审查，2项通过（14.759秒）：实际合成视频/封面经CLI生产封存，删除原项目后从恢复包实际重放成功，便携工具/素材证据保留。[证据](evidence/ADR-002-test-native-preview-archive-review.json)。明确是合成媒体，不替代两真实产品或实际ASC闭环。

归档策略配置测试完整审查，4项通过（0.047秒）：三入口非法声明写前拒绝、显式模式保留、探索不虚构选择、取回模式/后端必须匹配。[证据](evidence/ADR-002-test-archive-policy-review.json)。

交付状态与Studio观察两个测试完整审查，5项通过（2.848秒）：损坏包拒绝成功、只读记录不变、远端UNKNOWN独立保留，重启HTTP与实际CLI一致。[证据](evidence/ADR-002-test-delivery-observation-review.json)。不替代实际浏览器和ASC验收。

外部归档恢复集成测试完整审查，5项通过（1.329秒）：删除原封存/生命周期目录后恢复、无配置clean clone实际CLI取回、指定裸远端明确提交/descriptor验证及缺对象不发布。[证据](evidence/ADR-002-test-external-archive-review.json)。仍为隔离本机后端，不替代真实长期存储验收。

622d224完整插件打包及隔离运行时烟雾检查通过。[证据](evidence/ADR-002-package-smoke-622d224.json)。独立59项回归随后已通过；实际adg安装未执行，不关闭最终安装与真实工作流门禁。

622d224独立解压插件运行时59项回归通过（15.078秒），加载路径断言排除源码运行时，包与日志哈希已绑定。[证据](evidence/ADR-002-independent-package-622d224.json)。仍不替代实际adg安装、浏览器及真实产品验收。

库存观察失败与预算测试完整审查，修复HTTP错误响应未关闭导致的资源警告；10项以ResourceWarning错误模式通过（1.406秒）。未知容量不冒充零，观察不完整阻断维护，损坏归档预算UNKNOWN。[证据](evidence/ADR-002-test-inventory-budget-review.json)。

取回进程期限测试完整审查，4项真实子进程验证通过（1.650秒）：忽略终止的子进程、退出leader留下的pipe子进程和取消均收敛，同组命令共享总预算。[证据](evidence/ADR-002-test-retrieval-deadline-review.json)。后续修复将子进程就绪等待与清理超时分离，并用受控时钟验证总预算；4项以ResourceWarning错误模式通过（0.860秒）。未当作远端网络验收。

生命周期记录schema测试完整审查，8项通过（0.137秒）：版本/对象/身份及符号链接边界严格拒绝，全部业务类别不回填无效记录。[证据](evidence/ADR-002-test-record-schema-review.json)。不代表所有业务字段语义已验收。

尝试审计合同测试完整审查，2项通过（0.036秒）：空白/非文本执行者与阶段不创建尝试，非法失败原因不结束尝试。[证据](evidence/ADR-002-test-attempt-audit-review.json)。

Studio分层保存测试完整审查，4项通过（2.500秒）：缺If-Match写前428、本机层变化409、有效目录与本机文档保留及活动归档根变更400。[证据](evidence/ADR-002-test-layered-save-review.json)。不替代实际浏览器保存期间交互。

状态输入与本机层素材导入两个测试完整审查，4项通过（0.951秒）：非法状态身份不写文件，HTTP导入/读取同Unicode本机根且配置字节保留。[证据](evidence/ADR-002-test-input-status-review.json)。重名及导入路径穿越未由该范围证明。

暂存证明绑定测试完整审查，4项通过（2.279秒）：替换目录并重写身份证明仍被原哈希拒绝，正反向恢复/回滚与库存不误报成功。[证据](evidence/ADR-002-test-staging-proof-review.json)。取消和生产失败资格为独立范围。

验证策略绑定测试完整审查，1项通过（0.128秒）：修改验证版本/运行/errors不产生批准。[证据](evidence/ADR-002-test-validation-policy-review.json)。篡改同时触发提交绑定，尚不能独立证明新提交畸形验证的语义门禁。

验证语义覆盖缺口已补齐：新增有效提交事件下畸形验证记录回归，先确认记录读取有效，再断言Passing validation语义拒绝且无批准；2项通过（0.279秒）。未修改运行时行为。

保留策略测试完整审查，5项通过（0.833秒）：明确期限默认、非法策略拒绝、策略变化阻断旧计划、CLI/HTTP只读一致。[证据](evidence/ADR-002-test-retention-policy-review.json)。未执行实际永久清理。

导出服务失败清理回归完整审查，1项通过（0.508秒）：健康失败返回前实际监听不可连接且线程已停止。[证据](evidence/ADR-002-test-server-cleanup-review.json)。

PNG完整性回归完整审查，2项通过（0.003秒）：截断/像素块损坏在两种host工具路径均拒绝，合法RGB/alpha保留。[证据](evidence/ADR-002-test-png-integrity-review.json)。

独立封面合同测试完整审查，3项通过（0.292秒）：缺封面/尺寸不匹配拒绝，匹配封面本地通过。[证据](evidence/ADR-002-test-poster-contract-review.json)。视频probe为mock，时间点/依赖和ASC封面故障仍需独立验收。

封面生产/本机层请求/覆盖坐标三个测试完整审查，7项通过（1.377秒）：时间点及视频哈希绑定、失败取消部分素材保留、ETag执行前拒绝及滤镜坐标注入拒绝。[证据](evidence/ADR-002-test-poster-production-review.json)。抽帧为mock，不关闭实际封面/ASC验收。

发布目标/资产消费测试完整审查，3项通过（2.210秒）：保存记录篡改拒绝，有效提交下错误资产仍由归档语义比较拒绝，无交接目录。[证据](evidence/ADR-002-test-publication-consumption-review.json)。新提交非法目标及批准后变化仍需独立覆盖。

发布目标语义缺口补齐：有效提交且可正常读取的非法平台/app/version记录，仍由目标语义门禁拒绝批准和交接，原批准字节不变；4项通过（2.460秒）。未修改运行行为。

Studio发布HTTP/CLI测试完整审查，2项通过（2.485秒）：只读查询记录不变，UPLOAD批准和EXPORT交接保持独立，未声称实际上传/远端验证。[证据](evidence/ADR-002-test-studio-publication-review.json)。重启与实际浏览器为独立范围。

发布取回证明测试完整审查，7项通过（2.916秒）：实际clone身份绑定、clone失败无计划、有效提交下非法证明拒绝及归档模式不能重声明。[证据](evidence/ADR-002-test-publication-retrieval-review.json)。

托管Preview测试完整审查，7项通过（0.727秒）：输入目录失败终态、部分输出保留、便携证据与来源链、不合格输入执行前拒绝、复用输入媒体身份保留。[证据](evidence/ADR-002-test-managed-preview-review.json)。executor为mock，不代表实际编码或执行中输入变化验收。

存储配置预览测试完整审查，8项通过（2.433秒）：默认/派生/本机来源、搬迁要求、归属冲突及CLI/重启HTTP一致，完整磁盘快照不变。[证据](evidence/ADR-002-test-storage-preview-review.json)。只读预览不替代实际保存与搬迁矩阵。

配置分层核心测试完整审查，13项通过（0.510秒）：本机优先与配方身份分离、实际Git忽略且未跟踪、重复键/符号链接/解析中变更拒绝及命名后端访问保持本机。[证据](evidence/ADR-002-test-configuration-layers-review.json)。

正向搬迁配置层测试完整审查，8项通过（0.762秒）：源文档绑定、层出现/同字节文件替换写前拒绝、准备保留配置、缺共享authority不创建计划。[证据](evidence/ADR-002-test-relocation-layer-review.json)。完成切换更新owning层另行验证。

反向搬迁配置层测试完整审查，8项通过（8.118秒）：配置替换/本机层漂移阻断交换与恢复，恢复审阅层状态后可续执行，目录身份不被误改。[证据](evidence/ADR-002-test-reverse-layer-review.json)。完成本机层切换字节与返回后新运行为独立范围。
