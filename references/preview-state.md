# 预览与阻塞契约 v1

适用于新增状态写入；保留旧历史，不能把旧 `previewed` 自动视作通过新版验收。编排者负责最终核对、展示及写账。脚本只能检查声明和本地文件，无法证明模型真的核对了原帖或消息真的送达，不能为了通过检查伪造证据。

## 完成标准

- `prepared`：原帖、筛选、事件去重与任务文件已准备，不代表展示或全部媒体已完成。
- `preview_partial`：原帖全文和文字事实已核对，已在当前对话展示原文、训练稿、修改说明、来源、拟用标签及现有合格图片；明确列出每一项缺失媒体及原因。媒体仍待处理，不计为完整预览、不允许直接提交。
- `previewed`：文字和全部应交付媒体通过 QA，完整训练预览已实际展示。纯文字原帖也须核对媒体确实为零后设 `media_verified:true`。
- `blocked`：尚不能提供可靠文字预览，或后续处理受阻。不得凭 RSS 摘要补全文；已展示的部分预览记录保留。

视频超出现有图片流程属于媒体能力阻塞。文字能独立核准就展示部分预览；关键事实只能从尚不可读的视频获得时，文字不能设为已核对。视频作为核实证据与视频成品交付分别判断，能播放不等于能完成本地化交付。

`task.json` 保存以下字段（示意，必须填写实际原文及检查结果）：

```json
{
  "source_status_id": "123",
  "admin_scope": "vn",
  "target_language": "vi",
  "mode": "chat_preview",
  "publish_authorized": false,
  "source_text": "精确 X 原帖全文",
  "training_preview_language": "zh-CN",
  "training_draft_title": "训练标题",
  "training_draft_body": "训练正文",
  "training_edit_notes": ["实际修改与保留说明"],
  "preview_verified": false,
  "preview_progress": {
    "text_verified": true,
    "media_verified": false,
    "media_pending_reason": "原帖唯一视频尚无本地化交付能力"
  }
}
```

在任务 outputs 下保存实际展示内容为 MD；**先展示，后写账**。新 `previewed` 或 `preview_partial` 记录必须提供 `displayed_in_chat:true`、带时区的 `displayed_at` 和非空绝对路径 `display_evidence`。只保存了稿件未展示时保持 prepared/blocked，不填回执。

完整预览：task 的 `preview_verified:true` 且 `preview_progress.text_verified/media_verified:true`。部分预览：`preview_verified:false`、text 为 true、media 为 false，填写媒体缺失原因。`preview_partial` 还需要与 prepared 相同的筛选、原帖核对和事件字段，并填写下述阻塞字段；供后续新帖语义去重使用。

部分预览也占本轮最多 3 条的展示额度。同一文字版本已经展示就不重复输出；媒体完成后展示完整成品，`preview_partial -> prepared -> previewed`，不重复生成文字或重做已通过 QA 的图片。每日分别统计两个阶段，同帖可能在两栏出现，不能相加当作新帖数。

## 阻塞分类与恢复

新增 blocked/preview_partial 必须填写 `block_kind`：

| 类型 | 适用情况 | 恢复方式 |
|---|---|---|
| transient | 暂时网络、页面加载或工具服务失败 | 本轮同故障最多重试一次，再冷却至少 30 分钟；缺省由脚本生成 retry_after |
| capability | 缺少视频导出、本地化或所需工具能力 | 填具体 resume_condition，不填 retry_after；有能力变化证据后恢复 |
| access | 需要登录、权限或用户操作 | 填具体恢复条件；确认访问已恢复后继续 |
| editorial | 事实冲突或缺失依据，现有资料不能解决 | 填所需证据/判断；新证据或明确用户指令后继续 |

非暂时故障不会自动到期；RSS 字段变化也不会唤醒它。`resume_condition` 应具体，例如“已获得可核验的视频文件且视频交付流程已定义”，不能只写“稍后重试”。恢复进入 prepared/review 等状态时带 `resume_evidence`，说明实际变化或用户明确重试指令。换模型本身不是视频工具能力恢复的证据。

更新同一非暂时阻塞仍保持等待；把它改成 transient 也必须提供恢复依据，不能借改分类绕过等待。首次新故障/恢复/新需操作事项通知，未变化不重复提醒；其他候选照常继续。

旧无分类 blocked 保留原冷却行为，只有审阅实际阻塞证据后才补类型，不批量猜测迁移。旧 terminal 不重置、不自动补发。仅补阻塞分类不算发生预览。
