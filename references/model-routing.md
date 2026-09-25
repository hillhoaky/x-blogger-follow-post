# 帖子级模型路由

仅在 `patrol.py` 返回 `action:work` 时读取本页。目标是在不拆散单帖编辑责任的前提下降低常规轮次成本。

## 不调用模型的步骤

下列步骤保持确定性脚本执行：

- `patrol.py`、RSS 请求与解析
- 日报日期检查和 `daily_report.py`
- 队列、状态、事件记录和报告回执写入
- Image1 合成、文件校验、上传和 API 回读

`action:idle` 或纯 `reports_first` 轮次不创建内部模型执行者。

## 每条帖子只路由一次

编排者按候选 ID 从旧到新串行处理，并在实质编辑前为每条候选选择执行模型。不要并行处理多条帖子，不要为模型路由新建 Codex 用户任务、线程或定时器。

### Sol medium

使用 `gpt-6-sol`、`medium` 处理：

- 纯文字或媒体结构简单、事实关系清楚的帖子
- 明确命中 `CN_COMPANY`、`CN_EQUITY` 或其他既有过滤规则的内容
- 没有引用链、地点/时间冲突或来源身份疑问的普通宏观、市场和外交信息
- 最多一张简单照片或短文字图，且不需要复杂 OCR、版面重建或多图一致性判断

### Astra high

出现任一条件即使用 `gpt-6-astra`、`high`：

- 中国公司、中国内部政治、国际政治或跨境经贸之间的边界分类不明确
- 正文、引用帖、配图或时间换算之间存在冲突
- 转帖/引用链复杂，当前帖与旧帖的正文和媒体归属难以确定
- 事件语义去重难以判断 `duplicate`、`update` 或 `new`
- 多图、长图、密集文字、表格、图表或中英混排需要复杂 OCR、翻译规划与视觉 QA
- 人物身份、机构归属、来源可信度或不确定性表达需要额外判断

路由证据不足时选择 Astra，不能为了节省成本让 Sol 猜测。

## 单帖责任与交接

选定模型后，由同一个内部执行者完成该帖的精确 X 核对、过滤、事件语义比较、训练稿、修改说明、图片处理决策和 QA 结论。编排者只负责调度、最终一致性检查和账本写入。

委派时使用最小上下文，只提供该帖 `task.json` 路径、精确 status URL、当前规则版本和必要的相关事件 ID；不要复制完整对话、完整 Skill、历史账本或无关帖子。内部执行者不得直接标记 `prepared/previewed/published`，也不得调用发布接口。

在开始前创建或补充最小 `task.json`：

```json
{
  "source_status_id": "...",
  "source_url": "https://x.com/.../status/...",
  "mode": "chat_preview",
  "publish_authorized": false,
  "model_route": {
    "model": "gpt-6-sol",
    "reasoning_effort": "medium",
    "complexity": "standard",
    "triggers": []
  }
}
```

Astra 路由将对应字段写为 `gpt-6-astra`、`high`、`complex`，并列出实际触发项。最终 `task.json` 保留该信息，供成本复盘和日报统计扩展使用。

## 受控升级

若 Sol 在核对精确原帖后才发现 Astra 条件：

1. 在起草和图片编辑前停止，不能先完成一版再让 Astra重写。
2. 将已经确认的原文、时间、引用关系、媒体清单和升级原因写入 `task.json`。
3. 将 `model_route` 更新为 Astra，并添加 `upgraded_from: "gpt-6-sol"`。
4. Astra 只读取该 `task.json`、对应源文件和必要事件记录后继续。

每条帖子最多升级一次。升级后不降级，也不把同一帖子拆给多个模型分别改写和 QA。
