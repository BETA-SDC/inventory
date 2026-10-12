# 提醒报告

报告从正式台账计算，不会修改物资文件、Issue、标签或库存。它适合管理员定期检查，也可以通过 GitHub Actions 生成下载产物。

```bash
.venv/bin/python scripts/reports.py \
  --as-of 2026-10-12 \
  --expiry-days 7 \
  --output output/alerts.md
```

报告包括：

- 预计归还日期早于报告日的借用；
- 报告日到未来指定天数内到期的食品批次，也包括已经过期但仍有库存的批次；
- 处于 `hold` 状态、等待管理员处置的对象；
- 当前各货位库存。

逾期和临期报告只是提醒。管理员仍需查看 Issue 和实物，再通过 Issue 流程处理归还、过期、损毁或报废；报告不会自动创建 Issue，也不会自动关闭申请。

仓库的 `Generate inventory alerts` Workflow 每周生成一次报告；也可以手动运行并填写报告日期。Workflow 只读仓库内容，报告作为 Actions artifact 保存。GitHub 定时任务可能延迟，管理员应以实际检查为准。
