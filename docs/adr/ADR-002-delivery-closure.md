# ADR-002 交付收敛审计

## 当前状态权威

当前完成项、待办项和最新验证范围统一维护在[ADR-002 实施状态](ADR-002-implementation-status.md)。本文件保留交付门禁及历史审计证据，不重复维护当前快照；历史通过结果不能替代最终源码或正式验收。


本文件把ADR-002完整目标转为交付门禁，不缩小范围，不替代原ADR。用户明确要求推倒重新设计，不考虑历史兼容：新合同为唯一执行权威，旧记录不迁移、不兼容读取，旧自由写入入口按退出或移除处理。已有文件不自动删除；删除产物仍须按授权维护流程。当前结论：未完成，不可发布为完整统一方案。没有可信完成百分比；单项测试、包校验和代码存在不证明业务能力闭环。

最新摘要安装包：`/tmp/creative-summary-contract-package.zip`，SHA-256 `9f2380c7abf0863a14d42e4bb7c83aa6c42e0c344370d84f215ca32c7c4d6b7d`；234个载荷文件一致，仓库外43项证据链测试通过（`/tmp/creative-installed-summary-regression-proof.json`）。另有源树模拟敏感回执专项通过，证明私有token/path不进入Git导出、原始对象字节保留。此专项新增于安装包测试复制后，不冒充该43项集合中的测试。生产后端和真实远端验收仍未关闭。

摘要字段与错绑补充验收：合法提交但缺失summary身份/哈希或跨观察引用摘要时，持久化在创建后端目录前拒绝，无历史回填。8项针对性测试和47项观察/引用保护/共同记录版本组合通过（`/tmp/creative-summary-binding-regression.log`）。该诊断修复发生于最新摘要安装包之后，安装包仍待最终重建复验，不沿用旧43项包结果声称当前源码完整通过。

最新摘要包补充验证：`/tmp/creative-summary-final-package.zip`（SHA-256 `324ecb4a45c8717c38877b8f605acad36e4f2761a91d2df4e362351d132be979`），234个载荷文件一致，仓库外46项HTTP/CLI/摘要取回/敏感原文隔离/缺失字段/错绑/取消/SIGKILL组合测试通过（40.970秒，`/tmp/creative-installed-summary-final-regression-proof.json`）。原文登记后摘要失败/取消有专项，重试身份独立、旧原文和观察字节不变；搬迁往返及完整维护矩阵、生产后端和真实产品仍待验收。

证据链四根往返专项通过（4.915秒）：实际Git暂存忽略门禁、forward prepare/switch、搬迁后私有证据持久化/readback、reverse prepare/switch及返回后清理引用保护。原始证据和摘要artifact记录逐字节不变、关系与哈希有效。测试：`test_evidence_and_summary_survive_four_root_relocation`。仅临时项目同文件系统A→B→A，不代替重复往返/跨文件系统/全部中断点或生产后端验收；当前安装包46项复制集合早于此新增测试。

摘要证据重复往返已补齐：同一项目四类根实际A→B→A→C→A，9.535秒通过；两个物料记录与最初字节一致，最终外部定位与摘要哈希仍可导出。证据：`/tmp/creative-summary-repeated-relocation.log`。此前单次往返结果保留为历史；本轮仍为同文件系统，不能证明跨文件系统及搬迁中断后的摘要链恢复。

摘要证据搬迁进程中断恢复补充通过：配置安装后SIGKILL的公开CLI resume/rollback两项（6.353秒），目录发布后SIGKILL的公开CLI resume/rollback两项（5.414秒）。恢复后原始证据与摘要验证、关联字节一致及持久化/readback通过。证据：`/tmp/creative-summary-relocation-sigkill.log`、`/tmp/creative-summary-relocation-directory-sigkill.log`。仅正向两个切点，不冒充反向/全部切点、跨文件系统或真实产品运营验收。

摘要证据反向搬迁中断恢复4项通过（21.515秒）：目录发布后及配置安装后SIGKILL，公开CLI续执行/回滚均保留关联字节并通过原文、摘要及持久化读回核验；`/tmp/creative-summary-reverse-relocation-sigkill.log`。共用夹具调整后正向4项复验通过（12.717秒，`/tmp/creative-summary-forward-relocation-shared-fixture.log`）。范围为双向两个切点；尚未覆盖所有提交切点、跨文件系统、Studio中断操作或真实产品运营。

证据链迁移意图/回执切点8项通过（36.522秒，`/tmp/creative-summary-intent-receipt-sigkill.log`）：双向switch-intent提交后、switched回执写入前SIGKILL，公开CLI resume/rollback恢复后证据关联、原文、摘要及持久化/readback有效。结合前两组，当前临时同文件系统证据链覆盖双向×四个切点（意图、目录发布、配置安装、回执）×两恢复方向，共16个场景；不把该集合称作所有文件系统/准备/维护中断点。独立包早于本轮新增测试，跨文件系统和Studio恢复仍未验收。

证据链维护隔离/恢复专项通过（0.902秒，`/tmp/creative-summary-quarantine-restore.log`）：失败采集物料按0天试制保留计划隔离并恢复；观察引用的原文和摘要未被选中、始终可校验、artifact记录不变。诊断类别使用独立保留期，本专项不缩短该策略。尚未覆盖维护中断/永久清理、Studio交互及跨文件系统。

观察引用保护下永久清理正常路径通过（1.055秒，`/tmp/creative-summary-quarantine-restore-purge.log`）：仅临时可丢弃失败采集物料隔离→恢复→重新隔离→0天计划永久清理；活动对象与隔离副本均移除，受保护原文/摘要物料与记录仍有效。本轮未清理用户/真实产品文件；不替代永久清理中断恢复及Studio操作验收。

观察证据引用下普通永久清理SIGKILL三切点通过（3.478秒，`/tmp/creative-summary-purge-sigkill.log`）：purge-intent、purge-file-0检查点提交后及purged回执前终止，公开CLI按原计划恢复，INCOMPLETE→PASS；原文与摘要物料记录不变、哈希和绑定有效。仅临时失败采集物料永久清理，不替代Studio/跨文件系统/搬迁副本永久清理验收。

当前包恢复矩阵独立复验：同一摘要最终包SHA-256 `324ecb4a45c8717c38877b8f605acad36e4f2761a91d2df4e362351d132be979`，234个载荷文件仍与当前源码一致；仓库外67项测试通过（130.592秒，`/tmp/creative-installed-summary-recovery-matrix-proof.json`）。本轮复制当前测试集合，包含新增重复四根往返、双向16切点恢复组合、清理引用保护及普通purge三切点，不再沿用旧46项集合。仍是合成临时项目，不证明生产后端、跨文件系统或真实ASC；当前源树全量回归仍等待终态。

摘要改造源树全量回归已结束：939项执行、922项通过、17项跨文件系统用例跳过，685.216秒、304份指纹一致（`/tmp/creative-summary-full-regression-proof.json`）。之后项目身份/运行快照审计复现两个缺口并修复：无效project.id在内核初始化前拒绝；消费run核验配置快照/有效配置哈希、记录与原提交意图绑定，保留工作流专项诊断。新增失败测试先复现，实际源码42项配置/生命周期/工作流/重复迁移测试通过（13.737秒，`/tmp/creative-run-identity-green.log`）。该修复后当前源码及安装包扩大验证仍待完成，939项不冒充本次修复后全仓通过。

项目身份/运行快照扩大消费回归107项通过（144.661秒，`/tmp/creative-run-identity-consumers.log`），覆盖封存、publication、完整观察证据及Studio；发生于项目身份共享函数提取之前。随后新增跨入口失败合同，内核、配置compose和Studio check_config共用require_project_identity；38项配置/生命周期/工作流合同通过（1.080秒，`/tmp/creative-project-identity-shared-green.log`）。无效身份在写入前一致拒绝，有效显式Unicode身份保留，不从目录推断、不生成旧记录兼容身份。当前共享函数后的Studio/公开CLI和打包回归仍待终态。

