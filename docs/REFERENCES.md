# 参考资料台账

本表只把实际打开的原文或固定快照记为已阅读。候选链接不能写成已验证结论。阅读日期：2026-09-19。

| 来源/固定版本 | 本轮实际阅读范围 | 采用处 | 限制 |
|---|---|---|---|
| [FeiControl](https://github.com/Fibi66/FeiControl)，commit `6c3f7ff2de9dd8b24e153ede615176f7a0c0a61d` | 读取旧工作区缓存中的 commit.json、README、LICENSE、ATTRIBUTION；MovingAvatar 的初始定位/碰撞判断/目标位置逻辑；AvatarModel 的占位与 GLB 分支；Office3D 的 Canvas、相机预设、轮询和 Suspense 位置 | 状态与渲染分离、统一舞台、相机预设、缺少模型时占位、舞台与信息面板分层 | 仅参考思路；不复制源代码、GLB、图片、图标、OpenClaw 数据、API 或页面结构；其监控办公室不提供剧情裁定和作者提交语义 |
| [Three.js 文档](https://threejs.org/docs/)、[React Three Fiber 文档](https://r3f.docs.pmnd.rs/) | 待阅读；本轮仅核对已安装依赖的版本/许可 | 后续查证 API 和渲染资源生命周期 | 不宣称已经阅读官方文档 |
| [SQLite Transaction](https://www.sqlite.org/lang_transaction.html) | 当前文档作者未重新阅读；旧项目台账记有已读快照 | 仅作为旧 narrative 事务实现的背景线索 | 本表不据此宣称新项目并发验证或 SQLite 合规完成 |

FeiControl 证据位置：旧工作区 `baytech2026/runs/references/feicontrol/`。固定 commit 以该目录 `commit.json` 的 `sha` 为准；先前计划里缺少字符的 hash 已修正。

新增引用须记录：名称/作者或机构、URL、版本、实际访问时间、阅读范围、采用结论、对应文件、限制和验证方式。未阅读来源保持待阅读。

## 2026-09-19：3D 标注与交互复查

- 来源与作者：Fibi66/FeiControl，版权声明 Mission Control Contributors；上游 TenacitOS / Carlos Azaustre。固定版本仍为 `6c3f7ff2de9dd8b24e153ede615176f7a0c0a61d`。
- 实际读取：GitHub 固定版本 tree API、[AgentDesk.tsx](https://github.com/Fibi66/FeiControl/blob/6c3f7ff2de9dd8b24e153ede615176f7a0c0a61d/src/components/Office3D/AgentDesk.tsx)、[AgentAvatar.tsx](https://github.com/Fibi66/FeiControl/blob/6c3f7ff2de9dd8b24e153ede615176f7a0c0a61d/src/components/Office3D/AgentAvatar.tsx) 原文；旧缓存中 Office3D.tsx 的选择、详情面板和相机段落，以及 LICENSE、ATTRIBUTION.md。
- 已核实设计：AgentDesk 用小字号 Three.js Text、描边、状态颜色、悬停/选择材质和地面光圈提示对象；Office3D 将被选对象详情放在 Canvas 外的 AgentPanel，并在手机隐藏左右信息列表。
- 采用结论：舞台文字保持短小、颜色帮助辨认、选择后展开详情。对应自有实现 `web/src/Stage3D.tsx`、`WorldStage.tsx`、`StageLabels.tsx`、`stage.css`。
- 自有设计补充：屏幕像素字号、引导线、角色投影包围框避让、标签优先级与拥挤隐藏、底部两行事件卡。上述避让功能不是所读 FeiControl 组件的现成功能，不声称来自该项目。
- 验证方式：前端 TypeScript/构建检查以及本地浏览器的标注开关、角色选择、镜头和窄屏视觉检查；实际结果另记验收文档。
- 复用限制：只借鉴信息分层，不复制代码、模型、图片、数据、品牌或监控面板结构；未新增第三方资源和依赖。
