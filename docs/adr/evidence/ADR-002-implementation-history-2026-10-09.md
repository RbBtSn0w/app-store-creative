# ADR-002 阶段证据历史

本文件是整理前实施状态的历史快照，不是当前状态权威。旧“当前”“待终态”等措辞只表示当时观察；最新状态统一读取 [实施状态](../ADR-002-implementation-status.md)。失败和被取消的证据保留，不改写为成功。

# ADR-002 实施状态

## 最新验收快照（2026-10-09）

整体状态：整改尚未交付。以下区分已落地实现与最终验收；历史通过结果不能替代最新源码验证。

- [x] 新合同架构与实体模型落地；项目身份、运行快照及提交绑定统一，不兼容读取旧记录。
- [x] 四类物料目录、自定义根目录及本机覆盖已接通配置、CLI和Studio。
- [x] 受管理生产、失败尝试保留、依赖与批准绑定、封存及取回能力已实现。
- [x] Git保存配方/清单/批准/脱敏证据，原始私有证据独立保存；临时后端独立取回已验证。
- [x] 当前核心跨卷恢复专项：独立APFS卷33项迁移/证据链测试通过，任务83.246秒退出0，测试卷已卸载。包含正反向进程中断恢复；不代表完整维护或生产存储验收。
- [x] Studio私有证据持久化浏览器验收通过，仅限合成夹具。
- [x] 当前源码全量回归：984项执行，951通过、33跳过，740.445秒，312份源码指纹一致；证据`/tmp/creative-restore-intent-full-regression-proof.json`。跳过项为需独立卷环境的专项，不代表当前卷验收。
- [x] 当前恢复意图安装包验证：236份载荷与源码一致，SHA-256 `32e8e23357bdbb1ceb4238798ac155ae993bf1c8736878cd06a3b9c15c2a66c5`；隔离执行67项中66项通过，1项因测试夹具缺少打包工具失败，补齐该工具后独立重跑1项通过（2.317秒）。覆盖实际SIGKILL及恢复/清理互斥；此前包的媒体生产证据不能替代当前包媒体验收。
- [x] 三处状态诊断修复已应用；损坏记录返回FAIL，未知交付保持HTTP404，不从损坏记录传播身份。此前972项全量已通过；随后维护修复须单独复验。
- [ ] 完整维护验收：剩余权限/路径替换/协调边界、Studio中断恢复及永久清理操作。永久清理浏览器验收待当次用户确认。
- [ ] 生产持久后端：长期保存、访问控制、取回和成本验证；存储位置待确认。
- [ ] 两个真实产品闭环：截图、视频、封面、实际批准、封存及取回；第二产品待确认。Levelory Dev录制权限通过，但当前无可录窗口。
- [ ] ASC真实闭环：en-US封面时间码已调整并读回确认，但图片仍为0×0、图片请求HTTP 400；封面修复未成功。
- [ ] 最终差异审查、提交、PR、远端CI、合并main/push、插件更新及安装后真实复验。

下一顺序：恢复意图组合回归 → 更新安装包与验证 → 完整维护验收 → 生产存储及两产品闭环 → ASC复查 → 最终发行。

当前证据：`/tmp/creative-common-commit-final.log`、`/tmp/creative-common-commit-full-regression.log`、`/tmp/creative-installed-common-commit-regression.log`、`/tmp/creative-common-commit-package-proof.json`、`/tmp/creative-delivery-status-candidate-proof.json`、`/tmp/creative-preparation-status-candidate-proof.json`。

后文为历史记录，按对应时间和源码范围解释；与本快照冲突时，以本快照为当前状态。


## 当前工作区

- 分支：`feat/unified-artifact-lifecycle-v2`。
- 基线：`50a6414`，2026-10-08通过GitHub分支API再次核对，远端main仍一致。
- 隔离工作区：`/private/tmp/app-store-creative-redesign`。
- 原`feat/unified-artifact-lifecycle`工作区保持整改前状态；本次不继续写入。
- 当前差异尚未完成最终审查与发行，不据局部测试声明目标完成。

## 证据保存交付记录（分阶段）

原始观察证据已接通受管理保存、私有命名后端持久化、脱敏定位导出和无配置/数据库的独立取回。Studio本地登记实际浏览器通过；持久化界面已完成临时夹具浏览器验收，证据`/tmp/creative-persist-ui-browser-proof.json`；生产后端验收仍未完成。取消及关联提交失败会结束attempt，未成功生产的证据禁止持久化和发布导出。两个实际SIGKILL中断点使用通用租约接管恢复，仍需要显式结束接管attempt后重新保存。

当前证据生命周期独立包37项合同通过，234份载荷逐字节匹配；证据`/tmp/creative-installed-evidence-regression-proof.json`。这替代此前包对新增证据能力的缺失，不替代真实媒体生产、生产后端、真实ASC和最终全仓。源码尚未提交或发行。

## 历史全量与修复

冻结源树909项全量执行结束：889通过、3错误、17跳过，304份源码指纹不变。三个错误均来自新增局部base64导入遮蔽截图导入入口；重复导入已移除，51项组合及第三失败用例1项通过。新包常规检查包含三条证据命令。失败全量报告保留，不能将专项通过冒充修复后全量或远端CI。

## 能力状态

完整要求及关闭规则以[交付收敛审计](ADR-002-delivery-closure.md)为准。下表记录当前实现和剩余验收，不以模块数量计算百分比。

| 能力 | 当前实现 | 尚缺的关闭证据 |
| --- | --- | --- |
| 配置、存储和搬迁 | 四类根目录；项目/受保护本机配置；拥有层内容绑定；正反向计划、准备、切换、续执行和回滚；重复往返；命名外部后端访问配置随本机拥有层保留 | 剩余进程中断点、路径替换、权限及跨文件系统中断验收，以及搬迁副本完整维护闭环 |
| 生产和统一记录 | 捕获、截图、视频、海报、租约、来源、候选；不可变业务记录和提交审计；缺失提交显式放弃；操作日志只读查询 | 真实产品生产矩阵、完整执行工具身份、依赖失效、控制日志执行验证及失败恢复 |
| 审批、封存和取回 | 验证与设计批准绑定、不可变交付；Git/LFS独立取回；filesystem版本化对象；external元数据包及独立恢复 | 真实持久后端、实际项目提交/PR绑定及恢复演练 |
| 发布和远端证据 | 普通及external发布计划；独立上传批准；Studio计划审查/批准/本地交接导出；ASC响应转换；分开的上传、处理、媒体和封面门禁；external文件准备及重启复查 | 官方ASC实际执行、关系核验及新合同完整远端验收；不能从本机准备推断上传成功 |
| 库存与维护 | 对象及引用库存、保留计划、隔离/恢复、授权purge、搬迁备份观察；Studio搬迁维护完整入口及可逆浏览器验收；永久清理计划浏览器审查 | Studio永久删除最终执行与中断恢复浏览器验收、重复搬迁后的完整维护验收及生产远端恢复演练；本地封存包在副本永久删除后重建已验收 |
| Studio与发行 | 候选验证/设计批准/封存及恢复查询；记录、操作日志、发布批准与交接；普通及搬迁副本维护；安装技能合同及完整打包 | 完整异常恢复与执行验收；两个不同真实产品全流程；当前最终源树和实际安装工作流验收、最终差异审查及发行 |

