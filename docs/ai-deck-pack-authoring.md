# AI 卡组包创作流水线

第二阶段把创作者输入拆成三个稳定部分：YDK、攻略来源和 ComboDraft。AI 只负责把攻略转换成 ComboDraft，卡名解析、状态检查、公共节点合并、图生成和卡组包压缩全部由本地程序完成。

## 自动模式

设置 OPENAI_API_KEY 后，向命令提供 YDK 和攻略文本、UTF-8 文件或公网网页：

    python -m app.tools.author_deck_pack --ydk deck.ydk --guide-url https://example.com/guide --name "我的卡组" --output my-deck.ygopack

程序会生成受 JSON Schema 约束的请求。AI 输出如果无法编译，程序会把本地编译器的错误反馈给 AI 并重新生成，默认最多三次。API 密钥只从环境变量读取，不会写入草稿或卡组包。

## 任意 AI 模式

先导出完整提示词：

    python -m app.tools.author_deck_pack --ydk deck.ydk --guide-file guide.md --prompt-output authoring-prompt.md --prompt-only

把 authoring-prompt.md 交给任意支持长文本的 AI，将其返回的 JSON 保存为 ai-response.json。然后使用同一份攻略重新执行：

    python -m app.tools.author_deck_pack --ydk deck.ydk --guide-file guide.md --response-file ai-response.json --output my-deck.ygopack

回灌的 JSON 会经过与自动模式完全相同的校验。AI 不能修改命令确定的 deck_pack_id、名称、版本、规则集、作者、来源或 DRAFT 状态。

## 攻略来源限制

- 文件支持 UTF-8 文本、Markdown 和 HTML，最大 2 MiB。
- 网页只允许公网 HTTP 或 HTTPS，拒绝本机、局域网、保留地址和带账号密码的 URL。
- HTML 中的脚本、样式、SVG 和 noscript 内容不会进入提示词。
- 攻略正文被当作不可信数据，提示词明确禁止执行正文中的指令。
- 超长正文最多保留 120,000 个字符。

## 生成产物

- output.ygopack：可以直接由主程序导入的卡组包。
- output.draft.json：通过本地编译器验证后的 AI 原始草稿，便于人工审阅和继续修改。
- 可选 prompt-output：发送给 AI 的完整提示词，可用于复现或更换 AI。
