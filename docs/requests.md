# 从 Issue 生成管理员草稿

此工具只读取公开 Issue，不发送评论、修改标签、关闭 Issue 或提交 Git。实际业务文件仍由管理员确认后生成、审查并提交。

## 准备

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
git pull --ff-only
.venv/bin/python scripts/requests.py prepare --issue 123 --output .scratch/issue-123.json
```

将 `123` 替换为实际申请号。工具优先使用 `opencli gh`，不可用时使用 `gh`。账号必须能读取本仓库。输出仅允许在忽略的 `.scratch/` 内，且不覆盖已有草稿。

也可以从 `gh issue view --json number,url,title,body,author` 导出的公开 JSON 离线准备草稿：

```bash
.venv/bin/python scripts/requests.py prepare --input .scratch/issue-export.json --output .scratch/review.json
```

离线输出只能用于准备；正式 `check` 和 `apply` 都重新从 GitHub 读取申请，不能绕过内容变更检查。

## 管理员复核

草稿不复制申请正文和联系方式，保留内容摘要哈希、字段问题和对象库存摘要。疑似手机号检测只是辅助，不能代替人工检查正文和附件。

管理员依次完成：

1. 查看原 Issue、评论及附件，核实申请人是 SDC 成员。
2. 按组织规范核对私有联系方式；本工具不读取私有仓库。
3. 解决 `form_problems`。表单修改后重新生成草稿；不能通过删除草稿中的问题绕过检查。
4. 核实实际操作。草稿不会把预计领取时间当成已经领取时间。
5. 将 `confirmed_member`、`confirmed_contact`、`confirmed_physical_operation` 设为 `true`。
6. 补齐 `records` 中的管理员、实际时间、原因、位置和数量等字段，检查业务类型与实物一致。

借用、归还、消耗、调拨在识别已有对象后生成初步操作。资产数量默认为一；食品、耗材数量仍由管理员明确核实，避免误把规格或日期识别为数量。归还按原借用申请查找未结借出记录。

新增入库、异常和盘点可解析模板并提示缺漏，但不猜测处置动作；先由管理员登记位置、物品及对象，再重新导入 Issue，填写适用的业务记录。一个申请可以包含多个操作，每个 `operation_key` 必须不同。

## 检查并登记

```bash
.venv/bin/python scripts/requests.py check --draft .scratch/issue-123.json
.venv/bin/python scripts/requests.py apply --draft .scratch/issue-123.json
python3 scripts/inventory.py build
.venv/bin/python -m unittest discover -s tests -v
git diff --check
git diff
```

`check` 不写业务文件。`apply` 校验当前 Issue 摘要、当前台账摘要、管理员确认和整组候选操作，再一次性登记本申请的实际操作；普通写入失败会清理此次新增记录。正式记录保存申请内容摘要，不保存正文。

Issue 标题、正文或申请人变更会要求重新生成、复核草稿。台账有任何变化也需要重新生成，避免管理员持有旧库存；申请评论不在摘要范围内，管理员在入账前仍须查看评论中的补充与撤回。

重复应用同一草稿被拒绝。按同一 Issue 重新生成草稿时，相同操作键也不能重复入账。分批交付时使用新的明确操作键，并核对已登记数量。

一期不支持多个进程同时写同一工作目录，也不自动处理不同管理员之间的 Git 冲突。保持单人单工作目录操作，推送冲突时重新拉取、复核；工具检查不是完整的权限系统，仓库写权限仍须限制在管理员。

审核确认不写业务记录；必须完成实际交接才执行 `apply`。归还必须先经管理员检查。最后由管理员提交、推送，并在 Issue 中说明实际结果及提交链接。