共享身份规则后Studio/配置验证：实际26项Studio/分层输入保存/安装载荷测试通过，但组合命令因误写不存在的test_configuration_readonly_cli模块退出失败；保留原日志`/tmp/creative-project-identity-studio-config.log`。正确test_configuration_cli另行2项通过（0.169秒，`/tmp/creative-project-identity-config-cli.log`）。不是将失败命令报告为成功；缺失模块不计已执行测试。当前包已重建，独立安装行为仍待验证。

当前身份/快照包独立复验73项通过（128.482秒，`/tmp/creative-installed-run-identity-regression-proof.json`）；236个载荷文件一致，包SHA-256 `f5b8c5de0ce457ee18b054dc379c27c7ba2bf520613fb18812745954dd159f9d`。含统一项目身份及运行快照合同、证据/恢复矩阵；当前源树全量仍等待终态。录制前置最新只读预检退出0、窗口列表为空：CGPreflight屏幕权限已通过，未请求新权限、未启动或录制应用；`/tmp/creative-native-permission-latest-proof.json`。旧权限缺失证据已过时，真实捕获现需可用Levelory Dev窗口及确定性场景，不能把空窗口列表当录制成功。

## 当前任务 Checklist

状态以当前证据为准。已勾选只代表该条明确范围；六组完整能力均尚未整体关闭，不据测试数量计算完成百分比。

### 已完成并有对应验证

- [x] 从最新远端main基线50a6414建立feat/unified-artifact-lifecycle-v2；原工作区和独立备份保留。
- [x] 明确不考虑历史兼容；旧任务引擎、自由verify/publish及旧任务入口移除，独立安装包确认拒绝。
- [x] 四类根目录统一解析，项目/本机覆盖及Git保护接通；正反向搬迁、重复往返和公开恢复入口具有专项证据。
- [x] 真实独立APFS卷跨文件系统中断矩阵17项通过；四项实际文件系统权限验收通过。仅覆盖已列场景。
- [x] 候选、验证、设计批准、上传批准、封存和提交审计接通；损坏批准阻断执行，只读查询保留诊断。
- [x] 普通Git、LFS、external在临时后端和临时远端完成独立取回验证；不代表生产远端验收。
- [x] 引用保护、项目保留策略、隔离、恢复及永久清理接通；已有进程中断、替换和恢复专项证据。
- [x] CLI/HTTP/Studio读取统一策略；实际浏览器确认项目保留期、隔离期和未知预算呈现，不执行清理。
- [x] ASC交接计划、独立上传批准及官方预览响应转换接通；处理完成不冒充封面可加载。
- [x] 工作流快照补齐前的安装包独立解包验证80份载荷/技能文档一致；公开CLI验证批准诊断与执行拒绝，缓存载荷问题已修复。该包不代表最新源码。
- [x] 最近批准修复40项组合、11项CLI诊断回归通过；分段全量计划全部8段已完成：852项执行，835项通过、17项跨文件系统用例明确跳过，源指纹一致。

- [x] 临时Git squash合并后按实际提交重新取回并绑定；旧远端不可取回的审查SHA拒绝，新计划不继承旧上传批准。专项及相关8项回归通过；不替代托管PR验收。

- [x] 当前差异范围清单已刷新：274个路径、68个跟踪变更、206个未跟踪文件，均在预期目录；逐文件保存类型及当前字节哈希。证据`/tmp/creative-current-diff-inventory.json`。仅为当次文件范围审查，不代表正确性、安全审查或发行完成。

### 继续完成的工程与验收

- [x] 核心记录非普通文件拒绝修复后102项扩大回归及独立安装CLI验证通过，安装包已更新；此前852项分段结果只代表修复前源码。

- [x] 补齐run启动时的工作流版本及实现身份快照，缺失或未知工作流版本拒绝执行；相关56项回归通过（7.032秒，`/tmp/creative-workflow-snapshot-green.log`）。
- [x] 工作流快照合同文档及独立安装包专项验证完成；搬迁往返、分层封存及实现身份相关23项回归通过（43.366秒）。新包独立解包运行公开CLI，证据`/tmp/creative-installed-workflow-snapshot-proof.json`；仍为合成输入，不代表真实产品验收。
- [x] 工作流快照及观察证据变更后的本地分段全量回归：固定清单858项、8段全部完成，841项通过、17项独立卷用例跳过；测试覆盖一致，296份源码指纹及文件集合未变。证据`/tmp/creative-current-contract-regression/summary.json`。该结果对应视频路径整改前源码，不代表最新视频改动、单进程全仓、远端CI或真实产品验收。

- [x] 完成8段回归并核对852个测试ID覆盖；835项通过，17项无独立卷跳过，与此前实际APFS证据单独报告。分段执行不证明单进程全仓或远端CI通过。
- [ ] 逐条完成ADR实体/schema、全部执行者身份、依赖失效与控制日志执行验证审计。
- [ ] 通用导出的`with_video`路径统一到受管理Preview工具身份、回执和归档依赖合同；直接编码入口已替换为统一执行器，回执/验收帧依赖已登记，相关29项回归及2项合同测试通过；海报接入、失败诊断、实际编码及独立包专项见下文；完整真实产品及远端验收仍待完成。详见实体合同审计。
- [x] 通用视频导出按`posterRequired`复用受管理海报生产，候选同时包含视频及海报；时间码帧率解释与无效时间码创建run前拒绝已核验。相关29项回归及4项合同测试通过（`/tmp/creative-export-poster-green.log`、`/tmp/creative-export-poster-boundaries.log`）。上述专项后续已完成，见下文；真实产品验收仍待完成。
- [x] 通用导出失败/取消登记结构化诊断与已产生的视频、验收帧部分产物；失败和取消分别结束，不创建候选。相关41项回归通过（13.388秒，`/tmp/creative-video-failure-green.log`），异常继续向调用方报告。此证据不替代原生真实产品录制或进程强制中断验收。
- [x] 通用导出实际Chrome截图、FFmpeg视频编码、指定帧海报提取及内核验证通过：候选含screenshot/preview/poster，10个依赖节点，回执工具身份完整且无本机项目路径。证据`/tmp/creative-real-video-export-proof.json`。输入为合成场景；不代表两个真实产品、人工批准或ASC验收。首次沙箱执行被进程列表读取权限阻止，经宿主权限机制执行后通过。
- [x] 最新视频改造包独立解包验收通过：80份载荷/技能文件与源码一致，实际渲染/编码/海报、封存及独立恢复均通过；恢复包3个媒体产物、15个文件，媒体/配方/依赖核验通过。证据`/tmp/creative-installed-unified-video-proof.json`。批准记录仅为合成测试数据；不代表真实人类批准、持久远端取回或ASC验收。
- [x] 最新独立包使用四类项目外自定义绝对根（空格/中文路径）实际完成生产、封存和独立恢复；共享配置字节不变，默认工作根未创建。另以公开CLI登记三条合成观察并导出到自定义publicationRoot，原证据哈希保留。证据`/tmp/creative-installed-custom-root-proof.json`及`/tmp/creative-installed-custom-publication-proof.json`；不代表真实产品、迁移/维护全矩阵或真实远端验收。
- [x] 远端observation实际证据哈希的核心、CLI及ASC转换合同已补齐；缺失、错误格式、改动字节及无哈希历史记录拒绝。相关30项回归通过（16.421秒，`/tmp/creative-observation-evidence-final.log`）。核对范围见[实体合同审计](ADR-002-entity-contract-audit.md)。
- [x] 观察证据变更后的独立安装包验证通过：80份载荷/技能文件一致，公开CLI拒绝缺失和改动证据，三条观察登记及导出哈希一致。证据`/tmp/creative-installed-observation-evidence-proof.json`；输入为合成计划与响应。
- [ ] 原始观察证据长期取回及真实远端验收。
- [x] 观察记录消费核对原提交事件，改写事实不能用于远端成功判定；实际导出在写出文件前预检观察完整性。失败用例复现后修复，相关37项回归通过（17.140秒，`/tmp/creative-observation-integrity-repaired.log`），改写观察保留且不产生交接文件。缺失原始证据长期取回仍未关闭。
- [x] 设计批准固定发布目标；改写run目标后状态为STALE且封存拒绝，独立归档核验拒绝与批准不一致的目标。两项失败用例复现后修复，相关33项回归通过（`/tmp/creative-design-target-green.log`）；目标合同最终回归及状态专项证据另见`/tmp/creative-design-target-final.log`和`/tmp/creative-design-target-status.log`。缺失目标绑定不自动补写；真实ASC应用/版本关联仍由官方执行方核验。
- [x] Git/external发布计划创建与消费统一校验目标字段非空字符串及交付平台一致性；上传批准、实际交接导出和external准备不会跳过该检查。三个无效目标场景复现后修复，相关32项回归通过（43.519秒，`/tmp/creative-publication-target-green.log`），拒绝时不创建上传批准或交接文件。真实ASC应用/版本归属仍待官方执行方核验。
- [x] 最新目标合同包独立解包核对80份载荷/技能文档，并实际完成自定义根中的渲染、编码、海报、封存及独立恢复；批准目标保留，改写恢复包目标后独立核验拒绝。证据`/tmp/creative-installed-target-contract-proof.json`。输入及批准为合成测试数据，不代表真实产品或ASC发布。
- [x] 本地/external归档共享交付身份检查；external消费从绑定Git提交取得清单并核对哈希及修订、项目、目标、父修订。改写交付记录不能重标外部归档或生成批准/交接文件。两个失败场景复现后修复，相关30项回归通过（17.588秒，`/tmp/creative-external-identity-green.log`）。最新独立包及真实持久后端仍待验收。
- [ ] 补齐剩余权限、路径替换及维护协调场景，完成Studio中断/永久清理执行验收。
- [ ] 验证实际持久后端、真实PR/合并后提交绑定、干净克隆及CI只读门禁。
- [ ] 两个真实产品分别完成截图/视频/封面生产、批准、封存、取回及运营恢复演练。
- [ ] 由ASC完成真实交接执行及远端复查，分别核验上传、处理、关联、播放和封面，不重复上传。
- [ ] 完成最终差异审查、发行版本及远端CI；按既有授权完成提交、合并、push、插件更新和安装后复验。
- [x] Studio拒绝外部Origin读取媒体及配置，移除媒体通配CORS头；同源及无Origin读取保留。失败用例复现后修复，相关38项回归通过，实际Chrome渲染、视频编码及海报提取验证PASS（合成输入）。证据`/tmp/creative-studio-origin-green.log`及`/tmp/creative-studio-origin-render-proof.json`。
- [x] 移除Studio对旧`.creative/assets/`的隐藏目录访问例外；专项确认返回404且磁盘旧文件保留，不提供历史目录特殊服务入口。验证包含于上述38项回归。