## 已接通的闭环与证据边界

- 外部归档把便携元数据、准确Git提交、可信descriptor及版本化对象绑定；移除工作副本及本机媒体缓存后能够独立取回。命名后端访问配置保存在受保护且未跟踪的本机拥有层；不进入便携计划。临时filesystem和Git远端验收不代表生产持久后端。
- 业务记录绑定准确提交事件，区分提交完整、改变、未完成和明确放弃。控制日志仍只读观察，`execution_verified=false`，不能宣称执行验证已关闭。
- 正反向搬迁共用拥有层与目录身份检查；17项真实进程中断及2项复制准备中断验证公开CLI恢复。真实临时APFS卷正向、反向正常路径已通过，真实对象目录chmod读取权限撤销及暂存父目录写入撤销四项验收通过：先证明原计划可建立，再验证权限缺失拒绝计划；库存为未知、清理拒绝且记录不变，权限恢复后物料核验成功；真实准备写入失败保留意图和失败记录，恢复权限后新批次完成准备/切换且原记录不变；配置父目录写入拒绝发生于封锁前，恢复模式后旧意图拒绝，取消准备/新计划完成切换（tests/test_filesystem_permission_acceptance.py）。真实独立APFS卷跨文件系统中断矩阵17项通过（22.193秒），覆盖正反向四阶段公开CLI续执行/回滚及源变化拒绝；证据`/tmp/creative-crossfs-crash-matrix-proof.json`及对应日志。测试卷已卸载；无显式独立卷时17项明确跳过，不能把普通CI跳过当作跨文件系统通过。取消准备同字节目录替换负例已复现并修复：创建证明/实际目录身份不符时在删除前拒绝；25项组合回归及公开CLI取消专项通过，替换和原目录均保留；取消意图落盘后再次替换目录的负例也已修复，26项组合回归通过，删除前重新核对目录身份和拥有标记。其余权限及路径替换验收仍待完成。
- 候选批准与封存复查当前配置和源依赖；既有批准及封存字节保持不可变。Python/Swift实现指纹、媒体工具版本/哈希、浏览器实时引擎身份与录制编译身份进入证据；尚不证明完整执行环境或真实产品捕获。
- Studio正反向切换、正向中断续执行/回滚、发布批准自动刷新及搬迁副本隔离/恢复已通过独立测试项目浏览器验收。发布界面只输出本地交接，远端门禁保持独立。
- 永久清理库存保留完整原始文件清单和意图绑定的原计划，Studio显式重新审查后可恢复PURGING，禁止替代计划和自动重试。已清理记录正向搬迁及反向返回时同样保留原计划。6项HTTP验证包含删除中断后服务重启、原计划重读、替代计划拒绝及成功续执行。3项真实SIGKILL清理恢复和6项隔离/恢复进程中断测试通过。永久清理浏览器已验证完整计划及默认禁止执行，尚未点击最终删除。

所有浏览器和故障用例使用明确测试项目，不作为真实人类产品批准、真实产品捕获或ASC上传验收。

清理、真实进程中断、HTTP重启恢复、历史位置投影及投影恢复组合回归38项通过（63.283秒）。另有封存截图→四类目录搬迁→冗余副本永久清理→公开archive restore→完整包/字节核验→已有目的地保护的独立集成演练通过（`tests/test_post_purge_retrieval.py`）。这些证据不替代生产远端或两真实产品全流程。

普通对象永久清理已补齐计划/隔离操作/意图/终态的完整哈希绑定，重读终态核对准确容量及每个待删位置缺失。24项核心与Studio维护回归通过，覆盖重新出现文件保留、修改回执/计划/意图拒绝以及正确回执幂等读取。普通对象和搬迁副本仍各自按作用域核验；普通及搬迁副本维护按操作核验已接通CLI/只读HTTP和Studio历史列表；3项专项验证完整对象、损坏拒绝、未执行计划、重新出现文件保留、记录不变及公开入口重启一致性，26项核心/HTTP组合回归通过。83项前端测试、类型检查及构建通过。全量搬迁/封锁日志执行验证仍未完成。

普通对象永久清理逐文件检查点已实现；两个专项先复现无检查点丢失对象被误判完成，再验证拒绝，以及同字节替换保留。31项历史/维护/HTTP组合回归通过（4.948秒）；3项真实SIGKILL覆盖整体意图、文件检查点、终态回执之前，公开CLI按原计划恢复，读锁状态检查为PASS且物料元数据保留。此处只关闭该具体普通清理恢复窗口，不代表所有维护故障均验收。

最新完整包`/tmp/creative-maintenance-inspection-current.zip`已独立解压核验：60份Python/Swift/schema/Studio及入口载荷与当前源树逐字节一致；离开开发工作区环境后，包内公开history inspect-maintenance对独立临时隔离操作返回PASS，与核心结果相同。证据`/tmp/creative-maintenance-installed-proof.json`。该证明覆盖本地维护核验安装入口，不代表真实产品或远端发布。

搬迁复制对象独立核验已接通核心、CLI、只读HTTP和Studio。9项状态回归及公开入口重启一致性专项通过，验证激活保持VERIFIED但对象损坏时独立返回FAIL、没有目标读锁返回UNKNOWN且不创建锁、记录不变、覆盖参数拒绝。84项前端测试、类型检查及构建通过。反向返回专项验证正向后新增对象纳入完整检查、损坏拒绝及记录不变；重复A→B→A→B→A返回专项验证最新反向计划仍可准确核验，两项通过。新增专项分别修改来源和目标计划中的对象哈希，确认拒绝且保留变化后的记录；恢复原字节后同一检查重新通过。范围只含原计划复制的对象，不代表归档及全部搬迁/封锁执行核验。799项完整回归发生在本次新增实现之前；发行前仍须核对最终源树。

