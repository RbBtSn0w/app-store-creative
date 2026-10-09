# ADR-002 实施状态

更新日期：2026-10-09。整体状态：**实现及主要本地验证已落地，完整验收与发行尚未完成**。

本文件是当前进度的唯一权威。需求范围见 [ADR-002](ADR-002-artifact-lifecycle-and-release-archive.md)，阶段日志见 [历史证据](evidence/ADR-002-implementation-history-2026-10-09.md)。不以测试通过比例计算整体完成度。

## 工作区

- 分支：`feat/unified-artifact-lifecycle-v2`。
- 基础提交：`50a6414c7e83257bcc3ec691e9a604cc6605f5ef`。
- 隔离工作区：`/private/tmp/app-store-creative-redesign`。
- 待发布版本：`0.3.0`；整改已提交；[Draft PR #11](https://github.com/RbBtSn0w/app-store-creative/pull/11)已创建，尚未合并或发布。远端基线须在交付前再次核对。
- 原插件仓库与 Levelory 用户改动保留；真实采集使用独立 Levelory 源树和 Dev 身份。

## 实现 checklist

- [x] 新实体合同、不可变业务记录、内容寻址对象、项目身份、提交绑定及运行快照；不读取或回填旧合同记录。
- [x] 四类存储根、项目配置/受保护本机覆盖、统一解析及 CLI/Studio 配置入口。
- [x] 受管理截图、录屏、视频和封面生产，租约、输入快照、依赖、失败及 partial 产物保留。
- [x] 已登记真实截图导入后保留原采集身份；录屏保留原生文件与恒定帧率标准化证据。
- [x] 候选验证、范围绑定批准、不可变封存及独立交付包。
- [x] Git/LFS/external 归档合同、命名后端、私有原始证据保存及便携脱敏定位。
- [x] 发布准备、ASC 交接与独立上传/处理/播放/封面观察门禁。
- [x] 库存、保留策略、清理计划、隔离、恢复、永久删除以及正反向存储搬迁。
- [x] CLI、Studio、技能合同和运营说明统一；旧工作流入口退出。

这些勾选表示能力已实现，不表示下方完整验收已关闭。

## 最新归档边界修正

归档边界审查发现：已登记采集缺少逻辑路径时，导入会成功，但其来源闭包无法在候选验证阶段物化。现已在导入入口拒绝该输入，并确保拒绝发生在创建新运行之前。

- RED：新增回归测试因未抛出错误失败，证明缺口。
- GREEN：导入/生产14项通过；封存、来源、清单、分层便携归档与原生视频归档25项通过。
- 新分发包完整 smoke 检查通过；从解压包独立运行导入/生产14项通过，包SHA256为`1a737a26e635a199a628c89383f2f0fe645cb6e9e65421a69afa840a88bfe95f`。证据：`/tmp/creative-archive-path-installed-proof.json`。
- 本修正随当前变更提交；下方全量与远端CI对应修正前版本，新提交5bcf5e2已在run 37902471567通过完整远端CI，见`evidence/ADR-002-ci-5bcf5e2.json`。

来源闭包后续审查：补充上游制作失败及缺失逻辑路径的导入拒绝，两种情况均先复现RED；导入、生产及封存归档40项通过。只读复查Levelory当前候选的65份来源依赖全部满足此约束。该后续源码修正待新提交CI，不能沿用5bcf5e2绿色结论。

写锁身份后续审查：获得独占锁后复查device/inode，阻止等待期间替换锁文件造成的双锁写入。新增回归先复现RED；记录/历史/并发38项通过；真实第二进程等待旧锁后替换路径，获锁即拒绝、业务记录字节不变。证据见`evidence/ADR-002-lock-replacement-review.json`。该后续修正须独立CI，不能沿用此前提交结论。

外部存储后续审查：复制期间父目录被替换为链接时，旧失败清理会误删新目录的未登记同名文件，回归已复现RED。现将暂存创建、读取、发布和清理绑定原目录描述符，清理核对暂存inode；源码27项、独立解压包27项通过，238份载荷与源码一致。证据见`evidence/ADR-002-external-parent-replacement.json`。该修正须独立新CI，不沿用此前绿色结果。

核心登记后续审查：复现对象根替换导致的失败清理误删。共用`safe_staging.py`现服务不可变记录、对象登记和外部复制；源侧暂存及目标发布均绑定目录描述符和文件身份。源码53项及周边42项通过；漏打包门禁先复现RED，加入必需载荷后5项通过；独立解压包55项通过，240份载荷与源码一致。证据见`evidence/ADR-002-shared-staging.json`。该统一修正须新提交完整CI，不能沿用f89d644结论。

## 最新验证证据

| 项目 | 结果及范围 | 证据 |
| --- | --- | --- |
| 当前源码全量 | 999 项执行，966 通过、33 跳过；662.765 秒；316 份源文件指纹一致；退出0 | `/tmp/creative-overlay-fixed-full-regression-proof.json`、同名日志 |
| 独立卷专项 | PR head `cda553c`对应源码独立APFS卷33项通过，75.014秒退出0；已卸载且is_mount为false。全量原skip结果保留 | `/tmp/creative-pr11-crossfs-acceptance-proof.json` |
| Studio 中断恢复 | 安装包真实 SIGKILL 后 INCOMPLETE/RESTORING，按原意图恢复至 PASS；合成夹具 | `/tmp/creative-studio-installed-restore-proof.json` |
| 来源与设计 | Levelory中英文10份真实采集；新候选10份原采集进入依赖闭包，成图与已审查版本哈希一致 | `/tmp/creative-levelory-linked-design-provenance-proof.json` |
| 真实视频/封面 | Dev窗口采集及UI操作均成功；20秒1920×1080、30fps、H.264/AAC；原生录像、标准化回执及poster依赖完整 | `/tmp/creative-levelory-framed-preview-proof.json` |
| 坐标边界 | 叠加层拒绝滤镜字符串、布尔值、非有限值及越界数值；20项相关组合通过 | `/tmp/creative-overlay-coordinate-green.log` |
| 安装包 | 238份载荷与当前源码逐字节一致；隔离安装41项28.861秒通过；源码仓库不在PYTHONPATH | `/tmp/creative-overlay-fixed-package-proof.json`、`/tmp/creative-overlay-installed-regression-proof.json` |

| 完整物料候选 | Levelory候选`94b210b7ce2a4661b8cf3bfbeb238e6c`技术校验PASS；10截图、1预览、1封面，65份来源依赖；尚未人工批准或封存 | `/tmp/creative-levelory-complete-candidate-proof.json` |
| 远端CI | run 37902471567，提交`5bcf5e2`，全部步骤成功；源码1000项执行、967通过/33跳过，Studio30文件/90项通过，类型检查、构建和分发包检查成功 | `evidence/ADR-002-ci-5bcf5e2.json` |

此前全量因复现坐标边界问题被主动终止，日志保留、不计成功；当前999项是修复后的新终态。完整包验证和远端CI分别记录，不能相互代替。

## 完整验收与发行 checklist

- [x] 本地维护边界专项：提交5bcf5e2下实际权限拒绝、路径身份替换、配置恢复、并发写入阻断及维护/搬迁协调，共50项通过、无跳过。证据见`evidence/ADR-002-maintenance-boundaries-5bcf5e2.json`。
- [ ] 完整维护矩阵关闭：浏览器永久删除最终执行及真实产品级演练；当次删除授权尚未收到。
- [ ] 正式持久存储验收：长期保存、访问控制、成本与独立取回；正式位置尚未确定。
- [ ] Levelory完整闭环：截图审核缺口、真实批准、封存、发布交接和干净工作区取回。真实生产技术链已通过；视频右侧黑边已在独立采集源树修正；中文UI残留英文、合集侧栏截断仍待审核处理。完整12份物料候选技术校验PASS，人工审核、封存及取回尚未关闭。
- [ ] 第二个不同真实产品完整闭环：产品及仓库尚未确定；不能使用合成夹具替代。
- [ ] 真实失败/取消/重试/隔离/恢复与归档取回的产品级演练。
- [ ] ASC新合同完整远端验收及当前封面故障关闭：最新只读查询仍为previewImage 0×0；此前时间码调整成功不等于封面修复。
- [x] 当前包独立安装专项与逐字节载荷核验；不替代更新后的真实工作流验收。
- [ ] 完整差异审查及最新敏感证据检查。
- [x] 整改提交保存到独立分支；不代表发行完成。
- [x] Draft PR #11创建并关联当前任务；远端head为`5bcf5e2330f67882957ea6c110f36eed7cbd7835`（当前仅有未提交验收文档更新）。
- [x] 远端CI：首次缺少FFmpeg问题已修复；run 37902471567在提交5bcf5e2上全部成功。
- [ ] 实际产品归档的准确提交/PR绑定。
- [ ] 合并main、推送、插件更新和更新后的实际工作流复验。

## 后续顺序

先完成当前包验收与差异审查，再完成真实物料审核及产品/存储/ASC剩余门禁，最后进入提交和发行。正式存储、第二产品和删除授权需要人类输入；其他可独立工作继续推进。所有明确需求有对应有效证据后，才能宣布整体完成。
