# YGO Combo Navigator

PC 版 Master Duel 的手动截图展开导航器。目前完成的是第一阶段基础设施：

- 枚举并选择 Master Duel 窗口；
- 用户点击后连续截取多帧，选择变化最小的稳定帧；
- 载入和编辑归一化 ROI 配置；
- 在截图上显示手牌、我方场区和阶段区域；
- 保存原始截图和带标注的调试截图；
- 没有启动游戏时，可以打开本地截图进行校准。
- 一键导入同时包含 YDK 和展开路线的 `.ygopack` 卡组包；
- 从本地缓存或卡片 API 补全卡片资料和卡图；
- 优先显示 Master Duel 简体中文卡名，并为新导入卡组缓存缺少的中文名；
- 为当前构筑生成感知哈希和颜色特征索引。
- 扫描手牌区和我方场区，显示可排除的候选识别结果；
- 导入结构化展开图，从任意匹配节点返回多条剩余路线；
- 选择路线后，在下一次分析中判断正常推进或受阻重规划。

## 启动

```powershell
cd F:\YGO
python -m app.main
```

也可以先以可编辑模式安装：

```powershell
python -m pip install -e .
ygo-navigator
```

## 测试

```powershell
python -m pytest
```

## 第一阶段使用方法

1. 将 Master Duel 设置为 16:9 窗口、Windows 显示缩放 100%、简体中文界面。推荐 1920×1080；1600×900 也可使用，但需要按实际画面校准 ROI。
2. 启动程序，点击“刷新窗口”。
3. 选择 Master Duel 窗口，等待画面动画结束，然后点击“截取稳定画面”。
4. 在右侧选择 ROI，通过 `X/Y/宽/高` 调整区域。
5. 点击“保存 ROI 配置”。
6. 点击“保存调试图”保存原图和带框截图。
7. 点击“导入卡组包”，选择一个 `.ygopack`；程序会同时载入构筑和展开路线，并准备卡图特征。
8. 设置当前主要阶段和通常召唤权，点击“分析当前截图”。
9. 排除误识别候选后点击“按勾选结果匹配路线”。
10. 选择路线；受到反制且结算后重新截图并再次分析。

## 导入卡组包

点击“导入卡组包”，程序会从 `.ygopack` 中同时读取 YDK 构筑、展开图和版本信息。如果本地缺少卡图，程序会下载当前构筑所需的图片并生成视觉特征；再次导入时优先复用本地缓存。

构建项目自带的示例包：

```powershell
python -m app.tools.build_deck_pack deck-packs/crimson-powerforce-md
```

## 从 YDK 和展开草稿创建卡组包

创作者不需要了解 .ygopack 内部目录。准备一个 YDK 和一个符合
schemas/combo-draft.schema.json 的草稿 JSON，然后运行：

    python -m app.tools.create_deck_pack --ydk deck-packs/crimson-powerforce-md/crimson-powerforce-structure.ydk --draft examples/combo-draft.example.json --output deck-packs/crimson-powerforce-demo-0.1.0.ygopack

草稿中的卡片一律填写中文或英文卡名，编译器只会在输入 YDK 内解析。卡名缺失或存在歧义时会直接报错，不会猜测卡片 ID。每个步骤必须在 changes 中明确描述手牌、场上、墓地、除外区、通常召唤次数、已用效果和限制的变化。

## 使用 AI 从攻略创建卡组包

自动模式支持直接输入攻略文本、UTF-8 文件或公网网页。设置 OPENAI_API_KEY 后运行：

    python -m app.tools.author_deck_pack --ydk deck.ydk --guide-url https://example.com/guide --name "我的卡组" --output my-deck.ygopack

不使用内置 API 时，可以把标准提示词交给任意 AI：

    python -m app.tools.author_deck_pack --ydk deck.ydk --guide-file guide.md --prompt-output authoring-prompt.md --prompt-only

将 AI 返回的 JSON 保存后再回灌：

    python -m app.tools.author_deck_pack --ydk deck.ydk --guide-file guide.md --response-file ai-response.json --output my-deck.ygopack

AI 输出会先经过元数据锁定、卡名解析、状态迁移、图编译和卡组包校验。失败时自动模式会根据编译错误重新生成，默认最多三次。详细流程见 docs/ai-deck-pack-authoring.md。

`examples/kewl-tune-core.ydk` 是用于测试识别管线的核心卡池，不是合法的完整构筑。正式分析应导入玩家在 Master Duel 中实际使用的完整构筑。

新账号选择“深红力量”后，可以直接导入 `deck-packs/crimson-powerforce-md/crimson-powerforce-structure.ydk`。这份文件精确对应单份原始结构包：主卡组 40 张、额外卡组 8 张。

## 展开包

仓库自带三个包：

- `deck-packs/example/graph.json`：仅用于格式和测试；
- `deck-packs/kewl-tune-md/graph.json`：Cue 单卡标准路线的首批社区转录数据。
- `deck-packs/crimson-powerforce-md/`：单份“深红力量”准确卡表，以及首批共鸣者标准展开路线。

校验展开包：

```powershell
python -m app.tools.validate_deck_pack deck-packs/kewl-tune-md
python -m app.tools.validate_deck_pack deck-packs/crimson-powerforce-md
```

Kewl Tune 和 Crimson Powerforce 路线数据目前标记为 `COMMUNITY_TRANSCRIBED`。它们需要在本机 Master Duel 中逐步验证，之后才能改为 `VERIFIED`。

默认 ROI 是按 1920×1080 制作的归一化初始估计值，会按实际 16:9 客户区缩放。第一次在真实游戏中运行时，仍需要根据实际 UI 微调。

## 当前限制

- 只提供以 `md-zh-hans-1920x1080` 为参考的 16:9 归一化配置；
- 手牌重叠识别仍需要用真实 Master Duel 截图校准阈值；
- 当前 Kewl Tune 包只包含 Cue 单卡标准路线；
- 墓地、除外区、额外卡组消耗和效果使用状态尚未自动识别；
- 最小化的游戏窗口不会参与枚举；普通窗口遮挡不影响后台客户区截图；
- ROI 校准针对游戏客户区，不包含窗口边框。

