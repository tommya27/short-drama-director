# 短剧剧情创作平台 MVP

独立于旧长篇小说平台的新项目。作者从一句话想法开始，让多个角色在共享虚拟世界中行动、交流、观察和互相影响；作者查看候选变化、编辑、干预和确认，再整理成场次卡、剧本和分镜草稿。3D/2.5D 是实时剧情状态的显现层。

## 一键运行（Windows PowerShell）

需安装 Python 3.13（含 Windows py launcher）和 Node.js 18+。在本目录打开 PowerShell：

```powershell
./start.ps1
```

脚本使用 Python 3.13、`backend/.depsclean` 和 `web/node_modules`。缺少依赖时会安装到项目目录，不修改全局 Python 环境。离线演示不需要 API Key。

- 导演台：<http://127.0.0.1:5274/>
- 健康检查：<http://127.0.0.1:8200/health>
- API 文档：<http://127.0.0.1:8200/docs>

停止服务：

```powershell
./stop.ps1
```

启动脚本核对端口，保存进程 ID、可执行文件、命令行、创建时间和项目根目录。8200 或 5274 被未登记进程占用时直接报错。停止脚本只停止本项目记录且身份仍匹配的进程。手动启动的服务不受脚本管理，请在其原终端停止。

日志位于 `.runtime/backend.stdout.log`、`.runtime/backend.stderr.log`、`.runtime/web.stdout.log`、`.runtime/web.stderr.log`。`./start.ps1 -SkipInstall` 禁止自动安装依赖。

## 手动运行和验证

后端：

```powershell
$env:PYTHONPATH = (Resolve-Path backend/.depsclean).Path
py -3.13 -m uvicorn api.app:app --app-dir . --host 127.0.0.1 --port 8200
```

前端（另一个终端）：

```powershell
cd web
npm ci
npm run dev -- --host 127.0.0.1 --port 5274 --strictPort
```

后端测试与前端构建：

```powershell
$env:PYTHONPATH = ((Get-Location).Path + ';' + (Join-Path (Get-Location) 'backend') + ';' + (Join-Path (Get-Location) 'backend/.depsclean'))
$env:DIRECTOR_DB = Join-Path ([IO.Path]::GetTempPath()) ('director-test-' + [guid]::NewGuid().ToString('N') + '.db')
py -3.13 -m pytest -q backend/tests
Remove-Item Env:DIRECTOR_DB
cd web
npm run build
```

## 项目边界

新应用不包含旧平台的项目页、长篇大纲、章节、风格档案、插件、设置、登录或旧导航。剧情核心在 `backend/director_core` 内独立版本化，运行时不导入 `baytech2026`。首个完整场景是董事会会议室；其他样例通过场景配置和通用适配器显现。

- `backend/`：FastAPI 服务和剧情核心。
- `web/`：React + TypeScript + Vite 导演台。
- `scene_manifests/`：自动加载的场景配置；场景数据中的 `scene_manifest` 可覆盖默认值。扩展方法见 [场景配置说明](docs/SCENE_MANIFEST.md)。
- `docs/`：来源、复用边界、第三方许可和验收清单。
- `start.ps1` / `stop.ps1`：本地运行脚本。



## 开场生成与场景样式（按输入自动适配）

**一句话想法 → 可直接确认的完整设定**（`POST /api/v1/ideas/expand`）：

- **模型路径**（live 且有密钥）：真实模型按严格 JSON 结构扩写——剧名、类型、主场地、3-4 个区域、
  3-4 个角色（公开目标/隐藏目标/秘密/公开身份/外形/行为锚点）、道具、事实，
  以及**舞台 manifest**（scene_key、名字、palette、zones 坐标、asset_set、相机预设、交互点）。
- **规则路径**（离线/无密钥/模型输出不可用）：本地确定性模板，**永不联网**。
- 返回值带 `source`（`llm` / `rule`）与可选 `fallback_reason`，**确认开场页会写明这份开场是谁生成的**，
  不做静默替换；`DIRECTOR_OPENING_MODE=rule` 可强制只走规则路径。

