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

## 最新验证证据

| 项目 | 结果及范围 | 证据 |
| --- | --- | --- |
| 当前源码全量 | 999 项执行，966 通过、33 跳过；662.765 秒；316 份源文件指纹一致；退出0 | `/tmp/creative-overlay-fixed-full-regression-proof.json`、同名日志 |
| 独立卷专项 | PR head `cda553c`对应源码独立APFS卷33项通过，75.014秒退出0；已卸载且is_mount为false。全量原skip结果保留 | `/tmp/creative-pr11-crossfs-acceptance-proof.json` |
| Studio 中断恢复 | 安装包真实 SIGKILL 后 INCOMPLETE/RESTORING，按原意图恢复至 PASS；合成夹具 | `/tmp/creative-studio-installed-restore-proof.json` |
| 来源与设计 | Levelory中英文10份真实采集；新候选10份原采集进入依赖闭包，成图与已审查版本哈希一致 | `/tmp/creative-levelory-linked-design-provenance-proof.json` |
| 真实视频/封面 | Dev窗口采集及UI操作均成功；20秒1920×1080、30fps、H.264/AAC；原生录像、标准化回执及poster依赖完整 | `/tmp/creative-levelory-real-preview-proof.json` |
| 坐标边界 | 叠加层拒绝滤镜字符串、布尔值、非有限值及越界数值；20项相关组合通过 | `/tmp/creative-overlay-coordinate-green.log` |
| 安装包 | 238份载荷与当前源码逐字节一致；隔离安装41项28.861秒通过；源码仓库不在PYTHONPATH | `/tmp/creative-overlay-fixed-package-proof.json`、`/tmp/creative-overlay-installed-regression-proof.json` |

此前全量因复现坐标边界问题被主动终止，日志保留、不计成功；当前999项是修复后的新终态。完整包验证和远端CI分别记录，不能相互代替。

## 完整验收与发行 checklist

- [ ] 完整维护矩阵关闭：剩余权限、路径替换、协调边界及永久删除浏览器最终执行；当次删除授权尚未收到。
- [ ] 正式持久存储验收：长期保存、访问控制、成本与独立取回；正式位置尚未确定。
- [ ] Levelory完整闭环：截图审核缺口与视频构图修正、真实批准、封存、发布交接和干净工作区取回。真实生产技术链已通过；中文UI残留英文、合集侧栏截断及视频右侧黑边仍待处理。
- [ ] 第二个不同真实产品完整闭环：产品及仓库尚未确定；不能使用合成夹具替代。
- [ ] 真实失败/取消/重试/隔离/恢复与归档取回的产品级演练。
- [ ] ASC新合同完整远端验收及当前封面故障关闭：最新只读查询仍为previewImage 0×0；此前时间码调整成功不等于封面修复。
- [x] 当前包独立安装专项与逐字节载荷核验；不替代更新后的真实工作流验收。
- [ ] 完整差异审查及最新敏感证据检查。
- [x] 整改提交保存到独立分支；不代表发行完成。
- [x] Draft PR #11创建并关联当前任务；远端head为`cda553c5539824f3f118d2661951d437b9600b1a`。
- [ ] 远端CI及实际产品归档的准确提交/PR绑定；首次CI因runner缺少FFmpeg失败，已补测试前工具安装，待新运行。
- [ ] 合并main、推送、插件更新和更新后的实际工作流复验。

## 后续顺序

先完成当前包验收与差异审查，再完成真实物料审核及产品/存储/ASC剩余门禁，最后进入提交和发行。正式存储、第二产品和删除授权需要人类输入；其他可独立工作继续推进。所有明确需求有对应有效证据后，才能宣布整体完成。