- [x] 最新交付身份及Studio修复后的独立包核对80份载荷/技能文件一致；实际完成四类自定义绝对根中的截图、视频、海报生产及封存恢复，3项媒体、15个归档文件验证通过，目标改写拒绝。证据`/tmp/creative-installed-current-studio-contract-proof.json`，包SHA-256 `761a2685af1105d734b2c3a4c51d541fa37fdfe6208c26d2f278e257d1e3f557`。合成输入及测试批准，不替代真实产品、远端或最终发行验收。

- [x] 工作区身份及配置权威元数据被替换为FIFO时，写入入口不再挂起；锁拒绝非普通文件并核对打开前后inode。实际子进程复现三个失败场景后修复，相关43项回归通过（`/tmp/creative-metadata-fifo-green.log`）。不代表全部路径替换/并发协调矩阵；此前安装包早于本修复。

- [x] 统一事务入口元数据修复后的扩大回归通过92项（115.388秒），覆盖自定义正反向执行、迁移恢复/CLI、重复往返、维护协调、保留、隔离及purge进程中断和日志读取。证据`/tmp/creative-transaction-recovery-regression.log`；不代替未覆盖的完整矩阵或真实运营验收。

- [x] Git/LFS/external取回证明消费统一要求来源验证严格为true；缺失、false或错误类型拒绝状态确认、上传批准及实际交接。四个失败场景复现后修复，相关21项回归通过（29.567秒，`/tmp/creative-retrieval-provenance-green.log`）。不回填旧记录；生产持久远端仍待验收，此前独立包早于本修复。

- [x] 普通Git/LFS计划消费重新比对封存媒体有序列表、路径、artifact身份、角色、SHA-256、上传checksum及预览海报时间码；五种改写失败场景复现后修复，相关30项通过（23.584秒，`/tmp/creative-publication-assets-green.log`）。拒绝批准及实际交接；external对应媒体清单消费仍需独立审计，当前独立包早于本修复。

- [x] external发布消费从绑定Git清单与配方核验媒体有序列表、路径、artifact身份、角色、SHA-256和海报时间码；四种改写失败场景复现后修复，相关13项通过（`/tmp/creative-external-assets-green.log`）。上传checksum此阶段仅格式核验，真实字节对应检查仍需在hydrate后补齐；不将该条作为完整external媒体消费关闭。

- [x] external hydrate后的准备及状态查询流式核对实际媒体SHA-256和上传MD5，检查普通文件及读取期间身份变化；错误checksum不创建准备回执，取回字节保留用于诊断。失败复现后修复，相关17项通过（11.641秒，`/tmp/creative-external-checksum-final.log`）。提交元数据阶段仍仅核验checksum格式，实际字节核验在hydrate后执行；生产后端仍待验收。

- [x] external校验补充真实大文件与准备状态边界：超过30MiB媒体通过流式校验，字节改动拒绝，FIFO在打开前拒绝；同时改写计划与准备checksum/计划哈希仍被实际媒体检查判为FAIL。相关14项及新增FIFO后7项通过（`/tmp/creative-external-media-boundary.log`、`/tmp/creative-external-media-boundary-final.log`）。不代表生产媒体/后端验收。

- [x] 发布媒体清单构造规则统一：Git/external计划创建及消费共用publication_assets，保留路径基准差异；上传MD5改为流式读取。相关23项通过（17.524秒，`/tmp/creative-unified-publication-assets.log`），包括目标/媒体拒绝、external准备与合并提交绑定；未缩小真实后端及产品验收范围。

- [x] 公开观察登记拒绝FIFO输入，不再挂起；观察JSON及证据读取使用普通文件/身份核验和30MiB上限，在事务前失败不创建工作区。子进程失败复现后修复，相关24项通过（12.173秒，`/tmp/creative-observation-file-green.log`）。长期证据存放/取回仍未关闭。

- [x] ASC响应转换入口与观察登记共用普通文件/身份及30MiB输入边界；输入预检先于事务，FIFO响应拒绝且不创建工作区，响应哈希仍绑定原始字节。失败用例后相关转换/CLI回归通过，证据`/tmp/creative-normalization-file-green.log`；不代表长期存放或真实远端验收。

- [x] 本地原始观察证据受管理接入：retain_observation_evidence核对实际字节后使用交付所属run的独立attempt、artifact及不可变关联，原观察不变；关联进入统一记录审计和清理引用保护。相关47项通过（14.172秒，`/tmp/creative-retained-evidence-green.log`）。仅核心本地登记；CLI/Studio、持久定位、脱敏导出、独立取回及中断全矩阵仍待完成。886项全量发生于本次新增能力之前。

- [x] 公开publication retain-evidence接通统一核心，匹配证据原始字节及原观察的准确计划/目标；计划改变在attempt前拒绝，私有原文不进入publicationRoot。相关22项通过（14.978秒，`/tmp/creative-retain-cli-final.log`）。测试夹具字段错误已修正；持久后端/Studio/脱敏取回仍待完成。

- [x] 观察证据核心持久接口复用persist_managed，核验观察/证据artifact绑定，返回既有不可变外部版本记录；临时文件系统后端实际独立取回原始字节，定位无本机路径，相关48项通过（17.026秒，`/tmp/creative-evidence-persistence-green.log`）。仅核心接口及临时后端证据；公开持久入口、脱敏导出/干净消费端及生产后端仍未关闭。

- [x] publication persist-evidence公开入口接通，复用本机命名backend和现有外部版本存储；CLI实际写入后在独立目标取回核对原字节，reference不导出本机路径。相关26项通过（16.538秒，`/tmp/creative-evidence-persist-cli-green.log`）。临时后端不代表生产持久性，Studio及便携脱敏证据取回仍待完成。

