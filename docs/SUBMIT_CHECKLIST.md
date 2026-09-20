# 提交清单与现场操作（2026-09-20）

截止：**14:00 关闭提交通道**。本文件是当天唯一操作指引；每一步都给了可照抄命令。

## 一、交付物清单

| 交付物 | 状态 | 位置 / 说明 |
|---|---|---|
| 可演示应用（工具） | ✅ 可跑 | 后端 `8200` + 导演台 `5274`；赛道要求"单点跑通即可" |
| PPT ≤5 页中英双语 | ✅ 已生成 | `docs/PITCH_DECK.pptx`（5 页，封面嵌入真实生成背板图）；文本版 `docs/PITCH_DECK.md`；改内容后重跑 `py -3.13 scripts/make_deck.py` |
| Demo 演示视频 | ⬜ 待录 | 见下方"录制脚本"（3–5 分钟，真实运行） |
| 赛期迭代痕迹 | ✅ 已有 | `git log --oneline`（2 个提交，见下方"提交历史"） |
| 来源与复用披露 | ✅ 已有 | `docs/PROVENANCE.md`、`docs/REFERENCES.md`、`docs/THIRD_PARTY_NOTICES.md` |
| 验收证据 | ✅ 已有 | `docs/ACCEPTANCE.md`（含真实模型与 T1 实跑记录） |

## 二、服务启停（**不要**用 start.ps1：端口可能被手工进程占用）

当前由手工进程托管，PID 记录在 `.runtime/backend.manual.pid`、`.runtime/web.manual.pid`。

```powershell
# 查看状态
curl.exe -s http://127.0.0.1:8200/api/v1/runtime     # 模式与模型（徽标同源）
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:5274/

# 重启后端（改代码/改 .env 后必须重启）
$pid = Get-Content .runtime/backend.manual.pid; Stop-Process -Id $pid -Force
$R = (Get-Location).Path
$env:PYTHONPATH = "$R;$R\backend;$R\backend\.depsclean"
Start-Process -WindowStyle Hidden py -ArgumentList '-3.13','-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8200'
# 起好后把真实监听 PID 写回 .runtime/backend.manual.pid
(Get-NetTCPConnection -LocalPort 8200 -State Listen).OwningProcess | Set-Content .runtime/backend.manual.pid

# 重启前端
$wpid = Get-Content .runtime/web.manual.pid; Stop-Process -Id $wpid -Force
Set-Location web; Start-Process -WindowStyle Hidden node -ArgumentList './node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5274','--strictPort'
```

## 三、切换真模型 / 离线规则

```powershell
# .env 已被 .gitignore 忽略，绝不提交
# DIRECTOR_MODEL_MODE=live|offline ；留空则"有密钥=live，无密钥=offline"
# 改完重启后端，界面徽标会同步显示
```

判断标准：界面徽标显示「真模型试演 · deepseek-v4-flash」= live；显示「离线规则试演」= offline。
无论哪种模式，界面上都写明来源，**答辩时以徽标为准**。

## 三·五、可直接演示的场景（已配好素材）

| 场景 ID | 内容 | 素材 | 适合展示 |
|---|---|---|---|
| `scene_c020e6b6488a` | 董事会，已提交 3 个事件（含 2 处**可见降级**记录） | 背板 + 3 立绘 | 事实透镜与降级记录（推荐首选） |
| `scene_d5f679bcab8d` | 董事会主线 r16、48 个事件、2 个分支 | 背板 + 3 立绘 | 分支与回放 |

入口：`http://127.0.0.1:5274/scene/scene_c020e6b6488a?branch=main`

## 四、录 Demo 脚本（3–5 分钟，真实运行）

1. 打开 <http://127.0.0.1:5274/>，输一句想法 → 确认设定 → 建立场景。
2. 点「推进一步」→ 展示三位角色各自的候选（不是轮流发言）。
3. 点一条事件 → 展开「提议 → 检查 → 结果 → 状态变化」。
4. 点关键道具 → 展示事实透镜（谁持有 / 谁已知 / 依据）。
5. 编辑一句台词并**锁定** → 重新生成 → 证明锁定不被覆盖。
6. 加一条导演指令 → 推进 → 展示指令被采纳与检查记录。
7. 点「预览与检查」（正式 revision 不变）→ 点「提交剧情」→ revision +1。
8. 工具栏点「生成美术素材」→ 背板 + 立绘出现，悬停看提示词与模型。
9. 切到「整理输出」→ 由选中事件生成场次卡 / 剧本 / 分镜草稿。
10. 录屏里保留终端或徽标，证明是当场运行。

## 五、提交历史（赛期增量证据）

```
d0433ed feat(web): 导演台界面、2.5D/3D 舞台、回放与美术素材层（赛期实现）
8ec4446 feat(backend): 短剧导演台后端内核与真实模型接入（赛期实现）
```

用 `git log --oneline` 与 `git status --short`（应为空）当场证明：**提交都是赛期内产生的**，
工作区干净、没有未纳管的改动。

## 六、提交与打包（14:00 前）

```powershell
# 1) 冻结：确认工作区干净后打标签
git tag -a submit-2026-09-20 -m "BAYTECH 2026 提交状态"
git log --oneline --decorate | head -5

# 2) 不要打包这些内容
#    .env（密钥）、data/（数据库与素材）、.runtime/（日志与 PID）、web/node_modules、backend/.deps*
#    它们都已在 .gitignore 中

# 3) 需要交付的文档
#    README.md、docs/（ACCEPTANCE / PITCH_DECK / PROVENANCE / REFERENCES / THIRD_PARTY_NOTICES / SCENE_MANIFEST / RESPONSIVE_QA）
```

## 七、答辩口径（三句话）

1. **这是什么**：面向短剧编剧与导演的可视化 AI 导演台——角色先演一遍，作者看见依据、随时干预、最后定稿。
2. **两个亮点**：看见 Agent 怎么演（提议→检查→结果）；剧情事实透镜（谁持有/谁已知/依据，非法动作可见降级）。
3. **边界**：不一键生成整部作品、不做电影级 3D、事实判定分级提醒且允许作者覆盖；真模型与离线规则可切换并如实标注。

## 八、已知限制（主动说明，比被问出来好）

- 运行模式：现场若走 live，模型质量与延迟有随机性；离线规则作为断网备份（界面会标注当前模式）。
- 3D：程序化布景 + 立绘精灵，未做骨骼动画与真实寻路；生成式 3D 资产属下一步。
- 事实判定：规则 + 模型判定可能漏判/误判，因此只做分级提醒与可见降级，不静默改写。
- 视觉验收：不同 GPU / 窗口尺寸 / WebGL 丢失回退需要人工在浏览器里再核一遍（见 `docs/RESPONSIVE_QA.md`）。
