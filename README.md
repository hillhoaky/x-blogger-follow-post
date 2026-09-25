# IFXData X 跟帖助手

通过 RSS 跟踪 X 博主的新帖，核对原文和媒体，完成选题过滤、事件去重、正文改写与图片 QA，并在明确授权后发布到 IFXData。

内部 skill 标识仍为 `x-blogger-follow-post`，现有安装路径和巡航入口无需更改。

## 工作流程

- **中文训练预览**：展示原文、改写稿、修改说明、来源、标签及处理后的图片；完整预览与媒体待处理的部分预览分别记录，保存草稿不算展示。
- **恢复与去重**：区分暂时故障和需满足具体恢复条件的阻塞，复用共享账本、基线及单一编排者，避免重复处理或重复发布。
- **筛选回归**：包含 17 个选题和事件去重案例，以及离线契约检查；语义案例仍需模型或人工评审，不能仅靠脚本证明编辑判断正确。
- **授权发布**：提供 Vietnam 越南文流程和 Global 中文流程。Global 支持授权起点后新帖的范围检查；发布前必须配置下发地区并完成独立 QA，提交后回读核验。

## 默认配置与依赖

仓库默认 `chat_preview`、`publish_authorized:false`，不因安装或更新而启用发布。示例来源为 `@fxtrader`，配置位于 [sources.json](references/sources.json)。发布目标、下发地区及新帖起点须按用户授权配置，不补发旧训练稿。

需要本机的 `x-newsfeed-post` skill 提供媒体与发布基础工具，以及相应浏览器、图片处理能力和 IFXData 登录授权。本仓库不包含登录凭据、运行账本或训练媒体。

完整使用规则见 [SKILL.md](SKILL.md)，Global 配置见 [global-publishing.md](references/global-publishing.md)。

## 离线检查

```sh
python3 scripts/self_check.py
python3 scripts/filter_regression.py --help
```