- [x] 发布导出追加受管理观察证据的严格外部版本定位，绑定观察/计划/原始哈希，不复制原文及本机路径；前置核验先于交接文件写出。相关27项通过（18.075秒，`/tmp/creative-evidence-locator-green.log`）。仅定位导出，非法字段全矩阵、干净消费端/Studio及生产后端仍待完成。

- [x] 观察证据定位导出负向验收：私有root字段、非安全backend、错误version/hash、bool大小/schema及未知provider均拒绝，原记录字节保留且不生成任何publication目录。相关28项通过（19.327秒，`/tmp/creative-evidence-locator-negative.log`）。不代表干净消费端、生产后端或执行方身份认证。

- [x] archive retrieve-evidence独立CLI接通：仅可信locator哈希、私有backend和新目标，无配置/数据库的干净目录实际取回原始字节，未生成工作区。相关29项通过（20.262秒，`/tmp/creative-clean-evidence-green.log`）。可信Git来源、负向全矩阵、生产后端/Studio及中断验收仍待完成，不声称真实远端事实通过。

- [x] 独立证据取回负向验收：可信locator哈希不符、未知schema/私有字段/身份逃逸、证据哈希错绑、后端损坏/缺失版本拒绝且无输出；已有目标字节保留。新增专项及外部存储回归通过，证据`/tmp/creative-evidence-retrieval-negative.log`。仍不代表托管Git可信来源、生产持久后端或Studio验收。

- [x] 观察证据定位实际Git提交及独立克隆取回验收：临时仓库提交locator，从完整SHA的Git对象读取可信哈希，--no-local克隆并检出准确提交；无配置/运行数据库的公开CLI从私有后端恢复原始字节，remote_verified保持false。相关29项通过（23.344秒，`/tmp/creative-evidence-git-clone.log`）。仅临时本机Git/后端，不替代托管PR、生产持久性及真实ASC验收。

- [x] Studio本地HTTP观察证据登记接入相同核心，exact字段与RETAIN确认、严格base64及既有同源/请求大小边界；真实临时HTTP操作登记后核对对象原始哈希。相关30项通过（27.780秒，`/tmp/creative-studio-evidence-green.log`）。仅HTTP接口，前端界面/负向全矩阵/实际运营验收仍待完成。

- [x] Studio观察证据登记负向边界验收：错误确认、额外私有路径字段、无效base64及字节哈希不匹配均返回400，全部已有记录字节不变且不创建attempt。相关31项通过（27.107秒，`/tmp/creative-studio-evidence-negative.log`）。仍不代表前端文件选择/持久化界面或实际运营验收。

- [x] Studio加入原始观察证据文件选择/登记界面：原观察ID、执行者、20MiB浏览器文件上限及显式核对；调用统一HTTP核心，未知结果不自动重试，成功提示不冒充外部持久性或远端完成。前端88项回归及构建通过，运行dist已刷新。新交互实际浏览器/组件专项与持久化界面仍待验收；此次首次相对路径写入失败已纠正，不计入新增界面证据。

- [x] Studio原始证据登记实际浏览器验收：合成回执选择及显式确认后登记成功，成功后提交禁用；磁盘关联及受管理原文SHA-256核对一致。证据`/tmp/creative-studio-evidence-browser-proof.json`和截图`/tmp/creative-studio-evidence-browser.jpg`。测试服务与夹具已清理；attempt状态查询路径错误，未计入本次证据。持久化界面、生产后端及真实ASC验收仍待完成。

- [x] Studio持久化HTTP入口接通本机命名后端，拒绝浏览器路径覆盖、错误确认及缺失后端；真实临时HTTP保存后独立取回原文字节通过。新增2项专项通过，前端88项回归、类型检查及构建通过。持久化界面已接入，但新交互实际浏览器验收、生产后端及中断恢复仍待完成。

- [x] 原始证据保存取消合同：复现KeyboardInterrupt/SystemExit缺失结束记录后修复，取消结束attempt并保留已写工作原文，不创建关联或自动重试。相关回归35项执行通过（取消专项重复执行一次，34个不同测试），证据`/tmp/creative-evidence-cancellation-regression.log`。不包含SIGKILL、绑定提交阶段或全部恢复矩阵。文档已消除本地保存/持久化/独立取回能力的旧状态矛盾。

- [x] 观察证据关联提交失败复现后修复：关联提交后才标记attempt成功，绑定失败结束为failed；已绑定但取消的证据拒绝持久化及发布定位导出，原文和关联保留诊断。相关35项回归通过（`/tmp/creative-evidence-binding-regression.log`），新增取消后消费拒绝专项1项通过。仅覆盖可控异常，SIGKILL及全部恢复矩阵尚未验收。

- [x] 原始证据保存真实SIGKILL专项：artifact登记后和关联提交后两个中断点均保留原回执；未完成绑定拒绝持久化，有效租约拒绝接管，到期显式接管后新保存成功且旧原文不变。1项测试含2个实际进程场景通过（3.567秒，`/tmp/creative-evidence-sigkill-recovery.log`）。恢复使用现有通用接管并手动关闭接管attempt后重新登记；未实现一键恢复，不代表所有落盘点或Studio恢复验收。

- [x] 当前证据生命周期安装包独立验收：234份载荷文件逐字节匹配；解包独立目录运行37项观察/原文保存、HTTP/CLI、独立取回及SIGKILL恢复合同全部通过（32.555秒）。包`/tmp/creative-evidence-lifecycle-package.zip`，SHA-256 `40d7a20415e1c78abc13ad1a5704a90f9483d6925a035c94c2f9ba805807bb5b`；证据`/tmp/creative-installed-evidence-regression-proof.json`。本次包含最新证据修复及Studio构建，未重新验收真实媒体生产、生产后端、真实ASC或当前全仓，不作为最终发行包。

- [x] observation-evidence完整提交绑定核验：复现actor改写仍可持久化后修复，读取核对原提交事件及记录字节哈希，持久化和导出均拒绝且保留损坏原记录、无外部写入。相关40项回归通过（36.307秒，`/tmp/creative-evidence-commit-integrity.log`）。实体审计已区分历史19类与当前20类，清除公开取回未接通的过期状态；此前独立包早于本修复。

- [x] publisher技能、agent交接与生命周期合同补齐原始回执保存→命名后端持久化→脱敏定位导出→可信Git哈希独立取回流程，明确未知请求复查、私有原文边界及不重复ASC上传。三条公开命令help逐项核对，插件校验及新包结构smoke通过（`/tmp/creative-evidence-agent-contract-package.zip`）。仅合同和打包验证，不冒充实际agent全流程；实体审计的过期等待/未实现叙述已修正。

- [x] 当前20类业务记录共同版本边界重新验收：缺失、bool、float、字符串、0、未知版本及null均拒绝且原字节不变，共8项通过，证据`/tmp/creative-current-twenty-record-schema.log`。实体字段审计仍独立，不据共同版本测试关闭整个合同。

- [x] 最新冻结源树全量已结束：909项，889通过、3错误、17跳过，304份源码指纹一致（605.727秒，`/tmp/creative-evidence-final-full-regression-proof.json`）。三个错误均为新局部base64导入遮蔽截图导入入口；已移除重复导入，51项受影响组合及第三失败用例1项通过。新包增加retain/persist/retrieve-evidence常规入口检查并通过打包（`/tmp/creative-fixed-evidence-package.zip`）。本轮全量失败不改写为成功；当前修复后全量及独立媒体安装验收尚待完成。

- [x] 未知证据请求复查接入现有publication status/Studio发布报告：展示关联与观察ID、生产结果及已登记后端版本，读取核对原文和提交范围且无写入/私有路径。新增核心只读专项及相关36项通过（37.135秒，`/tmp/creative-evidence-custody-status.log`）；前端89项、类型检查及构建通过，含新展示专项。实际浏览器及损坏/未完成复查矩阵仍待验收；首次前端相对路径写入失败已纠正。

