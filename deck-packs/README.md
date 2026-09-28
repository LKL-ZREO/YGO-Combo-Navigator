# Deck packs

正式卡组包使用 `.ygopack` 扩展名，本质上是一个 ZIP 文件。包内至少包含：

- `manifest.json`：卡组包元数据以及 YDK、展开图文件名；
- 一个 `.ydk`：随包提供的推荐构筑；
- 一个 `graph.json`：与该构筑配套的展开图。

图中的卡片必须使用数字 `cardId`，不要使用显示名称作为主键。

`nodes` 表示可以从截图状态接入的局面；`edges` 表示用户接下来执行的动作；带有 `result` 的节点是经过验证的终场。运行时会尝试匹配所有节点，因此受到干扰后可以从另一条路线的中间节点继续。

实际卡组包应随卡表版本维护。`example/graph.json` 只用于展示格式，不代表真实可用的 Master Duel 路线。

当前可测试的数据包：

- `kewl-tune-md`：Kewl Tune 的首批社区路线；
- `crimson-powerforce-md`：新账号单份“深红力量”结构卡表和首批标准路线。

构建卡组包：

```powershell
python -m app.tools.build_deck_pack deck-packs/crimson-powerforce-md
```

构建完成后会生成 `deck-packs/crimson-powerforce-md-0.1.0.ygopack`，用户只需在程序中点击“导入卡组包”。

