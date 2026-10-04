# 物料库存与容量口径

inventory是只读的本地观察，不创建存储目录、不执行清理、不查询远端。它不能代替cleanup计划或正式归档验证。

```sh
python3 app_store_creative.py inventory --repo /path/to/project
```

## 对象分类

| 字段 | 含义 |
| --- | --- |
| reference_count | artifact业务记录数量；多个记录可能引用相同字节 |
| registered_identities | 已登记SHA256身份数量 |
| active_count | 活动对象路径中的实际文件数量，包括孤立或损坏文件 |
| corrupt | 活动已登记对象的大小或哈希不匹配 |
| missing | 已登记身份缺少活动文件和有效隔离副本，且无已完成永久删除记录 |
| quarantined | 活动位置不存在，但仍有大小及哈希验证通过的隔离副本 |
| purged | 有已完成永久删除记录，当前没有活动文件或有效隔离副本 |
| orphan_files | 内容寻址路径中的文件没有artifact登记；仅报告 |
| unknown_files | 对象库中的其他未知文件；仅报告 |
| unknown_quarantine_files | 隔离目录中的文件未出现在隔离操作清单；仅报告 |
| corrupt_quarantine_files | 隔离副本无法通过大小或哈希验证，不报告为可恢复 |
| unsafe_links | 对象库符号链接；不读取目标 |

工作文件继续分别报告registered_files、changed_files和unregistered_files。不根据文件名或相同字节猜测归属。工作根本身或子目录的符号链接不跟随；生产在登记尝试前也拒绝符号链接工作位置。

## 容量口径

active_object_bytes和quarantine_file_bytes按实际本地文件的逻辑大小统计，同一SHA的多个业务引用不重复增加活动对象大小。payload_logical_bytes合计活动对象文件和隔离文件的逻辑大小。

payload_unique_inodes按设备与inode去重，可识别活动对象与隔离副本之间的硬链接。payload_allocated_bytes_estimate按唯一inode的stat块数估算分配空间；APFS共享extent、克隆及压缩没有进一步解析，因此不是精确的已释放磁盘空间。永久删除报告的bytes_removed同样是被移除隔离文件的逻辑字节，不是整个项目的磁盘回收量。

work_file_bytes、release_directory_bytes和publication_directory_bytes分别统计这些本地目录的普通文件大小，不表示其中每个文件都已通过来源或正式包验证。other_object_file_bytes报告对象库其他未知文件大小。符号链接目标不计入。

Git历史、LFS远端和external后端容量未测量时返回null，不写成零。删除工作树或本地隔离文件不会证明Git历史或LFS远端容量减少。

## 并发与后续维护

库存是观察结果，不提供全目录事务快照。并发生产或清理期间文件可能变化；遇到读取失败应重新观察，不能用库存输出绕过执行前的引用及哈希校验。

孤立对象不能自动判定为可回收，可能来自尚未登记的生产或被中断的操作。当前仅报告，后续需通过执行记录和授权的孤立对象处置流程确定归属。工作文件及日志的隔离/清理、目录relocate和完整后端容量采集仍待实现。
