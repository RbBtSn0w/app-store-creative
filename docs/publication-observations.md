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
  "facts": {"processing_state": "COMPLETE"},
  "supersedes": []
}
```

```sh
python3 app_store_creative.py publication observe --repo /path/to/project \
  --id PUBLICATION_ID --observation normalized-observation.json
python3 app_store_creative.py publication status --repo /path/to/project \
  --id PUBLICATION_ID
python3 app_store_creative.py publication export --repo /path/to/project \
  --id PUBLICATION_ID --confirm
```

evidence_reference使用可追溯的执行记录身份，不能填本机绝对路径、带查询参数URL或凭证。内核仅接受规定的事实字段，不存储任意原始响应。执行者需要保留原始证据的可信定位；当前尚未实现各类ASC原始回执的自动适配与取回。

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

当前尚未提供独立导出目录重建运行记录的完整恢复入口、Studio观察编辑界面、ASC回执自动适配或实际远端全链路验收；这些仍属于统一整改的未完成要求。
