# 筛选与事件去重验收 v1

修改 filters.json 或事件判定规则时运行；正常巡航不加载整套案例。固定案例包含两天训练中纠正的外交/中国公司摘要及合成边界题；摘要不是逐字原帖证据，不可用于发布。

先导出不含答案的输入：

```bash
python3 scripts/filter_regression.py export --output /absolute/work/cases-input.json
```

执行者只读当前 filters.json、operations.md 的事件规则及导出输入，逐条语义判定，不访问 X/后台、不处理账本、不根据关键词自动分类。记录每题 id、reason；filter 题填写 decision/rule_id；event 题填写 event_relation/incremental_facts（duplicate/new 为 []，update 必须列出实际新事实）。输出 JSON 数组。

判定后再评分：

```bash
python3 scripts/filter_regression.py grade --predictions /absolute/work/decisions.json
```

缺题、重复 ID、多题、错误分类/规则、错误事件关系或缺失 update 增量均返回非零退出码并列出题号。评分器只对照结构化答案，不能自动判断自由文本增量是否属实，须人工/模型复核理由与实际新事实。不要将期望答案复制成预测后声称模型通过测试。案例全部通过仅证明这套有限案例；不是线上准确率。

新增用户纠正时补输入、期望、边界及历史 ID。规则确实变更才更新答案并记录原因，不能为使测试通过改答案。条件允许可独立评估；自查必须标记 self_review，不能声称独立盲测。
