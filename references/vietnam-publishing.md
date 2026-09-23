# Vietnam 发布路由

## 已验证的 Vietnam 接口

2026-09-23 从当前后台 `main.d102eb33.js` 的完整相关函数分支核实，并对列表/详情做了只读请求。证据见 [vietnam-api-evidence.json](vietnam-api-evidence.json)。接口根路径为 `https://api.ifxdata.com/api/v1/admin`：

- Vietnam 创建：`POST /feed/createPost`，`countryPost:["vn"]`、`typePost:"sortPost"`、认证 userId、title、source、labelId、important、JSON 字符串 fileUpload、imageTicket:null。
- Vietnam 列表/查重：`GET /feed/getAll?country=vn&pageNum=N&pageSize=100`。
- Vietnam 详情/回读：`GET /feed/getFeedId?id=<Vietnam ID>`；实际回读的 language 为 vn。
- Vietnam 更新：`POST /feed/updatePost`，pathName:vn；只有明确要求修改既有内容才用。
- 上传：现有 `/uploadFile`。标签沿用该 Vietnam 表单实际使用的 `/feed/getNewsfeedLabel?language=en&type=1&pageSize=1000`，使用选中 ID；这是共享标签查询，不是 Global 发帖。
- Global 的 `/feed/createPostSource`、`getPostSource`、`updatePostSource` 不用于本流程写入或帖子回读。

专用 helper `scripts/vietnam_api.py` 复用现有图片渲染/上传逻辑，固定 Vietnam 路由与 language 验证，保留上传检查点、单次提交和不确定恢复；创建前即写 publish_uncertain，避免中断后再次创建。通用 skill 的 publish/update helper 不再用于本流程。

```bash
python3 "$SKILL/scripts/vietnam_api.py" inspect --id <Vietnam-ID>
python3 "$SKILL/scripts/vietnam_api.py" render --task /absolute/task.json --output-dir /absolute/output
python3 "$SKILL/scripts/vietnam_api.py" publish --task /absolute/task.json
```

render 为本地渲染；publish 无 --apply 只生成计划。**当前 chat_preview 锁定上传与后台写入**，不能为了测试接口试发。结束训练后获明确授权，将 operations.mode 设 publish、publish_authorized 设 true，并在任务记录授权，才可加 --apply。单条明确授权可在该任务记录 explicit_publish_override:true、publish_authorized:true 及 authorization_evidence，不能凭预览旧授权添加这些字段。

尚未做生产写入测试。当前抽样详情没有 newsfeedLabel；不能据此认定所有帖子都无标签。若新稿回读缺少标签关系，helper 会报不确定；通过 Vietnam UI 核对同一记录补全证据，绝不能重发。非零图片且只有数量匹配时，不自动收养同标题记录；需有有序 URL 检查点或 UI 逐图验证。

## UI 备用路径

API 契约变化或无法完成必要回读时用下面的 Vietnam UI；提交不确定后只读恢复，不能在 UI 再创建。若 Vietnam 页面无 Image1 样式控件，先用 helper render 得到最终图片再上传；不假定本地页面提供 Global 专属样式控件。

## Vietnam 内创建

1. 进入已登录 Newsfeed：`https://admin.ifxdata.com/dashboard/newsfeed?page=1`。读取控件，选版本切换 **Vietnam**，验证选中值及实际路由。不能停留 Global 后仅在新建框勾 Vietnam 来代替。
2. 在 Vietnam 列表查账本记录 ID 与精确标题候选。标题相同不等于重复，核对正文/标签/Important/媒体；完全相同则采用已有 Vietnam ID，冲突则 review。
3. 从 Vietnam 版本打开 `New Newsfeed`，按实际表单填标题、正文、现有标签、Important `Yes`。有语言字段只选 Vietnam；固定语言则记录固定值。无法验证 Vietnam 范围则待处理，不猜接口。
4. 按索引上传已 QA 的越南文图片。用 UI Image1 就上传未套样式的本地化图片；用 helper 已渲染的 Image1 图片则 UI 选 None，避免重复页脚。最终有效样式记录 Image1。
5. 复核 Vietnam 范围、全部字段、图片内容/顺序/数量和样式；持久化任务与队列 `submitting` 后仅点一次 Post。
6. 留在 Vietnam 定位精确记录，读 ID；详情/Edit 回读正文、标签、Important、语言和媒体，多图逐张核对，然后关闭编辑不保存。保存证据并记 `published`。

## 中断恢复

- `submitting` 可能已提交；重启后与 `publish_uncertain` 同样只读恢复。对话框消失、字段清空、无即时结果、网络错误都不能作为重发理由。
- 最多两次有间隔的 Vietnam 精确结果查询；不确定则记录 `publish_uncertain` 和已知 ID。之后仍只读，不能切 Global 或换 API 再提交。
- `published` 必须有 Vietnam ID 和字段/媒体证据；成功提示或 Global 父 ID 不够。
- 上传前失败可修正重试；已提交则冻结标题/正文/媒体用于恢复，先查清原结果再谈改稿。

## 任务 JSON 的实际回读证据

```json
{
  "source_status_id": "<X status ID>",
  "admin_scope": "vn",
  "target_language": "vi",
  "newsfeed_id": "<Vietnam record ID>",
  "verification": {
    "scope": "vn", "title": true, "body": true,
    "label": true, "important": true, "media_order": true,
    "evidence": "<实际回读时间、记录链接/页面路由与比对结果>"
  }
}
```

只有核对过的项目才设 true；纯文字的 media_order 代表远程媒体数确认为 0。
