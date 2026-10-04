# 素材导入与工作区库存

CLI、Studio和生产执行器共用受管理输入合同。Studio不再把截图直接放进固定的.creative/assets目录；每次导入创建独立run/attempt、验证图像完整性、登记内容寻址对象并保留成功或失败结果。相同名称不会覆盖前次导入，相同字节可以共享物理对象。

```sh
python3 app_store_creative.py input import --repo /path/to/project \
  --source /path/to/capture.png --name capture.png --actor OWNER
python3 app_store_creative.py input resolve --repo /path/to/project \
  --path /api/inputs/IMPORT_ID/capture.png
```

导入支持现有PNG/JPEG检查；格式损坏在创建工作目录前失败。返回path是稳定引用，不是仓库内必须存在的文件。Studio通过受限API读取该引用对应的已登记对象，不开放任意文件路径。显式配置在项目外的workspaceRoot/objectRoot同样可用，受宿主权限约束。

输入库中的已接收导入持续保护，直到明确退役；不要绕过引用图手工删除对象。

## 输入库退役

```sh
python3 app_store_creative.py input status --repo /path/to/project --id IMPORT_ID
python3 app_store_creative.py input discard --repo /path/to/project \
  --id IMPORT_ID --actor OWNER --reason "Unused capture" --confirm DISCARD
```

退役追加不可修改的操作者和原因记录，释放输入库条目自身的保留引用。默认从退役起继续保留30天；当前配置、候选、审批、交付、未结事故及活动尝试的引用仍会保护字节和来源依赖。退役不会立即删除文件，也不会自动改写配置；已有配置引用在字节可用时仍可解析。

清理计划与执行均读取当前权威配置，遍历截图、背景图和源素材引用。配置修改会使旧计划失效，包括计划生成后重新选用退役素材的情况。配置无效、归属改变或存储绑定改变时拒绝清理，不退回旧快照。

工作区只允许一个权威配置文件执行写入或维护。--config可声明自定义文件；首次写入登记其规范化位置，其他配置文件不能直接共用该工作区执行清理。配置文件位置调整需要后续显式位置变更流程，不自行改写configuration-authority.json。

## 生产与正式封存

生产解析稳定引用，将字节复制到独立尝试的输入快照，保存快照哈希索引。新生产来源保留原始导入artifact依赖；复制后及产出提交前检查哈希与租约。截图库外部位置不会进入正式配方。

正式封存将配置引用改写为包内相对路径，保存必要输入及来源信息。恢复包可以脱离原工作区验证配方输入，不依赖原导入API或本机绝对路径。临时快照索引只允许读取其明确登记且哈希匹配的输入。

## Studio配置备份

保存配置前，原始配置字节登记为configuration产物，使用同一对象库和尝试记录，不再创建独立backups目录。已有受管理数据时，Studio拒绝直接改变根目录绑定或项目身份；位置调整需要后续relocate流程。

## 库存分类

```sh
python3 app_store_creative.py inventory --repo /path/to/project
```

工作区库存分别报告registered_files、changed_files、unregistered_files。登记时保存工作文件位置；库存对比当前字节与登记哈希，修改后的文件不会继续标为已登记。库外来源不伪造工作文件登记。

库存只读，不执行清理。未知文件始终只报告，不以内容相同推断归属。已补齐孤立CAS、缺失/损坏/隔离对象分类和本地容量估算，详见docs/artifact-inventory.md。全后端容量统计、孤立对象处置、工作文件与日志保留和完整位置变更仍待完成。
