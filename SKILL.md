---
name: x-blogger-follow-post
description: 通过 RSS 发现指定 X 博主的新帖，按东南亚受众需求过滤，将正文及图片改为越南文，在 IFXData Vietnam Newsfeed 发布并回读验证。用于“x博主跟随发帖”、fxtrader 跟帖、RSS 新帖检查和过滤库维护；单个指定 X 帖子的一次性发布使用 x-newsfeed-post。
---

# X 博主跟随发帖

RSS 发现更新 → 对应 X 原帖 → 过滤 → 越南文改写与图片 PS → IFXData **Vietnam 版本**发布 → 回读记录。默认 `@fxtrader`，配置见 [sources.json](references/sources.json)。

## 常规巡航入口

已启用任务每轮只运行 `scripts/patrol.py --output-root <当前任务绝对路径>/outputs`。脚本先查本地日报日期，再做一次 RSS 条件请求，只返回新 ID、到期未完成项或新故障。`action:idle` 即安静结束，不读取其余参考、完整账本、浏览器或后台；同一任务已读规则无需逐轮重读，规则更新或有实际工作时按需读取。

- `reports_first`：按返回日期先运行 `daily_report.py`（延迟项加 `--delayed`），逐日展示摘要与报告链接；通过 `patrol.py --output-root ... --ack-report YYYY-MM-DD` 记录本任务已展示日期，然后再运行巡航入口检查 RSS。已有报告无需重复生成。
- `work`：读取 [operations.md](references/operations.md) 和本次处理所需参考，按下文完成新帖/到期未完成项。事件去重时再用 `rss_queue.py queue` 读取事件资料。
- `notice`：仅告知新故障、恢复或需要用户处理的事项。原有故障未变化保持安静；日志留给日报。
- 已有 `baseline/skipped/previewed/published` ID 的 RSS 字段变动只更新缓存，不自动打开 X、不作为新稿或修订任务。用户明确要求复核/改稿时才处理旧帖。

## 范围与依赖

- 有成稿工作时才读取并复用本机 `x-newsfeed-post/SKILL.md` 的准备、标签、图片、Image1规则，通常位于 `~/.codex/skills/x-newsfeed-post/`。实际发布获准后再读上传与提交规则。本 skill 的运行模式、Vietnam 路由、图片语言与去水印规则优先。
- **当前运行模式为 chat_preview（对话训练）**：正常完成发现、选题、事件去重、改写、图片 PS 和 QA，在当前对话展示完整训练稿；不上传、不提交 IFXData，任务 `publish_authorized:false`。每条预览必须同时展示：原帖原文、拟改写稿、具体修改说明、原帖链接、拟用标签和处理后全部图片。训练稿语言由 `operations.preview_language` 控制；当前为中文，先训练事实取舍和编辑方式。越南文可以作为内部 production draft 保存，但不替代对话中的中文训练稿。持续处理新帖，不等待用户逐条点评，也不先做一批样本等待整体校准。用户反馈随做随改。只有用户明确要求结束预览并开始后台发布，或明确指定某条实际发布，才切换相应范围的授权。
- 用户已同意每 10 分钟检查一次、每轮最多产出 3 条；当前产出指对话预览，未来获准发布后才指实际发布。每天河内时间 24:00（次日 00:00，Asia/Ho_Chi_Minh）汇总刚结束的自然日。调度与时效详见 [operations.md](references/operations.md)。复用已有 heartbeat，不重复创建。
- 每次检查一份 RSS 快照，候选按原帖 ID 从旧到新串行处理；不刷 X 主页找新帖，不擅自补发历史。

## 1. RSS 检测与队列

读取 [rss-state.md](references/rss-state.md)，运行 `scripts/rss_queue.py`。正确 URL 为 `https://rss.app/feeds/ar9gRF2tWDZD8ThY.xml`，不含用户链接中黏连的中文说明。

- RSS 只负责发现原帖链接、ID、时间；摘要/缩略图不能替代 X 原文和原图。
- 首次默认建立快照基线，不把 feed 的旧帖全当新帖。明确“发最新一条/补发 N 条”时首次用 `--bootstrap-latest N`；已有基线的历史补发由用户指定帖子，保留原账本，不能清空状态。
- RSS 故障、空 feed、解析失败是检测异常，不等于没有新帖；不得改用 X 主页探测。
- 按 `博主 + X status ID` 去重，并按 [operations.md](references/operations.md) 做语义事件去重。发现、预览、实际发布分别入账；失败不丢弃。重复事件没有新事实就跳过，有新数据/官方确认/实质进展才作为更新；同一帖子修订不自动重发。
- 跨任务复用固定状态路径，单一发帖执行者。脚本文件锁只保护账本写入，不能代替执行者协调。