- [x] 证据复查异常及实际浏览器验收：关联actor改写和外部定位私有root字段均保留只读诊断、无版本/路径泄露；专项1项含2场景通过。浏览器选择发布计划实际显示证据/观察ID、生产成功与后端版本，同时远端状态仍为Verification incomplete。证据`/tmp/creative-evidence-custody-browser-proof.json`和截图`/tmp/creative-evidence-custody-browser.jpg`；合成夹具，不代表真实ASC或生产后端验收。

- [x] Levelory真实验收前置只读刷新：官方ASC确认app 6797350200、MAC_OS版本1.5（c22c8f4f-6a31-46aa-b940-c77b4f2126de）仍PREPARE_FOR_SUBMISSION，英文/简中文本地化均属于该版本。英文原preview处理COMPLETE但poster仍0×0，当前时间码00:00:05:01；简中文无preview。五张配置源截图存在，但当前项目配置无previewVideo。证据`/tmp/creative-levelory-live-readiness.json`及原始官方响应。未上传、改封面或修改Levelory已有文件，不代表新架构真实产品流程完成。

- [x] Levelory已有真实UI截图在新隔离生命周期完成双语实际生产：10张screenshot候选PASS，源配置及5张输入字节不变，无旧记录迁移。证据`/tmp/creative-levelory-fresh-production-proof.json`，工作区`/tmp/creative-levelory-fresh-acceptance`。人工查看发现默认composition呈现移动设备框、简中文案复用英文UI源；技术PASS不作为设计批准或1.5实录验收，目标适配与语言来源待整改。未封存、批准或上传。

- [x] 真实Levelory候选发现的目标默认构图修复：未指定layout时Mac使用mac_native_hero，手机保持phone_bottom；显式layout保留，编辑器和导出复用规则。失败用例先复现；前端90项、类型检查及构建通过。实际10张双语重新渲染PASS，查看简中首帧确认移动设备框已消除，证据`/tmp/creative-levelory-mac-layout-proof.json`。旧源语言问题仍待新采集/配置解决，不作为完整设计批准。

- [x] Levelory语言来源严格前检已验证：原配置未启用requireExportEvidence，探索输出PASS不证明本地化审核；隔离配置启用严格模式后5个简中场景全部拒绝隐式继承。证据`/tmp/creative-levelory-localization-gate-proof.json`。编排技能补齐发布候选必须启用严格输入/渲染证据检查，不用已合成商店图片充当raw。实际简中采集、渲染严格验收及批准仍待完成。

- [x] 新项目模板默认严格验收：requireExportEvidence=true，非默认语言逐卡声明独立raw截图路径；新增失败合同先复现，3项安装载荷测试及插件校验通过。模板不制造素材，缺失实际输入仍拒绝；已有Levelory配置未修改。新包验证见`/tmp/creative-strict-template-package.zip`。

### 外部输入与阻塞

- [ ] 第二个真实产品尚待确认；已建议Fubiao，未把建议当作用户选择。
- [ ] 原生录制仍待真实窗口与场景验收；最新只读预检已通过权限门禁，但Levelory Dev窗口列表为空（`/tmp/creative-native-permission-latest-proof.json`）。此前权限缺失已过时；未启动应用、未录制，不用合成视频代替。
- [ ] 真实产品候选的设计批准及上传范围必须与实际产物绑定；既有泛化授权不制造尚不存在的批准证据。

最近一次全量回归执行869项，852项通过、17项跨文件系统用例跳过，300份源码指纹前后一致，耗时603.155秒；证据`/tmp/creative-latest-full-regression-proof.json`及`/tmp/creative-latest-full-regression.log`。该结果包含交付身份及目标绑定修复，发生在最新Studio Origin修复之前；该修复另有38项专项及实际合成媒体生产验证，不冒充最终源树全量验收。

## 当前证据

当前工作分支为`feat/unified-artifact-lifecycle-v2`，工作区`/private/tmp/app-store-creative-redesign`，基线50a6414与2026-10-07刷新后的origin/main一致。271个原整改路径的字节、权限、符号链接和删除状态已校验复制；原工作区及独立备份保留。存在大量未提交及未跟踪开发产物，尚无最终可安装发布版本；不能把未提交源树视为发布版本。

最近已完成的全量回归为869项执行、852项通过及17项跨文件系统用例跳过，300份源码指纹一致（`/tmp/creative-latest-full-regression-proof.json`）。它发生在Studio、事务元数据、发布媒体清单及观察文件输入修复之前；后续修复有各自专项证据，不能将历史全量结果视为当前最终源树通过。

当前冻结源树全量回归已结束：886项执行、869项通过及17项跨文件系统用例跳过，耗时559.742秒，301份源码指纹前后一致。证据`/tmp/creative-current-final-contract-regression-proof.json`及`/tmp/creative-current-final-contract-regression.log`。包含最新事务元数据、发布媒体清单、external实际checksum及观察/ASC输入修复。跳过用例不计为通过；真实独立卷此前有单独17项证据，不能混为本轮执行。

最新独立包早于后续修复，当前包验证仍待完成。前端88项及类型检查/构建属于此前未变更前端源码的证据。全量回归不替代长期证据链、真实产品、持久后端、ASC及最终发行门禁；目标保持未完成。

## 按完整能力关闭

| 顺序 | 交付能力及ADR范围 | 当前已验证部分 | 仍须完成及关闭证据 |
| --- | --- | --- | --- |
| 1 | 配置、存储位置与迁移；ADR 1、9 | 分层加载、共享条件保存、CLI/Studio有效路径、内部拥有层安装/恢复、正向本机计划 | 统一正向及反向prepare/switch/resume/rollback；本机文件成为唯一实际写入目标，共享原文不变；正向切换及安装后中断续执行/回滚已接通，含真实Git公开CLI；反向链路及真实Git公开CLI的A→B→A→B→A、安装后恢复/回滚已验证；继续覆盖全部中断点；新合同下既存run仍可读取；路径替换、重叠、权限和跨文件系统验收。拥有层往返链路已接通；完整迁移能力仍待上述验收。 |
| 2 | 生产、依赖与统一操作；ADR 2、7 | 捕获、截图、视频、海报登记；CLI/Studio受管理入口；租约、候选和来源关联 | 旧任务引擎、公开verify/publish及旧交接/模板已退出，独立媒体验证不写发布状态；继续核验剩余低层执行器边界，业务记录提交事件及公开history verify已接入；迁移/维护日志统一只读查询已接入；继续完成执行验证、完整执行者身份和真实依赖失效；Studio审批/封存/恢复、记录审计及发布状态只读入口已接通，继续完善维护及发布执行协调；失败、取消、重试和接管不得覆盖原输出；真实浏览器及原生录制验证，不能仅使用模拟生产器。 |
| 3 | 审批、封存与Git取回；ADR 3、8 | 不可变封存、配方独立恢复、设计/上传批准分离、临时Git/LFS远端取回 | 完整媒体及来源证据、私有路径脱敏、持久远端与external策略；可信清单、准确提交/PR绑定，干净克隆独立取回和CI只读门禁；实际截图/视频/封面归档通过验收。 |
| 4 | 库存、清理与长期维护；ADR 5、6、7 | 引用保护、隔离/恢复/purge、保留副本和库存观察 | 配置暂存与孤儿管理、日志保留、重复迁移后的完整副本位置投影、共享对象保护、Studio维护操作；未知文件保留，引用保护和过期拒绝；清理中断、恢复、永久删除后重建验收。 |
| 5 | ASC交接及远端证据；ADR 4、7 | 本地publication计划、上传批准、观察派生和未知状态门禁 | ASC Preview真实响应转换及公开命令已接通，0尺寸封面不误报通过；继续完成应用/版本/语言关系核验、真实远端交接和复查；上传、处理、封面和关联分别有证据；请求成功但证据缺失保持未知/失败；避免重复上传。Creative准备物料及证据，不复制ASC上传能力。 |
| 6 | 两产品运营验收与最终交付；ADR 1–9 | 单元/HTTP/临时工作区测试与打包证据 | 两个不同产品分别完成截图、视频、封面生产→批准→封存→Git取回→ASC交接→远端复查；至少一次失败/取消/重试/隔离/恢复演练。最终源树全仓、前端、真实安装包和文档一致；整理差异、审查及授权范围内Git/发布动作后，才可称可更新使用。 |