搬迁对象核验安装包已独立解压并在开发目录以外执行：`/tmp/creative-relocation-object-inspection.zip`的61份运行载荷与当前源树逐字节一致，包内storage inspect-relocated-objects检查两份复制对象返回PASS，与核心结果完全相同。证据`/tmp/creative-relocation-installed-proof.json`。原打包进程句柄已丢失，以现有包完整性、载荷一致性和实际入口执行作为本次可验证证据，不据此声称原进程终态。

artifactPolicy版本化解析及schema已补齐，内核与Studio配置检查拒绝未知版本/字段及非法数值。普通cleanup plan默认读取项目试制保留天数；CLI移除硬编码默认参数，显式参数仍登记实际天数。两个专项先复现缺口后通过。普通及搬迁副本保留/隔离期默认值已接入核心及CLI；普通计划保存完整解析策略，执行和续执行拒绝策略改变。新增两项先复现后通过，涵盖配置隔离期读取及旧计划拒绝。Studio策略读取已接通三个维护界面，核心/CLI/HTTP只读一致性与覆盖参数拒绝专项通过；85项前端测试、类型检查及构建通过。显式诊断角色的保留期限已接入普通对象清理，引用保护和同字节别名优先；未登记日志不自动回收。预算只读报告已接通核心、CLI、HTTP和Studio，完整容量范围仍未关闭。打包门禁已强制包含策略、预算和搬迁对象核验模块；独立解包后在仓库外、移除PYTHONPATH的空项目中读取实际策略及UNKNOWN预算，确认未创建状态。三个缺失模块负例均阻断打包（`/tmp/creative-policy-package-negative-proof.json`），当前完整包为`/tmp/creative-policy-budget-installed.zip`；这些检查不替代生产全流程。诊断期限/依赖保护/共享别名/原计划时间及永久清理组合36项通过；预算请求身份与未知范围渲染补充后88项前端测试、类型检查和构建通过。

## 当前验证证据

| 范围 | 实际结果 | 证据边界 |
| --- | --- | --- |
| 外部发布 | 8项通过 | 含公开CLI、配置名称解析、移除生产目录后的配置远端取回、准备记录重启复查及损坏拒绝 |
| 原发布回归 | 11项通过 | 现有Git发布合同与取回证明 |
| 远端观察回归 | 12项通过 | 已保存观察派生门禁，不是实际远端执行 |
| 配置及搬迁层回归 | 29项通过 | 含本机拥有层及配置保留，不覆盖全部文件系统故障矩阵 |
| 外部对象后端 | 6项通过 | 临时filesystem对象、准确版本及无覆盖恢复 |
| 搬迁真实进程中断 | 17项通过 | 四阶段正反向公开CLI续执行/回滚与源变化拒绝；日志`/tmp/creative-relocation-process-matrix.log` |
| 提交审计 | 14项通过 | 业务记录提交事件与只读审计 |
| 核心维护组合回归 | 77项通过，89.430秒；`/tmp/creative-copy-maintenance-core-regression.log` | 隔离、库存、永久清理及历史位置恢复，不代替完整最终源树验证 |
| 当前Studio后端回归 | 39项通过，35.577秒；`/tmp/creative-studio-maintenance-integrated-regression.log` | 包含搬迁副本维护接口；之后库存/恢复入口变更另有6项专项通过，不替代浏览器验收 |
| 最近前端验证 | 88项测试及类型检查、构建通过 | 最终发行源树仍需统一复验 |
| 发布批准自动刷新 | 浏览器批准后自动读取保存状态，显示Approved；未点击手动复查 | `/tmp/creative-publication-refresh-browser-proof.json`及同名PNG；测试项目，远端门禁仍为Not verified |
| 安装包入口 | `/tmp/creative-installed-external-entrypoints.zip`校验通过 | 独立解压后验证新增8个外部归档/发布命令入口，不代替真实产品全流程 |
| 复制准备进程中断 | 2项通过 | 公开恢复到新批次，失败暂存文件不覆盖；完成新批次准备与切换 |
| 搬迁恢复回归 | 19项通过 | 恢复10、续执行4、回滚5；支持最新缺失封锁修复 |
| 最近完整源树回归 | 819项通过，514.789秒；`/tmp/creative-redesign-policy-fence-full.log` | 266份Python实现/测试、原生源码及Studio源文件指纹运行前后一致；发生在后续控制日志/发布绑定复查增强之前；`/tmp/creative-redesign-policy-fence-integrity.json`。不代替真实产品、剩余故障及发行验收 |

此前703项全仓通过发生在操作日志、提交放弃及最近external改动之前，仅为旧源树证据，不支持当前完整源树结论。

真实浏览器测试项目曾完成候选验证、明确勾选测试批准、封存、刷新恢复相同交付ID及提交审计。证据位于`/private/tmp/creative-browser-fixture-evidence`，截图`/private/tmp/creative-studio-browser-review.jpg`。这是测试项目交互验证，不是人类产品设计批准。

2026-10-07对Levelory 1.5的实际只读ASC查询返回英文Preview处理COMPLETE、封面尺寸0×0；转换保留独立事实，没有把处理完成判定为封面可用。该查询也不是新合同发布全流程验收。

搬迁副本维护现已接入Studio计划、准备、保存记录复查、隔离提交、恢复、准备续执行与取消。6项HTTP专项覆盖中断删除后重启恢复、可逆流程、严格参数、取消、注入部分复制中断及临时项目永久清理；状态约束测试拒绝异常身份，不能代替实际浏览器验收。永久清理界面已接入独立计划及恢复对象审查。可逆维护浏览器验收已完成，证据`/tmp/creative-copy-maintenance-browser-proof.json`，独立活动物料核验通过；中断及永久清理浏览器验收仍未完成。

当前包独立解压后的入口启动通过，52份Python载荷及5份原生源码/schema/Studio构建资源与当次源树逐字节一致；之后库存/恢复入口有变更，需要在发行时重建并复验，证据`/tmp/creative-current-install-proof.json`。此结果是包内容一致性，不是产品实际安装全流程验收。

