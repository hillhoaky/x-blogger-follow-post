# Global 中文新帖发布

仅 operations.mode=publish、admin_scope=total、production_language=zh-CN、publish_authorized=true 时启用。用户授权从现在的新帖开始，旧训练稿及既有待处理项不补发。保存 publish_since、publish_floor_id；检查原帖真实时间、RSS 首次发现时间及原帖 ID。旧基线和历史状态不清空。submitting/publish_uncertain 即使早于起点也必须先只读恢复，不能遗弃不明提交。

## 内容与媒体

筛选 v3、语义去重、6小时突发时效、每轮最多3条和帖子级模型路由继续生效。中文标题与正文按已训练的事实、来源、不确定性和数字规则改写。图片以中文为目标：已有中文保留，纯英文有实质内容时译为中文；双语主内容保留已有中文与有信息价值的英文，不生成越南文。继续去叠加水印、完整画布 QA、Image1 v2（72px短过渡），纯文字不配虚构图。视频交付能力不足就留待处理，不以文字 QA 代替全部媒体完成。

## 目标与分发

Global 是源记录层，必须使用 admin_scope:total 与 target_language:zh-CN，不能把它改成 China 列表或 Vietnam。`country_post` 是 Global 表单要求的地区下发选择，必须等于用户确认后写入 operations 的数组；不能照抄后台默认全选，不猜空数组合法性。Global 标签查询 language=en 是标签父记录接口，与中文正文不冲突。选合适现有 Global 标签，不未经授权新建。

只操作 IFXData 后台，不主动发送/编辑 Telegram 或点击 Push/MP/CMT Push。系统自身的地区生成行为以 country_post 为准。

## 单次创建与核验

当前通用 helper 的 targetCountry 仅支持越南文，不能直接传中文强行沿用。Global API 创建契约从后台 main.d102eb33.js 核实为 POST /feed/createPostSource；GET /feed/getAll?country=total 和 /feed/getPostSource?id=... 用于查重/回读。地区选择必须先获明确配置。无候选时不试发测试帖。

逐帖保存 source_status_id、source_posted_at（带时区）、admin_scope、target_language、country_post、publish_authorized、授权依据、title/body/label/important、图片清单和 publish_qa:{source_verified,text_verified,media_verified}。有完整实际证据才设 true。

创建前只查 Global 最近50条，正文作为空标题的备用比较字段；结合本地事件事实语义判定。相同事件无新增事实则跳过，记录已存在ID；不能自动改写他人旧记录。候选不明确就 review，不扩大搜索或猜 no_match。新进展可新建，但必须列清新增事实。

写入前持久化队列 submitting 与任务 publish_uncertain；仅提交一次。先读响应ID，再用Global详情回读标题、正文、标签、Important、媒体内容/顺序；全部一致后保存 verification.scope:total、title/body/label/important/media_order:true 及实际 evidence，记 published。保留来源链接与本地任务路径。

请求超时或回读不一致只恢复查询原ID/限定结果；不能重发或换到 China/Vietnam 创建。每日分别统计完整预览、部分预览与 Global 实际发布，发布项必须列 Global ID 和语言。成功后在对话简报标题、Global ID、来源与验证结果，不再把实际发布称作训练预览。

## 当前可执行路径

通用 API helper 尚未实现中文 Global 创建，因此先用已验证的 Global UI 表单创建，API 用于最近50条只读核对和按ID回读；不修改共享 x-newsfeed-post helper 的越南文流程。

1. 在 admin.ifxdata.com/dashboard/newsfeed?page=1 核对 Global 选中，再打开 New Newsfeed。
2. 将 Language 勾选精确改为 operations.country_post：取消未授权地区，不能保留默认选择。中文标题/正文、现有标签、Important Yes。
3. 中文图片 QA 后使用 UI Image1；若用通用 helper render 已套 Image1，则 UI 选 None，避免双页脚。原图仅按索引上传一次并核对顺序。
4. 记录任务与队列的提交前状态，点击 Post 一次，随后按Global ID回读。对话框消失不等于核验完成。原帖不在授权起点范围内就不填写或提交。

读取 Global 最近50条可调用基础 JS helper 导出的 setScope('total')、recentPosts(1)；详情用 newsfeed_api.py inspect --scope total --id ID。令牌只在本地已授权会话中使用，不打印。Global 标签为父记录，沿用已验证列表接口，不把正文中文误当作必须新建中文标签。