这些能力存在依赖，不能以独立小模块数量计算完成度。实现过程中可以先通过测试建立合同，但同一能力必须接通公开入口、失败恢复、文档和交付包才关闭。

## 执行规则

故障验收按原ADR的进程中断、崩溃续执行、文件系统错误、跨文件系统及恢复要求执行，不额外要求真实硬件断电演练。仍需可复现的中断与恢复证据，不以设计推断代替验证。

优先完成第1项整个迁移链路，再推进第2–5项缺口并在第6项统一验收。每次进展报告注明关闭了哪项完整能力、证据位置及还剩哪些门禁。没有完整关闭就报告部分完成，不把再次打包或少量专项当作交付里程碑。

暂停扩大未被ADR要求或真实故障证明必要的防护抽象。必需的身份、原子性、Git和引用保护仍保留；每个防护改动绑定上述能力及可复现失败场景。最终测试只在实现变化、失败或未决风险需要时重复。

## 不可省略的验收清单

- [ ] 逐条审计ADR实体、schema及未知版本拒绝合同，而非仅模块存在。
- [ ] 重试不覆盖、内容去重保留来源、真实依赖失效、批准不可变。
- [ ] 并发提交不交叉、部分提交恢复、共享对象不误删、过期清理拒绝、路径逃逸拒绝。
- [ ] 四类目录默认/自定义/本机覆盖，CLI与Studio结果一致，既有存储绑定不被重解释。
- [ ] 正反向迁移及重复往返、跨文件系统、暂存和备份维护闭环。
- [ ] 空工作区/干净Git克隆取回、LFS/external约束、完整提交和清单绑定。
- [ ] ASC真实交接和回执，证据缺失不报完成、不重复上传。
- [ ] 两产品截图/视频/封面矩阵及运营恢复演练。
- [ ] 当前最终源树全仓、前端、包及实际安装工作流验证。
- [ ] 远端基线、最终差异审查和发布版本一致，Git写入按明确授权执行。

全部勾选必须有对应实际证据；当前均不能据局部进展整体勾选。状态更新汇总到ADR-002-implementation-status，不继续复制长篇合同变更历史到新的权威文档。

全量回归当前错误已独立复现：test_changed_run_target_cannot_reuse_design_approval仍预期状态查询返回STALE，但新增run原提交绑定检查在status入口直接拒绝被改写记录，报Run commit event binding differs from record bytes。修正方向为保留更早拒绝，在测试中同时验证status与seal拒绝且无交付记录；冻结全量仍运行，尚未编辑测试，完整结果待终态。该专项单独执行退出1，不计通过。

运行身份修复后首次冻结全量终态：943项执行、924通过、2错误、17跳过，源文件306份指纹一致，退出1（/tmp/creative-run-identity-full-regression-proof.json）。两项错误分别为旧测试预期STALE而当前更早拒绝改写run，以及Studio夹具缺少显式project.id；均独立复现后仅更新测试。相关验证见/tmp/creative-full-regression-errors-repaired.log，最终全量须重新验证，不沿用失败结果。

当前运行时对Levelory独立新架构验收项目完成只读storage inspect和history verify，两命令退出0，业务记录审计为PASS，记录数48。证据/tmp/creative-levelory-current-storage-inspect.json及/tmp/creative-levelory-current-history-verify.json；后者SHA-256为4db5ba2805199ab2bf0f61defe4d4d6c21795a1a815710545bb9f43738e37fe4。未修改产品主仓库、不补写旧记录；此审计只证明当前业务提交完整性，不证明中文UI、真实视频/封面、实际批准或ASC发布。

发布入口只读核对：当前.github/validate_plugin.py执行通过（0.2.10）；storage/run/preview、preview poster、archive verify-git及publication公开help与运营文档示例一致，run start消费目标JSON文件。当前活动README/运营说明/技能文档扫描未命中已退出的claim/complete、task.schema、creative_workflow、asc_handoff、project.json/release.json或--output-dir引用。技能lifecycle-contract.md第44行仍将external media retrieval描述为未实现，与后文受管理独立取回实现说明冲突；待冻结全量结束后修正该摘要，不将临时后端验收表述为生产闭环。源码与技能冻结保持不变。

当前源码真实跨文件系统专项：自建独立APFS临时卷，验证st_dev与源项目不同，17项正反向进程中断/公开CLI恢复测试全部通过（21.607秒，宿主任务23.049秒），退出0；测试卷成功卸载，映像保留为自有验收产物。证据/tmp/creative-current-crossfs-acceptance-proof.json及对应日志。该专项补充普通全量的17项独立卷跳过，不改写全量原始结果、不替代摘要证据链新增跨卷场景、Studio交互或生产后端验收。

原始观察证据/摘要跨文件系统矩阵：临时适配器复用当前RemoteObservationTests的16个搬迁SIGKILL用例，只将plan_relocation目标四根替换为自有独立APFS卷绝对目录，逐例断言st_dev不同；双向×意图/目录发布/配置安装/回执×resume/rollback，16项54.026秒通过，任务退出0、测试卷成功卸载。恢复后绑定记录字节、原始对象、摘要及私有后端保存/独立读回有效。证据/tmp/creative-current-evidence-crossfs-v2-acceptance-proof.json及日志；临时适配器/tmp/creative-crossfs-observation-matrix.py。首次选择器误包含retention测试，断言退出未执行用例，失败证据单独保留，不计通过。未更改冻结源树；临时后端不替代生产长期保存或Studio操作验收。

控制日志边界源码核对：operation_history.journals始终返回OBSERVED和execution_verified=false，只读四类控制记录；实际维护执行验证由maintenance_observations核对当前对象与目录后设置execution_verified，二者不能替代。新增跨卷证据链16项使用临时适配器，冻结结束后仍需将适配器纳入仓库的显式独立卷测试入口，保持无测试卷时明确skip；本机专项成功不代替长期可重复门禁。真实第二产品及持久存储位置已向用户请求必要信息，未选择未授权生产资源。

跨卷证据测试持久化候选已准备于/tmp/creative-crossfs-test-candidate/test_cross_filesystem_observation_evidence.py：使用独立TestCase显式绑定16个已验收用例，避免导入原TestCase引入无关重复测试；同文件系统或缺少专用卷时明确skip。无卷发现执行正好16项、均明确skip，不能记作16通过。候选独立APFS实际验收已启动，源码与技能仍冻结，尚未纳入仓库。

可纳入仓库的跨卷证据链测试候选独立验收通过：unittest discover只发现16项，无卷时16项明确skip；专用APFS卷下16项通过（53.754秒），任务55.209秒退出0并卸载卷。证据/tmp/creative-durable-evidence-crossfs-acceptance-proof.json与日志。候选仍在/tmp/creative-crossfs-test-candidate，待冻结全量结束后纳入仓库，不把临时候选声称为已提交门禁。

当前源码真实OS权限专项复核：test_filesystem_permission_acceptance四项1.778秒通过、无skip，退出0；对象目录读取拒绝时库存保持未知且清理/搬迁拒绝，暂存写入失败保留失败意图、权限恢复后新批次完成，配置父目录写入拒绝与恢复边界验证。所有chmod只作用于测试自有临时目录并恢复权限。证据/tmp/creative-current-filesystem-permission-acceptance.log。不将四项范围扩展为所有权限/路径替换/协调场景。

修正后冻结全量终态：943项执行、926通过、17项独立卷用例skip，686.563秒，退出0、306份源文件指纹一致；证据/tmp/creative-repaired-full-regression-proof.json及日志。此前17项已在专用APFS卷单独通过，不改写本次全量skip结果。随后只新增tests/test_cross_filesystem_observation_evidence.py（与真实卷16项成功候选字节一致）及修正技能external取回摘要，无运行时代码变更；新增模块无卷执行16项明确skip，插件结构及diff检查通过。新测试已进入仓库发现入口，真实卷候选验收见/tmp/creative-durable-evidence-crossfs-acceptance-proof.json。完整全量结果对应新增模块前，不能把959项称为已执行全量。