真实独立临时APFS卷已完成正向搬迁、隔离及恢复；另一独立试制完成正向后新增物料、反向返回原绑定、原有/新增物料核验及新运行。源目标设备不同，证据`/tmp/creative-crossfs-proof.json`、`/tmp/creative-crossfs-reverse-proof.json`。测试卷已卸载。跨文件系统正常路径已有实际证据，权限、替换及崩溃矩阵仍需完成。

源端缺失封锁按切出意图拒绝普通写入；25项状态/切换/恢复回归及48项反向/重复搬迁/真实进程中断组合通过（80.893秒）。历史源树完整回归819项通过、266份源文件指纹一致，证据见表格。

后续完整回归851项（549.674秒）出现7个批准诊断子场景错误，17个无独立卷的跨文件系统用例跳过，293份源文件指纹一致；失败证据为`/tmp/creative-final-source-regression.log`及对应proof.json，不计为通过。该缺口现已修复：只读状态展示损坏诊断，执行仍严格拒绝。修复后40项批准/发布/Studio/外部归档/审计组合通过（20.751秒），补充11项含公开CLI不可解析批准诊断通过（8.197秒）；日志分别为`/tmp/creative-approval-status-repair.log`和`/tmp/creative-approval-cli-diagnostics.log`。修复后的完整回归因SIGTERM中断，子进程退出-15，293份源文件指纹一致，没有测试最终汇总；证据`/tmp/creative-final-source-regression-repaired.log`及对应proof.json。该中断不计为通过，原因尚未确认。随后建立8段固定模块验证计划，852个测试ID的多重集合与unittest完整发现结果一致，绑定293份源文件指纹；证据目录`/tmp/creative-segmented-regression`。逐段保存终态，已完成段不自动重跑；所有段通过且覆盖核对完成前不计为全量测试通过，分段执行不代替远端CI。全部8段已完成：852项执行，835项通过、17项无独立卷用例跳过，293份源指纹一致；各段终态见result-0.json至result-7.json及summary.json。

当前验证包为`/tmp/creative-approval-diagnostics-package.zip`，SHA-256为11ced00d50565f89a2c6efc16bf033d54b4516465f4803209a74c5a5bf970d64。80份运行载荷/技能文档逐字节一致，仓库外移除PYTHONPATH后，公开CLI完成有效批准封存、损坏批准STALE诊断、封存拒绝和历史审计；项目文件保持不变，五个旧入口拒绝。证据`/tmp/creative-installed-approval-diagnostics-proof.json`。打包自检禁写Python字节码，完整包回归确认无缓存载荷（tests/test_package_runtime.py）。这些使用合成媒体和测试批准，不替代真实产品、人类批准或ASC验收。

此前安装包及目录替换取消验证保留为历史证据：`/tmp/creative-current-managed-contract-proof.json`、`/tmp/creative-installed-cancel-acceptance.json`及`/tmp/creative-installed-approval-proof.json`，不能代表当前包的全部行为。CI总时限调整为20分钟以覆盖已观察的全仓、前端及打包耗时，所有检查保留；远端CI尚未执行。

原生录制实际预检：2026-10-08使用当前Swift录制器查询Levelory Dev窗口，编译完成后因屏幕录制权限不可用退出2；不触发权限请求、不写成功回执，证据`/tmp/creative-native-permission-preflight.json`。该权限缺失结果已被2026-10-09只读预检取代：权限通过，Levelory Dev窗口列表为空，未录制；证据`/tmp/creative-native-permission-latest-proof.json`。两次预检均不证明实际录制成功。

批准读取完整性缺口已复现并修复：更改批准人后封存曾接受该记录，现在设计/上传批准经统一读取器核对完整记录哈希、提交意图类型、项目及位置绑定，缺失提交事件也拒绝；23项封存/发布/Studio组合回归通过；补充10项批准/发布组合通过，覆盖缺失事件拒绝、改动上传授权阻断交接文件写入，以及有效批准搬迁后读取和封存。另有42项批准/历史/清理组合通过（5.661秒，`/tmp/creative-approval-audit-acceptance.log`）：损坏批准仍报告CHANGED及FAIL，清理计划拒绝且记录/对象逐字节不变。该核验只证明本机提交完整性，不认证外部人类身份。

Studio策略/预算实际浏览器验收通过：空工作区总量显示未知及Not measured，明确4 KiB预算；普通维护加载项目17天保留/4天隔离，搬迁副本维护加载17天。配置字节未变，没有创建工作区或执行清理；证据`/tmp/creative-studio-policy-browser-proof.json`、对应DOM文本及截图。本证据不替代有已封存媒体的预算核验或维护执行。

合并后归档绑定专项通过：真实临时Git执行squash及仅推送合并分支，旧审查提交远端取回拒绝；新提交独立克隆验证清单不变，新计划保持未批准，旧批准及旧计划字节保留。8项专项/远端取回回归通过（6.226秒），证据`/tmp/creative-post-merge-binding-proof.json`及对应日志。原分段回归的293份源码仍一致，仅新增此专项测试，不代替托管PR/生产远端验收。

核心记录读取审查复现命名管道替换导致阻塞（2秒子进程超时，`/tmp/creative-record-identity-red.log`）。现复用现有普通文件身份读取，拒绝非普通文件、读取期间身份/字节变化，保留异常路径；33项记录schema/审计/批准组合通过（9.830秒，`/tmp/creative-record-identity-green.log`）。这属于ADR路径替换边界，未引入兼容读取。该修复发生在852项分段回归之后。扩大102项交付/发布/external/保留/搬迁恢复回归通过（24.499秒，`/tmp/creative-record-reader-expanded.log`）。更新包`/tmp/creative-record-reader-package.zip`（SHA-256 340891944e8c21bbd0c38a51aa2abdf0e31c19b7e7a467b05a6a4df88e20734c）80份载荷/技能文档与源码一致；独立安装公开CLI确认命名管道记录立即拒绝并保留，封存、批准诊断及旧入口拒绝仍通过，证据`/tmp/creative-installed-record-reader-proof.json`。旧852项结果不代表本次修复后全仓；真实产品及远端验收仍未完成。

## 下一步与完成标准

继续按完整能力补齐剩余验收，优先复用公开入口和真实工作流；不再追加重复历史段落，不另增ADR之外的硬件断电要求。两个真实产品必须分别完成截图、视频和封面生产到ASC交接、远端复查，并覆盖失败、取消、重试、隔离与恢复。最终源树、前端、完整包和实际安装行为一致，所有要求具有对应证据后才能声明整体完成。

