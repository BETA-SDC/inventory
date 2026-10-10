# SDC 公共资产与物资管理

SDC 成员通过本仓库的 Issues 申请新增、借用、归还、领用、调拨或报告异常。管理员审核、确认实物操作，再维护正式台账。普通成员不编辑仓库文件，也不提交台账 PR。

当前是建设第一阶段：已确定管理规划、业务规则和申请模板，并提供管理员登记、自动校验及台账生成工具。尚未接入 Issue 自动解析、二维码标签、定期提醒和自动关闭。

## 入口

- [申请入口](https://github.com/BETA-SDC/inventory/issues/new/choose)
- [实施规划](docs/plan.md)
- [申请与审核规则](policies/workflow.md)
- [实物编号与存放位置](policies/identification.md)
- [私有信息规则](policies/privacy.md)
- [管理员操作说明](docs/administration.md)
- [自动生成的查询台账](views/README.md)

## 数据分工

| 目录 | 内容 |
| --- | --- |
| `catalogs/` | 分类和计量单位 |
| `locations/` | 房间、柜子、货架、货位及上级位置 |
| `items/` | 物品名称、型号、规格和类别 |
| `objects/` | 独立资产或食品、耗材批次 |
| `records/YYYY/MM/` | 实际收货、借还、消耗、调拨和调整记录 |
| `stocktakes/` | 盘点计划、实测结果及调整依据 |
| `attachments/` | 可以公开的实物照片和说明 |
| `views/` | 工具生成的台账，不手工修改 |
| `templates/` | 管理员填写示例及未来的标签模板 |
| `.github/ISSUE_TEMPLATE/` | 成员申请表单 |

正式数据采用 JSON，中文说明及台账采用 Markdown。字段名、编号、路径、状态值使用英文；具体内容可使用中文。不预置虚构物资、地址或管理员名单。

## 联系方式

公开申请只填写 GitHub 用户名和已有的私有联系人条目链接。手机号等信息按组织规范保存到 [community-private-information](https://github.com/BETA-SDC/community-private-information)，不得填写到公开 Issue、照片、文件或评论中。没有权限的成员联系管理员办理，管理员确认联系方式已登记。

## 管理员工具

```bash
python3 scripts/inventory.py check
python3 scripts/inventory.py build
python3 -m unittest discover -s tests -v
```

CI 只有读取仓库和校验的权限，不依据公开申请自动改写正式文件。