解除冻结后的新安装包构建/隔离CLI烟雾通过；236个载荷与当前源码逐字节一致，包SHA-256为49e2c548f97d9c984f15c67d341fb2d6c1c25ce4b4e4bbcfa1405535356eed09，证据/tmp/creative-post-regression-package-proof.json。此前73项独立安装回归对应身份/快照修复包；新包只改变技能说明，不将烟雾/字节核对描述为重跑73项或生产验收。实体审计当前基线同步，保留原有真实产品、授权、后端及ASC门禁。

完整差异盘点包含未跟踪文件：284路径，运行模块58、Studio63、测试131、技能18、文档10、打包/其他4；分支feat/unified-artifact-lifecycle-v2、HEAD50a6414c7e83257bcc3ec691e9a604cc6605f5ef。证据/tmp/creative-current-change-inventory.json。初步审查project_identity、_run消费及maintenance_observations边界，不把无发现表述为完整审查通过。ASC封面当前只读诊断已按用户先前agent授权委派，禁止上传/删除/替换媒体和本轮ASC写操作，结果待返回。

ASC当前封面独立诊断：en-US预览29000019-5275-8538-8110-6dac57d06d74仍COMPLETE，时间码00:00:05:01，previewImage为0x0；API新鲜模板的两种有效尺寸/格式独立HTTP请求均400空响应，视频HLS可用且15秒，不支持仅浏览器缓存归因。CLI可修改previewFrameTimeCode，没有单独上传封面图或强制重建接口。按用户此前可逆封面修复授权，专门agent已接到单次修改为00:00:05.000并核验实际封面指令；不重传/删除视频，不将PATCH接受视为成功，结果待返回。

ASC封面单次修复实际结果：子agent用量限制中断，主线程先查询确认时间码仍00:00:05:01，未重复写。CLI声明支持的00:00:05.000被Apple API以Invalid format拒绝（退出5）；随后使用帧格式00:00:05:00，PATCH及独立查询退出0，时间码生效、视频checksum仍2a762a8cd8425dc9a58560393f5bf85d。实际图像HTTP400且非有效PNG，API立即与30秒延迟复查仍0x0/COMPLETE；模板仅w/h/f三占位符已全部替换。证据/tmp/creative-poster-frame-format-response.json、/tmp/creative-poster-frame-format-probe.json和/tmp/creative-poster-delayed-recheck.json，原始响应私有保留，不提交签名URL。未上传/删除/替换媒体，不能称封面成功。当前时间码保留00:00:05:00，必要恢复原值使用asc video-previews set-poster-frame --id 29000019-5275-8538-8110-6dac57d06d74 --time-code 00:00:05:01。

真实ASC响应通用门禁验证：当前asc_observation_adapter.preview_facts消费本次延迟查询的原始响应，输出upload found=true、checksum保持，processing COMPLETE，poster width/height均0且poster_verified=false；原始响应SHA-256为87baf45767935dde797af472fdc52d2b8a2df533ce5755191019aaf9620435cd。证据/tmp/creative-current-actual-poster-normalization-proof.json。该真实故障响应验证已有门禁拒绝误报，不绑定新候选/计划、不冒充批准或完整远端验收；CLI修改时间码没有使该门禁通过。

Studio永久清理实际浏览器审查已准备：隔离临时项目、一个44字节失败采集源对象，已有候选依赖受保护；对象先按0天试制策略隔离，生成独立purge计划0bdb8b788284404da2b3b8bc8f03b77d。浏览器显示完整对象哈希/大小与不可逆提示；Operator/Reason已填写，PURGE输入与确认勾选保持空，执行按钮disabled。截图/tmp/creative-studio-purge-confirmation.png，夹具元数据/tmp/creative-studio-purge-review-fixture.json。未执行永久删除；浏览器工具确认规则要求操作时用户确认，待确认后才可验收最终执行。只涉及自有临时测试对象，不操作Levelory或正式归档。

物料消费审查发现并修复缺口：verify_artifact此前只检查对象字节与记录的sha/大小，未核对原提交事件；测试复现role、inputs、logical_path、partial、media_type五种记录改写及缺失事件均被接受（2测试6失败，/tmp/creative-artifact-commit-red.log）。现在消费先核对events中的完整artifact提交哈希/身份/项目范围，缺失或改变拒绝；拒绝不修复原记录。2项专项与物料/封存/独立来源组合38项7.741秒通过，/tmp/creative-artifact-commit-green.log；扩大发布/远端证据/Studio消费回归运行中。该运行时代码修复晚于943项全量及当前独立包，旧全量/包不能当作本次修复后的完整验证。Studio永久清理仍等待真实用户当次确认，不执行待批动作。

物料提交完整性补充业务结果验收：候选选择同时拒绝改写输出inputs及其上游source的role，候选记录集合与字节保持原样、改写物料保留不自动修复。当前专项3项0.238秒通过；扩大消费回归仍在具体session14609运行，不因观察超时重启。该专项验证候选创建边界，不把结果扩展为所有业务实体消费完整性。

物料提交修复扩大消费回归100项165.336秒通过（/tmp/creative-artifact-commit-consumers.log），范围为publication、external、观察证据及Studio，早于随后attempt修复。随后新测试复现失败outcome改为succeeded后可选候选，以及started.owner改写后可续租，两项RED准确失败（/tmp/creative-attempt-commit-red.log）。attempt的started/outcome等记录读取现统一核对原提交事件、完整字节哈希与项目范围，不修复记录、不复用失败身份；租约/物料/封存/业务审计组合61项9.868秒通过（/tmp/creative-attempt-commit-green.log）。当前运行时代码晚于既有全量和独立包，完整回归及新包仍需验证。

共同业务记录提交边界已统一：全部20类记录按各消费入口对改写字节核对原提交事件，run保留专门快照消费核验，其余19类共用读取检查；移除verify_artifact重复事件实现，媒体字节检查仍保留。RED在15个类别准确失败（/tmp/creative-common-commit-red.log）；首次组合测试因子场景残留改写commit-abandonments夹具导致13个后续子场景错误，已仅修正测试隔离，不放宽核心拒绝（/tmp/creative-common-commit-green.log）。最终70项8.632秒通过，/tmp/creative-common-commit-final.log。当前源码全量具体session63189运行，新包具体session6258构建中；此前943项全量/包对应旧源码，不证明本次修复完整通过。不自动回填记录或生成新兼容提交。

共同提交边界新包逐文件核对236载荷与源码完全一致，SHA-256为371b55e14c60328d5bdacc8f98f2496cecf3d18fafcee9e0e2042f476eb7d719，证据/tmp/creative-common-commit-package-proof.json。仓库外独立解包后复制测试，PYTHONPATH只含临时tests与包内runtime/scripts，加入全部20类提交边界、物料/attempt及租约测试；具体session64415运行，日志/proof为/tmp/creative-installed-common-commit-regression.*。源码全量具体session63189仍运行，不把包烟雾或字节一致当作行为回归通过。待确认的Studio永久清理夹具服务早于共同提交修复启动，最终执行验收前须用当前运行时重新绑定同一隔离对象/计划，不能沿用旧服务进程声称当前源码已验收。

当前共同提交全量日志出现失败，未取得终态；独立重跑delivery_status/design_target/external_delivery_identity复现更早提交拒绝与旧诊断预期冲突，证据/tmp/creative-common-commit-failure-reproduction.log。其中delivery_status记录读取位于try之外，损坏记录直接异常而不是结构化FAIL，属于待修运行时诊断缺口。临时方法候选只将严格_read移动到原try内，3项delivery_status测试2.986秒通过，/tmp/creative-delivery-status-candidate-proof.json；尚未应用源码，不放宽提交校验，不计当前代码通过。其他外部发布错误仍须逐项区分诊断预期/有效流程，不把全部失败预判为旧测试问题。全量session63189与独立包session64415继续运行，冻结源码不变。

当前全量终态证据：`/tmp/creative-common-commit-full-regression-proof.json`；965项执行，22 failures、10 errors、33 skipped，696.712秒，309份源码指纹不变。随后三处状态诊断修复的当前源码5项回归通过，证据`/tmp/creative-status-diagnostics-source-regression.log`。旧全量失败报告保留，不把专项通过当作全量已修复。