## 当前观察证据合同核验

远端观察必须绑定实际非空证据字节的SHA-256；核心登记及公开CLI核验原文，ASC预览转换直接散列响应文件原始字节。读取无哈希旧记录拒绝，不自动回填。相关30项回归通过（16.421秒，`/tmp/creative-observation-evidence-final.log`）。独立安装包80份载荷/技能文件一致，公开CLI拒绝缺失和改动证据，三条合成观察登记与导出哈希一致（`/tmp/creative-installed-observation-evidence-proof.json`）。包SHA-256为`0f7b2f42838f56125efd294fbb60ee1d454ec27b95bb789e8d4ee9bef8ec0b0e`。原始证据由执行方保留，长期取回和真实远端验收未完成。最新合同源树本地分段全量回归已完成：858项执行、841项通过、17项独立卷用例跳过，8段退出均为0；296份源码指纹和文件集合未变，覆盖与发现清单一致。证据`/tmp/creative-current-contract-regression/summary.json`。这是本地分段执行，不证明单进程全仓、远端CI或真实产品验收；通用视频路径统一仍待整改。

## 当前独立安装包复验

最新交付身份及Studio Origin修复后，独立包80份载荷/技能文件与源码一致。实际Chrome渲染、FFmpeg编码、海报提取及验证PASS；四类含中文和空格的自定义绝对根有效，共享配置未变，默认工作根未创建。封存后独立恢复3项媒体、15个文件，配方和来源验证通过，改写批准目标拒绝。证据`/tmp/creative-installed-current-studio-contract-proof.json`。使用合成输入和测试批准，仍不代表真实产品、真实审批或ASC验收；版本与发布动作尚未完成。

## 当前源码全量回归

冻结源树回归886项执行、869项通过、17项跨文件系统用例跳过（559.742秒），301份源码指纹前后一致。证据`/tmp/creative-current-final-contract-regression-proof.json`和`/tmp/creative-current-final-contract-regression.log`。包含事务元数据、统一发布媒体清单、external实际checksum及观察文件输入修复。不是最终发布完成；长期证据登记/取回、真实产品、持久后端及ASC门禁仍未关闭。

当前源码真实跨文件系统专项：自建独立APFS临时卷，验证st_dev与源项目不同，17项正反向进程中断/公开CLI恢复测试全部通过（21.607秒，宿主任务23.049秒），退出0；测试卷成功卸载，映像保留为自有验收产物。证据/tmp/creative-current-crossfs-acceptance-proof.json及对应日志。该专项补充普通全量的17项独立卷跳过，不改写全量原始结果、不替代摘要证据链新增跨卷场景、Studio交互或生产后端验收。

原始观察证据/摘要跨文件系统矩阵：临时适配器复用当前RemoteObservationTests的16个搬迁SIGKILL用例，只将plan_relocation目标四根替换为自有独立APFS卷绝对目录，逐例断言st_dev不同；双向×意图/目录发布/配置安装/回执×resume/rollback，16项54.026秒通过，任务退出0、测试卷成功卸载。恢复后绑定记录字节、原始对象、摘要及私有后端保存/独立读回有效。证据/tmp/creative-current-evidence-crossfs-v2-acceptance-proof.json及日志；临时适配器/tmp/creative-crossfs-observation-matrix.py。首次选择器误包含retention测试，断言退出未执行用例，失败证据单独保留，不计通过。未更改冻结源树；临时后端不替代生产长期保存或Studio操作验收。

可纳入仓库的跨卷证据链测试候选独立验收通过：unittest discover只发现16项，无卷时16项明确skip；专用APFS卷下16项通过（53.754秒），任务55.209秒退出0并卸载卷。证据/tmp/creative-durable-evidence-crossfs-acceptance-proof.json与日志。候选仍在/tmp/creative-crossfs-test-candidate，待冻结全量结束后纳入仓库，不把临时候选声称为已提交门禁。

修正后冻结全量终态：943项执行、926通过、17项独立卷用例skip，686.563秒，退出0、306份源文件指纹一致；证据/tmp/creative-repaired-full-regression-proof.json及日志。此前17项已在专用APFS卷单独通过，不改写本次全量skip结果。随后只新增tests/test_cross_filesystem_observation_evidence.py（与真实卷16项成功候选字节一致）及修正技能external取回摘要，无运行时代码变更；新增模块无卷执行16项明确skip，插件结构及diff检查通过。新测试已进入仓库发现入口，真实卷候选验收见/tmp/creative-durable-evidence-crossfs-acceptance-proof.json。完整全量结果对应新增模块前，不能把959项称为已执行全量。

共同业务记录提交边界已统一：全部20类记录按各消费入口对改写字节核对原提交事件，run保留专门快照消费核验，其余19类共用读取检查；移除verify_artifact重复事件实现，媒体字节检查仍保留。RED在15个类别准确失败（/tmp/creative-common-commit-red.log）；首次组合测试因子场景残留改写commit-abandonments夹具导致13个后续子场景错误，已仅修正测试隔离，不放宽核心拒绝（/tmp/creative-common-commit-green.log）。最终70项8.632秒通过，/tmp/creative-common-commit-final.log。当前源码全量具体session63189运行，新包具体session6258构建中；此前943项全量/包对应旧源码，不证明本次修复完整通过。不自动回填记录或生成新兼容提交。

当前全量终态证据：`/tmp/creative-common-commit-full-regression-proof.json`；965项执行，22 failures、10 errors、33 skipped，696.712秒，309份源码指纹不变。随后三处状态诊断修复的当前源码5项回归通过，证据`/tmp/creative-status-diagnostics-source-regression.log`。旧全量失败报告保留，不把专项通过当作全量已修复。

共同提交消费者测试收敛：原有受影响23项通过，随后补充合法提交但字段无效的证明/媒体清单、独立依赖循环和外部定位字段覆盖，组合29项19.947秒通过（`/tmp/creative-commit-consumer-field-coverage.log`）。checksum准备负例使用新身份真实提交的测试记录，仍验证实际字节并保留已取回诊断文件。旧篡改场景断言更早提交拒绝；不放宽运行时校验。三处状态修复及本轮测试后重新执行冻结全量，结果待终态。

