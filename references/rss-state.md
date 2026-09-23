# RSS 与账本操作

将 `SKILL` 替换为已发现的本 skill 绝对路径。默认账本为 `~/Documents/Codex/skill-state/x-blogger-follow-post/fxtrader/state.json`，不随任务目录变化。脚本只探测 RSS 和维护本地账本，不访问 X、不做语义过滤、不发布。

```bash
python3 "$SKILL/scripts/rss_queue.py" probe
python3 "$SKILL/scripts/rss_queue.py" queue
```

`probe` 使用条件 GET，30 秒超时。首个成功快照默认全部 `baseline`；后续首次见到且大于初始基线 ID 的帖子进入 `discovered`，包括比上轮发现 ID 更小的延迟条目。顺序和重复 GUID 不影响去重。原帖正文/图片必须到 X 再核实。

只有首次明确要求“发最新 N 条”才用：

```bash
python3 "$SKILL/scripts/rss_queue.py" probe --bootstrap-latest 1
```

若网络权限不可用，使用获准的工具下载相同 feed，保存 XML 到当前任务 `work/`，再 `probe --feed-file /absolute/feed.xml`。不要用 X 主页替代 RSS。离线测试必须 `--state /absolute/work/test-state.json`，不得污染真实基线。

## 状态

`baseline` / `skipped` / `previewed` / `published` 为自动处理终态；`discovered` / `review` / `blocked` / `prepared` 是待处理；`submitting` / `publish_uncertain` 只能回读恢复。发布前把任务文件、图片和记录放在共享账本附近的 `posts/<id>/`，不要仅留临时目录。

网络失败、空 feed、坏 XML、错误来源不推进状态；报错不是“无新帖”。部分无法解析的条目出现在 `feed_issues`，需要报告。重试只做一次；仍失败留待下一次获准检查。RSS 是有限窗口，长时间停机可能漏掉已滚出 feed 的帖子，不能声称历史完整。

同 ID 的 RSS 指纹变化只更新缓存，不重建候选。基线、跳过、预览、发布终态不自动复核或提醒。只有尚未完成的候选设置 `source_changed`，在到期处理该候选时核对 X，确认后记录 `source_change_reviewed:true`；不能因字段变化突破重试冷却。不要把 RSS 时间当权威修订时间。旧帖复核由用户明确指令触发。

常规巡航用 `scripts/patrol.py --output-root <当前任务>/outputs`；底层 `rss_queue.py probe --compact`只输出新ID、到期候选、延后数量和检测异常，省略完整历史和事件库。必要时使用`queue`读取详细记录。

## 记录决定

先写 UTF-8 JSON 记录，再执行：

```bash
python3 "$SKILL/scripts/rss_queue.py" mark --id 123 --record /absolute/result.json
```

跳过示例：

```json
{"status":"skipped","rule_id":"CN_EQUITY","rule_version":2,"reason":"原帖及图表主体均为A股收盘行情，对本次受众不适用。"}
```

准备完成示例（`task_path` 指实际文件）：

```json
{"status":"prepared","rule_id":"MARKET_RELEVANT","rule_version":2,"reason":"原帖主体为美联储利率消息。","relevance":"美元与外汇交易读者关注的政策信息。","x_verified":true,"event_key":"美联储|利率决议|事件日期","key_facts":["原帖经核实的核心事实"],"event_relation":"new","task_path":"/absolute/posts/123/task.json"}
```

提交前：`{"status":"submitting","reason":"Vietnam字段和媒体QA通过，准备单次提交。","task_path":"/absolute/posts/123/task.json"}`。该任务文件必须有正确 `source_status_id`、`target_language:vi`、`admin_scope:vn`、`publish_authorized:true`。

提交后不明：`{"status":"publish_uncertain","reason":"提交后回读尚未确认，恢复仅查Vietnam记录。"}`。

回读确认后：`{"status":"published","reason":"Vietnam逐项回读一致。","task_path":"/absolute/posts/123/task.json"}`。脚本检查 [vietnam-publishing.md](vietnam-publishing.md) 的证据结构；这些证据必须来自实际核对，不能为了通过验证伪填。

若提交前发现已有完全相同的 Vietnam 记录，先完成同样的回读，再使用 `published` 加 `adopt_existing:true`、`rule_id` 和 `rule_version`；不额外创建。已跳过/基线帖的历史补发需要明确用户范围和账本审查，脚本不提供清空或强制重置开关。

账本原子写入并加短时文件锁；跨任务不得并发发布同一博主。用现有 heartbeat 承接后续调度，避免重复创建任务导致竞争。


当前 chat_preview 模式：prepared 后完成图片和正文 QA，展示后使用 `status:previewed`，task 必须有 `publish_authorized:false` 和 `preview_verified:true`。即使旧任务误留 publish_authorized:true，脚本仍阻止提交；只有新用户明确授权的单条 override 或已切换的正式发布模式才可提交。probe 结果在账本旁 runs/ 中留运行日志供日报使用。