共同提交消费者测试收敛：原有受影响23项通过，随后补充合法提交但字段无效的证明/媒体清单、独立依赖循环和外部定位字段覆盖，组合29项19.947秒通过（`/tmp/creative-commit-consumer-field-coverage.log`）。checksum准备负例使用新身份真实提交的测试记录，仍验证实际字节并保留已取回诊断文件。旧篡改场景断言更早提交拒绝；不放宽运行时校验。三处状态修复及本轮测试后重新执行冻结全量，结果待终态。

当前修复后新包：`/tmp/creative-repaired-commit-package.zip`，SHA-256 `cc25305d6b0ba9ef23a0f763a0aec1cd2e4925a65180382d7f80cf3146caf867`，236份载荷逐字节与冻结源码一致，打包门禁通过（`/tmp/creative-repaired-commit-package-proof.json`）。独立安装扩大回归session34168正在执行；修复后源码全量session92282仍运行，两者都尚无终态，不计通过。Studio发布详情不消费delivery_id，损坏计划状态的null身份不会被拼接为操作目标；列表仍按严格读取拒绝损坏计划。

修复后全量终态：969项，2 failures、33 skipped，690.270秒，310份源码指纹一致（`/tmp/creative-repaired-commit-full-regression-proof.json`）。独立包110项仅1 failure（`/tmp/creative-installed-repaired-commit-regression-proof.json`）。一处测试误改scope断言已恢复；另修复delivery状态对不存在记录保持HTTP404、已有损坏记录返回FAIL，实际6项6.485秒通过（`/tmp/creative-status-missing-record-regression.log`）。此前包字节早于该运行时修复，须重建，当前全量仍未通过。

当前最终状态包实际媒体验收通过（`/tmp/creative-final-status-installed-media-proof.json`及日志）：真实Chrome渲染、FFmpeg编码、封面提取、受管理登记/验证/封存及独立恢复，3类媒体、15个归档文件。含中文和空格的四类项目外自定义根被实际使用，默认工作根不创建，共享配置原文不变；脱敏工具回执及依赖、批准目标保留，修改恢复包目标被拒绝。使用合成场景与测试批准，不计两真实产品或ASC。首次沙箱因只读/bin/ps拒绝退出1，获运行时提权后重试退出0；冻结源码未变更。全量及独立安装组合仍待终态。

当前安装包组合终态：112项159.321秒通过、exit0，236份载荷一致（`/tmp/creative-installed-final-status-regression-proof.json`）。当前源码全量session32305仍存活，无终态，不计通过；不据安装包专项关闭完整交付。

当前包证据一致性复查完成：236载荷与当前冻结源码逐字节一致，安装112项及实际媒体生产/独立恢复证明绑定同一SHA-256（`/tmp/creative-final-status-package-proof.json`）。最新核心跨文件系统专项33项已启动，使用新建自有APFS映像、不同st_dev，session72030实测存活；结果待终态，执行后须确认卸载。源码全量session32305仍运行。

当前跨卷专项终态证据：`/tmp/creative-final-status-crossfs-acceptance-proof.json`及日志；自有临时APFS卷33项通过，任务83.246秒退出0，hdiutil卸载成功且mount.is_mount()为false。正式存储与完整Studio恢复仍未关闭。ADR目录示例同步当前独立remote-observations/observation-evidence/external-media/preparations记录，不再描述publication内嵌第二份回执权威。

输入边界审查复现：delivery/publication/external preparation状态将非法ID包装为FAIL（3测试18子场景失败，`/tmp/creative-status-input-red.log`），未写文件。候选在读取/诊断前复用safe_id，3项0.042秒通过，所有记录字节不变（`/tmp/creative-status-input-candidate.log`）；尚未应用冻结源码，待当前全量session32305终态后纳入。当前287路径差异尚未暂存，git diff --check通过，完整差异审查仍未完成。

远端main再次只读核对为50a6414c7e83257bcc3ec691e9a604cc6605f5ef，与当前分支HEAD基线一致（`/tmp/creative-final-status-remote-baseline.json`）；未执行fetch、暂存、提交或push。CI配置为Ubuntu Python测试及Node20前端/完整打包门禁，源码全量session32305仍运行；远端CI尚未触发，不能用本地测试替代。

冻结全量终态通过：969项758.069秒，33项独立卷跳过，310份源码指纹一致（`/tmp/creative-final-status-full-regression-proof.json`）；这些33项已有当期独立卷实际通过证据。后续非法ID修复在记录读取和异常转换前调用统一safe_id，3项永久测试纳入仓库，当前24项扩大回归18.836秒通过（`/tmp/creative-status-input-source-regression.log`）。无历史兼容或记录修复，最新包重建及最终全量尚待验证。

非法ID校验后新包构建及实际媒体验收通过：SHA-256 `406cf1e668fc4e62cfc39828c61dc29ec37e57bc3fe4316381ff89c61f4f1e85`，236份载荷一致（`/tmp/creative-status-input-package-proof.json`）。新包实际Chrome/FFmpeg/封面、四自定义根、封存及独立恢复15文件通过（`/tmp/creative-status-input-installed-media-proof.json`），合成场景与测试批准，不计真实产品。仓库外扩大115项组合session98652仍存活，结果待终态。旧入口扫描仅见--output-dir明确拒绝路径，无可执行旧工作流；不兼容读取旧记录。

非法ID校验后安装组合终态：115项142.270秒通过，exit0，236份载荷一致（`/tmp/creative-installed-status-input-regression-proof.json`）。另外仓库外真实CLI的delivery status/publication status/preparation-status三个入口拒绝../outside且退出2，配置与全部记录字节不变（`/tmp/creative-installed-status-input-cli-proof.json`）。最新源树含3项新增测试，最终全量尚需复验；本结果不替代正式存储、真实产品、ASC或发行。

当前运行时Studio已重新绑定原隔离夹具（http://127.0.0.1:3101，session38882）；浏览器读取维护记录，隔离操作检查PASS，永久删除计划检查NOT_EXECUTED，切换后旧结果替换；提交证据11记录/11意图显示Records verified。独立文件核对全部记录字节不变，44字节隔离对象哈希一致，purged回执不存在（`/tmp/creative-studio-current-read-verification-proof.json`，截图同名png）。未执行永久删除或中断写恢复；不能据此关闭完整Studio维护验收。

当前Studio可逆恢复实际浏览器验收通过（`/tmp/creative-studio-current-restore-proof.json`及截图）：独立临时46字节夹具，界面审查完整哈希/容量、填写测试操作者/原因、确认恢复，刷新历史为restored、执行效果PASS；独立核心核对恢复artifact哈希/大小，受保护候选仍有效，隔离副本保留。原待确认44字节永久删除夹具与计划未操作。该正常恢复流程不代表中断写恢复或永久删除验收。最新源树含非法ID校验与3项永久测试的冻结全量session33364已启动并确认存活，结果待终态。

实际普通恢复中断的Studio续执行验收完成（`/tmp/creative-studio-interrupted-restore-proof.json`及前后截图）：自有子进程首次恢复hardlink后SIGKILL退出-9，1/2对象恢复且无终态，UI实际效果FAIL且不报成功；通过原操作审查并续执行后2/2对象恢复、历史restored、效果PASS，artifact记录及隔离副本保持。发现普通restore_cleanup缺少恢复意图，部分恢复无法区分一般损坏；需补齐意图及INCOMPLETE诊断，不能关闭完整维护。临时TDD前置意图测试实际失败（`/tmp/creative-ordinary-restore-intent-red.log`），源码冻结未变更，待session33364全量终态后修复；不加入旧记录回填。

普通恢复意图修复合同已收敛（`/tmp/creative-ordinary-restore-contract.json`）：写文件前持久化绑定原操作/清理计划/存储范围的restore-intent；完成回执绑定意图哈希；未完成意图报告restoring/INCOMPLETE，损坏FAIL；恢复开始阻断永久删除；原意图及已结束回执不改写、不回填旧终态。八项验收覆盖意图写入失败、部分恢复续执行、错绑、损坏保留、永久清理互斥、真实SIGKILL/Studio及无意图旧终态拒绝。当前源码仍冻结，无实现完成声明。
