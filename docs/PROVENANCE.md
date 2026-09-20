# 来源与复用边界

## 内部剧情核心

来源：用户已有工作区 `D:/Deepseek harness workplace/baytech2026/workspace`。该 Git 工作树 HEAD 为 `1d52a03404829abe77b759e05e1a19d69cc46164`，但 `core/narrative/` 是未提交文件，不能用 HEAD 冒充这些文件的准确版本。因此以 2026-09-19 的 SHA-256 作为复制来源标识。

| 源文件（相对旧 workspace） | SHA-256 |
|---|---|
| `core/narrative/models.py` | `2C178827C5B4BD57F45886D5A97ACE9D7813F30FE9D6CD2336B73B5D02628490` |
| `core/narrative/sandbox.py` | `EB15E38234709617193168158592E8FFA088CE7EED9D8A40D5BF3E708A850F04` |
| `core/narrative/repository.py` | `BB8E7F791999F8F184A4B550A85E75353BFF7BFF0D192E990643138952258336` |
| `core/narrative/service.py` | `F6E60C2F663FA2F52CDD84AE3268C53F6436EA786D8F182D069DBEC0B6EBEB8F` |
| `core/engine/engine.py` | `5EB672598F6D440FDADD38478C1892CA803C54DF04FE27CE9C06ECAB70C6451C` |
| `core/engine/entity_state.py` | `BC676881D08E1B0FFCA488034B3339ECF45D51AC701495F74B0F941D2B17669B` |

这些是源文件 hash，不代表新项目文件与来源逐字相同。移植需要解除 `core.engine`、旧 LLM 客户端、旧数据库与平台配置的依赖，新项目运行时不得导入旧工作区。本轮实际复制/改写清单见下方迁移记录。

版权：在以上源文件头部与旧 workspace 根目录未找到明确的版权人或许可证文件，不推定它们为 MIT，也不虚构作者。此次复用根据用户对自己项目代码的明确授权进行内部开发；不替来源另行授予开源许可。

## FeiControl

固定参考：[Fibi66/FeiControl](https://github.com/Fibi66/FeiControl/tree/6c3f7ff2de9dd8b24e153ede615176f7a0c0a61d)，MIT。采用抽象设计启发，未纳入其源文件和资产。参考范围和读取位置见 `REFERENCES.md`，许可证及上游署名链见 `THIRD_PARTY_NOTICES.md`。

本项目程序化低多边形角色和场景属于新实现，不从 FeiControl 或 TenacitOS 拷贝模型。后续新增外部资产时须登记文件、作者、来源 URL、许可、修改范围和署名位置。

2026-09-19 标注调整：复查 FeiControl 的 AgentDesk、AgentAvatar 与 Office3D。参考小字号描边名称、颜色/光圈提示和独立详情面板；本项目另行实现屏幕坐标避让、引导线、优先级、标注开关及底部可折叠事件卡。没有复制其组件或资产；精确链接和阅读边界见 REFERENCES.md。

### 内核迁移完成清单（2026-09-19）

- `backend/director_core/models.py`：复制后移除 legacy scenario converter，保留 SceneSpec/世界状态归一化与实体规则输入。
- `backend/director_core/sandbox.py`：复制后切换为本地 `agent.py`、`entity_state.py`，保留 role_context、候选投影、可见性、道具转交/拾取/披露裁决。
- `backend/director_core/repository.py`：复制 SQLite checkpoint/revision/lock/preview/commit 语义；数据库默认为 `data/director.db`，环境变量为 `DIRECTOR_DB`。
- `backend/director_core/service.py`：复制作者控制流程，并通过 `offline.py` 注入离线角色策略；不创建真实模型客户端。
- `backend/director_core/agent.py`：提取旧 `engine.py` 的角色基础状态与事件格式化方法；`entity_state.py`：复制实体状态内核。两者均在新项目内运行，源文件 hash 见上表。
- `backend/director_core/offline.py`、`scene_input.py`、`engine.py`：新项目适配层，提供移动、回应、道具交付、信息披露、指令和 HTTP 契约映射。

新运行时 `rg` 检查无 `from core` 或 `import core`；启动时不依赖旧工作区路径。

## 2026-09-20：账号与令牌模块移植

来源：用户旧小说平台 `api/auth.py`（自有代码，用户授权内部复用）。

| 项 | 内容 |
|---|---|
| 源文件 | `D:/Deepseek harness workplace/小说写作平台/api/auth.py` |
| SHA-256 | `2FDFC56B58761C3596B17DA47D34D8B52DD0964692DA65B49EBA8F63297B51B3` |
| 移植目标 | `backend/director_core/auth.py` |

**保持等价**：PBKDF2-HMAC-SHA256（20 万次迭代 + 每账号随机盐）、自签 HMAC 令牌
（`base64url(payload).base64url(hmac_sha256(secret, payload))`，payload 含用户名/过期/token_version）、
`hmac.compare_digest` 恒定时比较、`token_version` 全量吊销、账号表先写临时文件再替换。

**改写范围**（逐条）：
- 环境变量前缀 `NOOVEL_*` → `DIRECTOR_*`（AUTH_DIR / AUTH_SECRET / TOKEN_TTL_DAYS / QUOTA_DAILY_TASKS / QUOTA_MAX_CONCURRENT）；
- 账号目录默认 `output/auth` → **`data/auth`**（新项目自己的数据目录，绝不读写旧平台账号表）；
- 令牌有效期默认 30 天 → **7 天**；口令最短 6 位 → **8 位**（本版计划公网访问）；
- 未移植：旧平台的限流（rate_limit）、登录事件日志、管理台页面、配额的实际扣减逻辑（字段保留）；
- 新增：`has_users()` 与 `owner_username()`，用于"还没有账号时保持单机单用户行为"的平滑过渡。

**验证**：`backend/tests/test_auth.py` 14 条离线测试（口令校验、用户名/口令规则、令牌往返与过期、
签名篡改、全量吊销、改口令失效旧会话、停用/启用、无账号时保持单机、管理员优先、列表不含盐与散列、Bearer 解析、删号）。
**限制**：账号表是单文件 JSON（适合几十个账号，不适合大规模并发写入）；未做注册与找回口令，账号由管理员创建。