当前修复后新包：`/tmp/creative-repaired-commit-package.zip`，SHA-256 `cc25305d6b0ba9ef23a0f763a0aec1cd2e4925a65180382d7f80cf3146caf867`，236份载荷逐字节与冻结源码一致，打包门禁通过（`/tmp/creative-repaired-commit-package-proof.json`）。独立安装扩大回归session34168正在执行；修复后源码全量session92282仍运行，两者都尚无终态，不计通过。Studio发布详情不消费delivery_id，损坏计划状态的null身份不会被拼接为操作目标；列表仍按严格读取拒绝损坏计划。

修复后全量终态：969项，2 failures、33 skipped，690.270秒，310份源码指纹一致（`/tmp/creative-repaired-commit-full-regression-proof.json`）。独立包110项仅1 failure（`/tmp/creative-installed-repaired-commit-regression-proof.json`）。一处测试误改scope断言已恢复；另修复delivery状态对不存在记录保持HTTP404、已有损坏记录返回FAIL，实际6项6.485秒通过（`/tmp/creative-status-missing-record-regression.log`）。此前包字节早于该运行时修复，须重建，当前全量仍未通过。

当前最终状态包实际媒体验收通过（`/tmp/creative-final-status-installed-media-proof.json`及日志）：真实Chrome渲染、FFmpeg编码、封面提取、受管理登记/验证/封存及独立恢复，3类媒体、15个归档文件。含中文和空格的四类项目外自定义根被实际使用，默认工作根不创建，共享配置原文不变；脱敏工具回执及依赖、批准目标保留，修改恢复包目标被拒绝。使用合成场景与测试批准，不计两真实产品或ASC。首次沙箱因只读/bin/ps拒绝退出1，获运行时提权后重试退出0；冻结源码未变更。全量及独立安装组合仍待终态。

当前安装包组合终态：112项159.321秒通过、exit0，236份载荷一致（`/tmp/creative-installed-final-status-regression-proof.json`）。当前源码全量session32305仍存活，无终态，不计通过；不据安装包专项关闭完整交付。

当前包证据一致性复查完成：236载荷与当前冻结源码逐字节一致，安装112项及实际媒体生产/独立恢复证明绑定同一SHA-256（`/tmp/creative-final-status-package-proof.json`）。最新核心跨文件系统专项33项已启动，使用新建自有APFS映像、不同st_dev，session72030实测存活；结果待终态，执行后须确认卸载。源码全量session32305仍运行。

当前跨卷专项终态证据：`/tmp/creative-final-status-crossfs-acceptance-proof.json`及日志；自有临时APFS卷33项通过，任务83.246秒退出0，hdiutil卸载成功且mount.is_mount()为false。正式存储与完整Studio恢复仍未关闭。ADR目录示例同步当前独立remote-observations/observation-evidence/external-media/preparations记录，不再描述publication内嵌第二份回执权威。

冻结全量终态通过：969项758.069秒，33项独立卷跳过，310份源码指纹一致（`/tmp/creative-final-status-full-regression-proof.json`）；这些33项已有当期独立卷实际通过证据。后续非法ID修复在记录读取和异常转换前调用统一safe_id，3项永久测试纳入仓库，当前24项扩大回归18.836秒通过（`/tmp/creative-status-input-source-regression.log`）。无历史兼容或记录修复，最新包重建及最终全量尚待验证。

非法ID校验后新包构建及实际媒体验收通过：SHA-256 `406cf1e668fc4e62cfc39828c61dc29ec37e57bc3fe4316381ff89c61f4f1e85`，236份载荷一致（`/tmp/creative-status-input-package-proof.json`）。新包实际Chrome/FFmpeg/封面、四自定义根、封存及独立恢复15文件通过（`/tmp/creative-status-input-installed-media-proof.json`），合成场景与测试批准，不计真实产品。仓库外扩大115项组合session98652仍存活，结果待终态。旧入口扫描仅见--output-dir明确拒绝路径，无可执行旧工作流；不兼容读取旧记录。

非法ID校验后安装组合终态：115项142.270秒通过，exit0，236份载荷一致（`/tmp/creative-installed-status-input-regression-proof.json`）。另外仓库外真实CLI的delivery status/publication status/preparation-status三个入口拒绝../outside且退出2，配置与全部记录字节不变（`/tmp/creative-installed-status-input-cli-proof.json`）。最新源树含3项新增测试，最终全量尚需复验；本结果不替代正式存储、真实产品、ASC或发行。

当前运行时Studio已重新绑定原隔离夹具（http://127.0.0.1:3101，session38882）；浏览器读取维护记录，隔离操作检查PASS，永久删除计划检查NOT_EXECUTED，切换后旧结果替换；提交证据11记录/11意图显示Records verified。独立文件核对全部记录字节不变，44字节隔离对象哈希一致，purged回执不存在（`/tmp/creative-studio-current-read-verification-proof.json`，截图同名png）。未执行永久删除或中断写恢复；不能据此关闭完整Studio维护验收。

当前Studio可逆恢复实际浏览器验收通过（`/tmp/creative-studio-current-restore-proof.json`及截图）：独立临时46字节夹具，界面审查完整哈希/容量、填写测试操作者/原因、确认恢复，刷新历史为restored、执行效果PASS；独立核心核对恢复artifact哈希/大小，受保护候选仍有效，隔离副本保留。原待确认44字节永久删除夹具与计划未操作。该正常恢复流程不代表中断写恢复或永久删除验收。最新源树含非法ID校验与3项永久测试的冻结全量session33364已启动并确认存活，结果待终态。

实际普通恢复中断的Studio续执行验收完成（`/tmp/creative-studio-interrupted-restore-proof.json`及前后截图）：自有子进程首次恢复hardlink后SIGKILL退出-9，1/2对象恢复且无终态，UI实际效果FAIL且不报成功；通过原操作审查并续执行后2/2对象恢复、历史restored、效果PASS，artifact记录及隔离副本保持。发现普通restore_cleanup缺少恢复意图，部分恢复无法区分一般损坏；需补齐意图及INCOMPLETE诊断，不能关闭完整维护。临时TDD前置意图测试实际失败（`/tmp/creative-ordinary-restore-intent-red.log`），源码冻结未变更，待session33364全量终态后修复；不加入旧记录回填。

## 普通对象恢复持久化意图（2026-10-09）

恢复在修改对象前保存并同步不可变 `restore-intent`，绑定原隔离操作、清理计划和当前存储；终态绑定意图哈希。原操作中断时仍留在活动位置的有效对象可以建立保留副本，然后完成恢复。终态读取要求活动对象及保留副本完整；缺失意图的终态拒绝读取，不进行历史补造。

