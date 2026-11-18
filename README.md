# Vouchpin（券钉簿）

骨架：券事件入湖 → 核销事实钉扎 → 核销后退回（单一入口）→ 批次互证。

本地：
- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）
- 回归：`cd backend && python -m pytest tests/`（负向入湖链路四场景：改脏原批合计 /
  事件有事实无 / 半截改脏原批 / 目标日预览缺负向行）

## 核销后退回：全局互斥的两条策略（只走一条）

唯一入口 `POST /api/redeem/return`（按事实钉扎态分派，同事务写事件湖+事实）：

- **未钉冲销（open 事实）**：仅 open 核销事实允许写 `void` 事件（负额）并作废该事实
  （行保留、状态 `voided`，审计不删行）；只能落在事实原业务日；预览合计同步减少，
  之后可对本日重钉。
- **已钉只追加（sealed 事实）**：已钉日事实与 sealed 批笔数/合计永不回改；退回必须落到
  另一业务日的 `return` 事件，并物化为该日的负向退回事实（`kind='return'`，open，供后续
  钉扎）；原批仍为现行凭证。目标业务日已钉扎或与原业务日相同都会被拒绝。

同源约束：退回入口、事实状态、事件湖、钉扎写闸、批次现行合计同出一源——
`POST /api/events` 只接受 issue/redeem，void/return 一律走退回入口；
仪表盘/预览合计只认在效事实（open+sealed，含负向 return 行），voided 不计入。
原批只读闸：钉时指纹 = 批头笔数/合计 与本批 sealed 明细重算一致，且每条 sealed 事实金额
锚定其源事件金额（事件湖只增不改）；负向写路径在提交前自检「原批指纹未动 + 负向事实链
齐套」，任一未对齐整事务回滚，回执不得成功。`GET /api/batches` 列表与
`GET /api/batches/{id}` 原批对照（钉时明细 + 关联退回链）均实时重算指纹与退回关联。
禁止「页显示已退但 sealed 合计未变且事实仍 sealed」的撕裂态；禁止无审计硬删事件行；
禁止「回执成功却改脏原批」与「有负向事件无负向事实仍当成功」。
