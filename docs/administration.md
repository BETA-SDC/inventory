# 管理员操作说明

目前所有登记在管理员本地进行，不会因为成员提交 Issue 自动记账。已有申请可使用 [Issue 草稿导入](requests.md)减少重复填写，并用[标签工具](labels.md)打印实物编号。

## 启用

仓库所有者在 `catalogs/administrators.json` 填写实际管理员 GitHub 用户名。成员身份和手机号在既有私有信息仓库核实，不复制到本仓库。

登记实际位置、物品定义和资产或批次，再登记实际入库。目录初始为空是正常状态。

## 填写与登记

管理员先拉取最新主分支，把对应 `templates/*.json` 复制到忽略的 `.scratch/` 目录。填写实际信息，删除 `id` 字段，工具分配编号。不要把模板中的示意日期和 Issue 编号直接作为真实数据。

```bash
git pull --ff-only
python3 scripts/inventory.py add location --input .scratch/location.json
python3 scripts/inventory.py add item --input .scratch/item.json
python3 scripts/inventory.py add object --input .scratch/object.json
python3 scripts/inventory.py add record --input .scratch/record.json
python3 scripts/inventory.py check
python3 scripts/inventory.py build
```

每次操作只运行需要的命令。已有物品或对象直接引用，不重复创建。食品对象填写 `expires_on`。多件资产分别创建对象。

`add` 在写文件前校验完整候选台账；失败不写正式文件。该工具是单管理员本地工具，不支持同时在同一工作目录登记。多管理员推送冲突时保留草稿，重新拉取最新数据、重新分配编号并检查，不强推。

## 业务字段

所有业务均需：`type`、`object`、`quantity`、`occurred_at`、`issue`、`operation_key`、`administrator`、`reason`。

- `occurred_at`：实际发生时间，含时区，例如 `2026-10-10T10:00:00+08:00`。
- `issue`：本仓库申请编号，正整数。
- `operation_key`：本申请内唯一的英文小写操作键，例如 `receipt-1`。同一申请分批处理使用不同键；重复登记相同键会被拒绝。
- `location`：库存操作的来源位置；入库和归还时表示目标位置。
- `receive` / `adjust-in`：增加位置库存。
- `consume` / `writeoff` / `adjust-out`：减少位置库存，资产不能使用 `consume`。
- `transfer`：填写不同的 `destination`，从来源移到目标位置。
- `loan`：仅借用资产，额外填写 `borrower`（GitHub 用户名）和 `due_on`。
- `return`：额外填写 `loan`（原借出操作编号），仅在管理员检查后登记，可返回不同位置。
- `hold` / `release`：整件资产或整个批次隔离／解除隔离，`quantity` 固定为 1，无需位置。

记录按操作编号顺序重放，而非按实际时间排序；补登记保留实际时间，在当前记账顺序检查余额。复杂跨历史纠错需要管理员复核，一期不自动推断。

消耗数量必须为整数基本单位，不能填写“半箱”。隔离是针对整个对象，部分批次隔离以后实现。外借资产损毁后核销、延期及 Issue 自动处理尚未实现，在 Issue 保持待处理，不能通过假归还结清。

## 提交

检查差异，确认不含敏感资料、编号与实物一致，再提交并推送。一个实际操作及相应生成台账放在同一次提交。

```bash
git diff --check
git diff
.venv/bin/python -m unittest discover -s tests -v
git add locations items objects records views catalogs
git commit -m "Record inventory operation for issue #N"
git push
```

管理员将提交链接记录到 Issue，完成规定的检查后再关闭申请。第一阶段不会自动发送评论。