## 2. 原帖核对与过滤

只对 RSS 队列中的候选打开精确 status URL。核对作者、ID、正文、时间、引用/转推上下文和全部媒体。登录失败、删除、正文截断、缺图或视频不可读取时记 `blocked`，不凭 RSS 摘要补写。非该博主链接记录异常，不能当其原创发布。

浏览器核对只提取目标帖的正文、时间、引用和媒体区域；不反复输出评论、推荐、趋势等整页内容。使用有上限的加载等待；同一故障本轮只重试一次，失败项至少30分钟后重试。

读 [filters.json](references/filters.json) 和 [editorial.md](references/editorial.md)。关键词只是提示；按完整主题判断，包括图中文字。

- 跳过中国股市、中国政治类；跳过无明确东南亚价值的中国本地资讯、广告引流和无财经信息的闲聊。
- 考虑全球宏观、外汇、黄金、能源、国际股票/科技、加密资产及东南亚财经。中国经济数据、央行政策、人民币、商品需求有明确跨境价值时可考虑；不能因为“中国”或姓名就误杀。
- 人物身份补全适用于通过筛选的稿件，不是发布中国政治帖的理由。混合主题不明则 `review`。
- 记录决定、规则 ID、具体原因、东南亚相关性、规则版本与原帖证据；跳过也入账。

## 3. 越南文正文与图片

依 [editorial.md](references/editorial.md) 改写客观的越南文标题/正文：补国家/职务与机构全称，观点注明归属；保留数字、时间、因果关系和不确定程度。身份或时点疑问查权威原始来源，不凭记忆填当前职务。

逐图检查并保持媒体顺序，按用户指定规则 PS：**中英混排且两者均为主内容时，只把中文改成越南文，英文原样保留；全英文主内容改成越南文；全中文改成越南文。英文正文中只有零星中文界面标签时，正文及标签一起越南文化。去除来源图片上的水印。** 原始 logo/图表图例等有信息意义的标记与叠加水印区分，不能误删数据。无文字也无水印的照片保留；只有水印的图也需清除水印。完整规则见 [editorial.md](references/editorial.md)。用图像编辑工具，PS 和逐张视觉 QA 后再套 Image1。

复用 `prepare_task.py`，逐张定 `keep/translate`，记录 `target_language:vi`、`admin_scope:vn`、`source_status_id`、标题/正文/标签与有序图片清单。默认 `Image1`、Important `Yes`，不加自制水印/页脚。预览不依赖后台可用；标签可按已有标签记录准备，不为预览创建标签。纯文字帖按 0 图片处理，不伪造图片；视频/动图超出现有图片流程时记待处理。

## 4. 对话预览与 Vietnam 发布

当前模式完成后，在对话依次展示：原帖原文、训练语言标题/正文、逐条修改理由、原帖链接、按顺序排列的处理后图片、拟用标签与必要的处理说明。图片必须实际显示，不能只报“已完成PS”。记录 `previewed`；不伪填 Newsfeed ID，不把预览计作发布。单帖原帖/图片/PS受阻则记原因、继续后面的合格帖，不让单条卡住整轮。训练阶段不调用后台/API做标签、查重或发布dry-run；使用已有标签缓存和本地账本，缺少标签记录时明确写拟用标签。`task.json` 同时保存 `training_preview_language`、`training_draft_title`、`training_draft_body`、`training_edit_notes` 和未来发布用的越南文稿字段。

用户明确授权实际后台发布后，才读 [vietnam-publishing.md](references/vietnam-publishing.md)。使用已核实路由的 **Vietnam 专用 API helper**，页面作为备用；通用 helper 涉及 Global，不能直接用于本流程。当前 chat_preview 禁止写入，API 核验不阻塞预览。

在 Vietnam 查重，完成字段与图片 QA；持久化 `submitting` 后仅提交一次。无响应或中断视为 `publish_uncertain`，只回读恢复，不能重发或换路由重发。必须在 Vietnam 核对记录 ID、标题/正文、标签、Important、图片内容/顺序才记 `published`。

有发布授权时连续完成准备、PS、QA、上传、提交、验证，不加中间确认。需要新建标签时遵守基础 skill 的单独授权；已有合适标签直接复用。

## 5. 报告与迭代

每日按 [operations.md](references/operations.md) 生成报告，严格区分已预览与已发布。报告发现数、预览数、发布数、跳过原因和待处理项；发布项列 Vietnam Newsfeed ID、标题、原帖链接、标签、图片数/样式。检测失败或发布未确认不得报成功。

用户反馈新规则后修改过滤库或编辑库的对应条目/版本，加说明边界的例子。旧的跳过记录不自动重发。运行脚本自检和 skill validator；维护 skill 不创建测试 Newsfeed。
