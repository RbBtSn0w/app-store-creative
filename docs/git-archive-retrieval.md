# Git归档取回验证

```sh
python3 app_store_creative.py archive verify-git --repo /path/to/project \
  --commit FULL_COMMIT_SHA --path release-assets/app-store/REVISION \
  --expected-sha256 MANIFEST_SHA256
```

入口创建独立临时克隆，禁用本地对象共享，检出指定完整提交，再验证正式包清单、媒体及配方来源。路径相对仓库且必须可移植，不依赖当前工作区的归档副本。临时克隆结束后回收；源仓库、索引和工作区不修改。

未指定远端时，仅证明本机Git仓库中普通Git媒体的提交可取回，不证明远端已push或远端服务可用。LFS必须指定远端并恢复真实对象。external已实现独立Git元数据克隆及指定后端版本对象取回，使用archive verify-external-git；它与普通Git媒体取回使用不同的描述符和后端合同，详见artifact-operations.md。普通Git发布计划生成前会执行该独立克隆验证，并把retrieval_proof绑定到提交、归档路径与清单哈希。上传审批、交接导出和发布状态使用同一证明校验；缺失或不匹配则拒绝。证明仍不代表远端已push。

## 配置远端取回

archive verify-git可指定--remote origin，publication plan可指定--archive-remote origin。入口从该已配置remote独立克隆并检出精确提交，不回退到本机仓库。证明中的source_scope与remote_name明确区分本机/远端；计划、审批和交接继续核对该范围。证据不保存remote URL或凭据，失败错误不透出Git认证输出。

临时bare远端测试证明已推送提交可取回、未推送提交拒绝，并验证计划登记远端证明。未对真实生产远端执行推送或验证；托管生产远端和external验收仍待完成；LFS临时远端验收见下文。

## LFS 归档取回

归档中的标准 LFS 指针必须与封存清单的 SHA-256 和大小一致。LFS 需要明确的配置远端；验证器从独立克隆执行指定提交的对象取回，再校验实际文件。仓库 .lfsconfig 端点覆盖目前拒绝。发布计划保留 lfs 模式及 configured-remote 证明；缺少真实对象恢复证据不能继续批准或交接。此能力不代替上传批准，也不执行 ASC 写操作。

独立取回命令共用300秒总预算，同时限制远端配置查询30秒、克隆/checkout/LFS命令各120秒。预算从取回入口开始计时，后续命令只使用剩余时间；超时拒绝生成发布计划，报告脱敏错误，并停止该命令所属的进程组。POSIX环境下每条命令建立独立会话，超时或执行器捕获到取消异常（例如KeyboardInterrupt）时向所属进程组发送SIGKILL并回收直接子进程。运行时尚未接管SIGTERM，外部直接终止宿主进程不能据此声称完成派生进程清理。主动脱离进程组的第三方进程不在该保证范围内。此预算约束外部命令等待，不声称文件系统校验或整个发布事务严格在300秒内完成。

发布计划消费对Git、LFS及external统一要求`package_verified`、`recipe_verified`、`provenance_verified`及`retrieval_verified`均严格为布尔true。缺失、false或其他类型不能授权上传或生成实际交接文件，不为既有记录补写成功字段。该检查绑定本地验证结果，不能替代生产远端可用性及真实ASC验收。