**场景样式随场景变化**，不需要为每个题材加代码：

1. `scene_manifests/*.json` 提供 5 个内置舞台（董事会/办公室/客栈/古宅/通用）；
2. **场景自带的 `scene_manifest` 会覆盖内置值**（前端 `layoutFor` 合并），所以开场生成时写进去的
   palette / zones / asset_set / 相机 / 交互点会直接生效；
3. `asset_set` 只允许从渲染器认识的**零件库**里选（相当于一套可拼装的景片）：
   - 通用：`table · chairs · screen · cabinet · plants · bench · pole · counter · desk · bed ·
     sofa · shelf · crate · barrel · gate · door · car · podium`
   - 形态标记：`outdoor · street · vehicle · cave`
   - 自然与工业：`rock · pine · rail · pillars · lamp · window_strip ·
     timber · track · minecart · lantern · tunnel · debris`
4. **舞台按形态渲染**（`stageForm()`：显式形态标记优先，其次按 scene_key/场景名关键词兜底，中英文都认）：
   - `interior` 室内：墙、地板、门、窗；家具按 asset 出现（会议桌/椅/屏幕/柜台/课桌/病床/沙发/货架/讲台…）；
   - `outdoor` 室外：地面、岩石、松树、护栏；
   - `vehicle` 载具：车厢顶、车窗带、长椅、立柱、驾驶台（地铁/火车/船/机舱）；
   - `street` 街景：路面、路灯、护栏、立柱、停车；
   - `cave` 矿洞/地道：岩壁、隧道拱、木支撑、铁轨、矿车、矿灯、碎石。
   非该形态的零件不会出现（例如矿洞里不会长出松树、也不会摆会议桌）；
5. 视觉身份由 T1 文生图补齐：背板提示词取自场景地点与环境设定，**同一个场景一个专属背板**；
6. **3D 里能看见角色交流**：每个有台词的角色头顶显示说话气泡（选中角色高亮），
   并用虚线指向该动作的对话对象；气泡内容来自真实事件，不是预制动画。

实测（live）：输入「华山之巅，两位旧友为同一把剑对峙…」→ 剧名《华山剑影》、区域
崖边/山巅平台/石阶入口、`scene_key=mountain-top`、`asset_set=[outdoor,rock,pine,rail]`，
背板 341KB；输入「游轮驾驶舱…」→ 《风暴航线》、舵轮平台/海图桌区/通讯台、
`scene_key=ship`、`asset_set` 含 `console,rail`。

## 美术素材（T1：文生图）

舞台的美术层由文生图产出，**作者在界面上按需触发**（舞台工具栏「生成美术素材」），不是自动生成：

| 类型 | 默认尺寸 | 提示词来源 |
|---|---|---|
| 场景背板 `backdrop` | `1024x1024` | 场景地点 + 环境设定（无人全景，用于铺底） |
| 角色立绘 `portrait` | `864x1152` | 角色外形（`appearance` / `visual_anchor`）+ 性别 + 公开身份 |
| 道具参考 `prop` | `1024x1024` | 道具名称，单独台面特写 |

- 默认模型 `doubao-seedream-5-0-pro-260628`，可用 `DIRECTOR_IMAGE_MODEL` 覆盖；供应商拒绝某个尺寸时自动退回默认尺寸，并**按实际尺寸记录**。
- 图片落在 `data/assets/`（可用 `DIRECTOR_ASSETS_DIR` 覆盖），文件名按内容哈希去重；同场景同类型同对象视为一个"槽位"，重新生成会覆盖该槽位记录。
- 每张图都在 `data/assets/index.json` 记录**提示词、模型、尺寸、时间戳、sha256**，界面素材条悬停即可看到；`GET /api/v1/scenes/{id}/artifacts` 可查。
- 端点：`GET /api/v1/images/runtime`（能力与模型名，不含密钥）、`POST /api/v1/scenes/{id}/artifacts`、`GET /api/v1/scenes/{id}/artifacts`、`GET /api/v1/assets/{asset_id}`。
- **图只做视觉层**：2.5D 用背板铺底、立绘替换占位形象；3D 用背板平面与立绘精灵。几何、走位、道具归属仍由 scene manifest 与世界状态决定，**图不参与任何剧情裁决**。
- 生成失败会显式报错（`502`），不会返回占位假图；3D 中素材加载失败只丢素材层，不影响舞台操作。