中断状态查询返回 `INCOMPLETE/RESTORING`，不声称完成；开始恢复后拒绝新永久清理计划和此前建立的清理计划。专项38项通过，包含实际SIGKILL后沿用原意图恢复、同步失败前不修改对象、篡改意图拒绝和保留副本丢失拒绝。覆盖源码核心及Studio后端，不替代新安装包、浏览器或完整维护验收。扩大组合回归日志：`/tmp/creative-restore-intent-integrated-regression.log`，扩大组合回归59项通过（17.090秒）。

安装包证据：`/tmp/creative-restore-intent-package-proof.json`、`/tmp/creative-installed-restore-intent-regression-proof.json`、`/tmp/creative-installed-restore-packaging-regression-proof.json`。首轮失败证据保留，未将其改写为全绿。

当前安装包Studio实际浏览器中断恢复通过：两个合成对象在首次活动链接后真实SIGKILL，界面显示INCOMPLETE/RESTORING且永久清理入口禁用；按原操作恢复后PASS/restored，独立核验原意图字节未变、两个活动对象及两个保留副本完整。证据`/tmp/creative-studio-installed-restore-proof.json`，截图`/tmp/creative-studio-installed-restore-completed.png`。此项不替代完整维护与真实产品验收。

新增恢复失败专项覆盖意图写入失败不改对象、活动对象损坏原样保留及终态意图哈希篡改拒绝；44项组合通过（5.801秒）。随后启动冻结源码全量验证，日志`/tmp/creative-restore-intent-full-regression.log`，对应进程仍待终态；当前包实际媒体复验也已启动，不提前计为通过。交付收敛审计不再复制当前快照，以本文件为单一状态权威。

恢复意图更新后的安装包实际截图/15秒视频/封面生产、封存及独立恢复已通过，3个媒体角色、15个归档文件验证，证据`/tmp/creative-restore-intent-installed-media-proof.json`。仅合成画面与测试批准，不代表真实产品或人类批准；临时媒体随测试清理，保留证据报告。冻结源码全量仍在运行。

Levelory真实采集已启动：独立源树副本保留用户当前营销测试内容，另在副本加入剪贴板changeCount保护；依赖恢复及工程生成已成功，使用LeveloryUITests专用应用身份执行单一中文快速粘贴场景。原仓库未修改。当前采集进程尚待终态，不计为真实媒体通过；管理attempt为62f2c8bfebbd436b92c1611da82a68bf，日志`/tmp/creative-levelory-quick-paste-zhHans.log`。Xcode MCP仍未获工作区权限，此处证据仅来自仓库定义的shell备用入口。

Levelory首个真实中文采集通过：仓库定义shell入口单项UI测试Passed（1通过、0失败、0跳过），实际窗口920×940，视觉检查搜索及类型标签为中文，示例内容为确定性测试数据；登记capture与依赖回执并结束采集attempt。原用户测试文件哈希未变。证据`/tmp/creative-levelory-real-capture-proof.json`。仅关闭中文快速粘贴单一checkpoint；其余场景、视频、真实批准及ASC仍未完成。

剩余9个Levelory中英文真实采集场景已在新租约attempt a087fad8793e4f7b9e71f3653daceea4中启动，日志`/tmp/creative-levelory-matrix-capture.log`，待终态及逐图审查。ASC只读复查当前en-US预览仍为COMPLETE、时间码00:00:05:00、previewImage 0×0；原始字节SHA-256与先前一致。脱敏证据`/tmp/creative-poster-latest-readonly-summary.json`。不声称封面修复或重新上传。

Levelory剩余九场景采集结束，9通过、0失败、0跳过，取得9份真实窗口截图并逐张视觉审查；连同此前中文快速粘贴共10个中英文原始checkpoint。全部注册原图哈希、尺寸及依赖回执，结束各自attempt。中文主窗口/过滤器仍有Search Clips、Agent Relay、Copy Result和状态文本未翻译，合集侧栏名称截断；记录为审核缺口，原始像素未修改，不判定可发布。证据`/tmp/creative-levelory-real-matrix-proof.json`。截图设计生产、视频、正式批准、封存/持久取回及ASC仍待完整验收。

真实Levelory十份来源已按en-US与zh-Hans分别映射至新配置，复制前后SHA-256一致，不使用英文UI冒充中文来源；完整十帧设计候选生产已启动，尚待终态和视觉审查。证据`/tmp/creative-levelory-real-source-map.json`。

Levelory真实十帧设计候选生成并技术验证PASS（2880×1800，无alpha），逐帧视觉检查完成，无文案裁切或空白输出；产品UI翻译和侧栏截断缺口保留。受管理design-review绑定10份输出与10份原始来源，开放incident保护证据；无人工批准、封存或远端写入。候选dd39002fab0344cd952f7aa6b31b14e3，证据`/tmp/creative-levelory-real-design-review-proof.json`。

待发布版本统一为0.3.0（两个插件声明及仓库校验器），未发布。声明校验及完整打包smoke通过；236份载荷与此前已验证包相比仅两个版本声明变化，运行时字节未变。证据`/tmp/creative-redesign-0.3.0-package-proof.json`。发布说明位于`docs/releases/0.3.0.md`，保留不兼容合同及未完成门禁；此前984项源树全量早于版本声明变更，不冒充远端CI。

## 原采集记录到设计输入的依赖（2026-10-09）

新增公开 `input import --artifact <capture-id> --actor <actor>`，与 `--source` 互斥。已登记截图必须具有完整 capture 角色、有效对象和成功采集终态；新输入记录保留原 capture 的依赖，不用同名普通文件代替来源身份。生产继续消费受管理输入别名，保留这条依赖链。

缺失入口的 RED 三项按预期失败；实现后连同生产及配置组合十五项通过（7.542秒）。第一次组合因测试原 capture 未设置封存要求的相对 logical_path 失败，仅修正测试来源路径后通过，未放宽封存校验。日志 `/tmp/creative-capture-import-red.log`、`/tmp/creative-capture-import-green.log`。

Levelory 十份原始截图已用该入口实际导入，逐份验证哈希与原 capture 依赖，证据 `/tmp/creative-levelory-original-capture-import-proof.json`。此前设计候选未重新生产，不声称它已具有新增依赖。当前运行时发生变化，此前984项全量及0.3.0包不能作为本次变更后的最终验证；需重新打包和最终回归。

