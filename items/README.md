# 物品定义

每种名称、型号、规格一致的物品建立一个 JSON 定义，按分类存放。

必填字段：`id`、`name`、`category`、`unit`。使用分类目录规定的类型，单位使用 `catalogs/units.json` 中的整数基本单位。

参见[填写模板](../templates/item.json)。包装换算及保存条件自动匹配在第二阶段实现。