## 运行模式（live / offline）

角色候选由谁生成，取决于运行模式；**当前模式始终显示在界面徽标上**（场景页顶部与落地页页脚），不会把离线规则说成模型生成。

| 模式 | 生成方式 | 来源标记 | 生效条件 |
|---|---|---|---|
| `live` | 真实模型（OpenAI 兼容接口，默认 DeepSeek `deepseek-chat`） | 事件 `source=llm`、草稿 `generation_source=llm_role_agents` | 显式 `DIRECTOR_MODEL_MODE=live`，或未显式指定但能读到密钥 |
| `offline` | 本地确定性规则策略 | 事件 `source=offline_rule_v1` | 显式 `DIRECTOR_MODEL_MODE=offline`，或没有密钥 |

- 解析顺序：显式指定 > 环境变量 `DIRECTOR_MODEL_MODE` > 自动（有密钥=live，无密钥=offline）。
- **显式 live 但缺密钥会拒绝启动**，不会静默降级成离线规则。
- 密钥只从环境变量或项目 `.env` 读取（`DIRECTOR_LLM_API_KEY`，也接受 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`）。`.env` 已被 `.gitignore` 忽略；`GET /api/v1/runtime` 只返回模式、模型名与环境变量名，**绝不返回密钥**。
- 切换模式：改 `.env` 的 `DIRECTOR_MODEL_MODE` 后 `./stop.ps1` + `./start.ps1`；启动脚本会打印后端实际生效的模式。
- 其他可选环境变量：`DIRECTOR_LLM_MODEL`、`DIRECTOR_LLM_BASE_URL`、`DIRECTOR_LLM_TIMEOUT`。

## 当前交付状态

世界状态和草稿保存在 `data/director.db`，可通过 `DIRECTOR_DB` 指定另一数据库。删除数据库会丢失场景；正常启动和停止不会删除它。

2026-09-19 验证：独立服务健康检查返回成功，前端 `npm run build` 通过。构建提示 3D 分包约 881 kB，属于加载优化项。
2026-09-20 验证：后端 `70 passed`（2 条第三方依赖弃用警告）；接入真实模型后 `/api/v1/runtime` 返回 `mode=live / generator=llm_role_agents`，一次真实生成 3 个角色候选约 4.8 秒，事件与草稿分别标记为 `llm` / `llm_role_agents`，预览不改变正式状态、提交后正式版本递增为 1、重复提交同一幂等键保持版本不变。美术素材（T1）实跑通过：场景背板 `1024x1024 / 231KB`、角色立绘 `864x1152 / 160KB`，均带提示词、模型与时间戳。覆盖范围与反例见 [验收记录](docs/ACCEPTANCE.md)。

前端有全景、俯视、角色近景和可配置相机；支持布景清单、配色、区域坐标、道具交互点与地图渲染模式。慢速模式每轮停下等导演预览和提交，提交后等待两秒进入下一轮；不会自动提交。

可选模型入口为 `DirectorStore(db_path, generator_factory=...)`，工厂可返回 `LLMCandidateGenerator(your_client)`。客户端须提供 `chat_json(system, user, tag=...)`；只会收到隔离后的角色上下文。默认 HTTP 服务按上面的运行模式构建：有密钥走 `live`（真实模型），无密钥走 `offline`（本地规则）。