新来源关联候选已实际重建：`bd3cea1885114be4ab503f035bcfc855` 技术验证 PASS，10 份原 capture 全部进入候选依赖闭包；10 张输出与此前逐帧审查版本 SHA-256 完全一致。证据 `/tmp/creative-levelory-linked-design-provenance-proof.json`。不改变既有翻译/侧栏审核缺口，不构成人工批准，未封存或上传。

新增失败采集和 partial 截图拒绝专项，当前组合17项7.723秒通过。新包 `/tmp/creative-capture-linked-0.3.0-package.zip` 完整打包 smoke 通过；独立安装组合结果以 `/tmp/creative-capture-installed-regression-proof.json` 为准。此前984项全量早于此行为变更，最终回归仍待执行。

## 真实窗口视频采集推进（2026-10-09）

隔离 UI 测试新增确定性过滤操作旅程，原仓库测试文件 SHA-256 仍为 `8ada8acb6afedadcb0586ec822600b76a99f3927f72f84897c2502b5997a6887`。v1 因测试沙箱拒绝写公共临时目录，测试退出65，录屏未启动；失败摘要 `/tmp/creative-levelory-video-summary-v1.json`。v2 已到达测试自身目录 rendezvous，但窗口查询目标错误；后续查询确认真正 UI 应用是 `me.rbbtsn0w.levelory.dev`，不是支持模块 `me.rbbtsn0w.levelory.ui-testing-support`。既往把后者描述为运行应用的记录应按此事实纠正。宿主无法向测试容器写开始标记，v2 继续保留失败证据，不计通过。

原 v2 UI 进程及 xcodebuild 经宿主只读进程查询确认已不存在后，v3 改用测试内部延时安排操作，并针对显式 Dev 窗口录制45秒原始take；不存在生产应用启动或桌面回退。当前运行 `229df840ca0b44838ebc594c03509888`，工具会话14647，证据 `/tmp/creative-levelory-real-video-execution-v3.json` 和对应 UI/native 日志。尚待终态、真实操作帧审查与后续编码/封面，不能计为视频验收通过。

真实视频 v3 已终态：UI测试退出0，但录屏退出2，原始take实际47.268333秒，计划45秒，严格时长校验拒绝；无成功录屏回执，失败attempt保留partial产物。证据 `/tmp/creative-levelory-real-video-execution-v3.json` 和 `/tmp/creative-levelory-real-video-native-v3.log`。不把UI成功计为视频成功。

依据本机ScreenCaptureKit SDK `SCStream.h` 的录制输出移除契约，执行器在计划等待结束后先 `removeRecordingOutput`，再 `stopCapture`，避免流关闭延迟继续计入文件。六项录屏适配器/探测/执行身份回归通过（0.416秒），不足以证明原生时长修复。v4 已编译并收到RECORDING_STARTED，当前运行 `b687b8872da949bba65957e3d5b9339b`、会话69480，原生实测终态仍待验证；严格校验未放宽。当前运行时代码再次变化，既有包不代表此Swift变更。

v4 终态仍失败，但具体原因已改变：UI退出0、录屏退出2；严格时长校验已通过，随后平均帧率校验拒绝。原生录制对最低帧间隔的声明不等于恒定输出帧率，静态/动态窗口仍可能产生变帧率视频。保留先移除录制输出的Swift时长修复，但不声称整体录屏通过；原始失败take保留，下一步需设计真实take到恒定帧率输出的受管理规范化和证据关联，不能直接放宽成功门禁。

录屏规范化新增：原生take保留为 `.native.mov`，原生校验单独允许有效变帧率、仍检查范围/尺寸/编码/时长；FFmpeg显式转换恒定帧率后再次执行严格输出校验，不补帧延长过短采集。回执绑定两份文件哈希、原生probe和编码工具身份，受管理记录形成规范化capture → 便携回执 → 原生capture依赖；失败时保留两类partial对象。三项RED按缺少模块失败，当前10项相关回归通过（0.847秒），包含实际FFmpeg转换和私有工具字段拒绝。日志 `/tmp/creative-recording-normalization-integrated.log`。

真实v5复验已启动，运行 `fb72c335c37042a28b7d534f52dba00a`、会话4144；最终成功仍待工具终态和操作画面检查。规范化元数据工具字段验证在采集过程中追加，因此此次操作运行不能替代最终冻结源树回归或安装包验证。

v5 终态仍失败：UI退出0，原生take47.933333秒再次越过严格时长容差，规范化未开始。v4单次通过时长不能证明原生结束边界稳定；不将其写成已完全修复。原失败attempt与take保留。

原生/标准化合同进一步拆分：原生校验保留最多10秒额外尾段，拒绝低于计划减原有容差的截断录像及更长异常尾段；标准化不延长短录像，使用显式时长裁切和CFR，标准化结果仍执行原严格时长/帧率校验。尾段预算是明确的新采集合同，不是对最终物料门禁的放宽。新增边界负例后12项通过（0.874秒）。真实失败take的独立转换证明位于 `/tmp/creative-levelory-real-native-normalization-proof.json`；仅验证真实字节转换，不改变失败采集终态或补造成功回执。新完整原生采集、输出审查、打包及全量仍待验证。

真实 v6 采集已通过：UI和录屏均退出0；运行 `8f9e3922e6e4488b80a07b83093ffbdc`，标准化capture `eb818a5df150460e8c6509e9b23986af`。原生take、转换工具/哈希与便携回执依赖登记有效，未将以前失败take补造为成功。

完整新包smoke及独立安装29项9.376秒通过：SHA-256 `0bfcd30162153ab8096759f6416548bd8764600a60e1ff7386a352603cc60cbf`，证据 `/tmp/creative-normalized-installed-regression-proof.json`。不替代本次改动后的全量回归。

真实录像连续区间17–37秒已编码为20秒en-US预览：1920×1080、30fps、H.264/AAC48kHz双声道；六帧接触表观察到选择条目、打开过滤器、选择Uppercase及结果。初始12秒封面显示菜单，保留该尝试，另提取17秒完成结果为待审封面；preview `f7b1d22b5df14c3f8d723fec10ad3b9f`，poster `10a879729c6645bea211b64876bb2876`。受管理agent review及开放incident保护依赖，标记NEEDS_REVIEW：原生宽高比适配留下右侧黑边，尚需编辑构图审查。证据 `/tmp/creative-levelory-real-preview-proof.json`；无人工批准、封存或远端写入，仅关闭真实生产技术链路，不关闭Levelory完整发行验收。
