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

## 2026-09-20：对白分段与阅读节奏

**本节来源均为搜索结果中出现的标题/摘要片段，未打开原文**，因此按本台账规则记为「待阅读」，不构成标准符合性声明。

| 候选来源 | 链接 | 想用它回答什么 | 当前证据状态 |
|---|---|---|---|
| Netflix Timed Text Style Guide（English UK） | https://partnerhelp.netflixstudios.com/hc/en-us/articles/30806198616339-English-UK-Timed-Text-Style-Guide | 定时文本按阅读速度控时长、单条有最短/最长与行宽约束 | 仅见标题与摘要片段；待阅读 |
| BBC R&D WHP306（字幕速率研究） | http://downloads.bbc.co.uk/rd/pubs/whp/whp-pdf-files/WHP306.pdf | 字幕速率与理解度的经验区间 | 仅见摘要片段；待阅读 |
| Pošta (2012) 字幕标准（经 Masaryk University 学位论文二手引用） | https://is.muni.cz/th/seuk9/Diploma_Thesis-AJP-Kachynova.docx | 单条字幕最短约 1–1.5 秒、并有上限 | 二手引用；需回溯原文 |
| 国家标准《无障碍音视频出版物通用技术规范》（起草稿） | https://std.samr.gov.cn/dcpspTools/gbPlan/download?path=%2Fzxd%2F2024004172%2F20_%E6%A0%87%E5%87%86%E8%B5%B7%E8%8D%89%2F20_WD_2024004172_%E6%97%A0%E9%9A%9C%E7%A2%8D%E9%9F%B3%E8%A7%86%E9%A2%91%E5%87%BA%E7%89%88%E7%89%A9%E9%80%9A%E7%94%A8%E6%8A%80%E6%9C%AF%E8%A7%84%E8%8C%83.pdf | 中文单行字数与字幕呈现的一般约束 | 起草稿；待核对正式发布版 |
| Ren'Py preferences 文档；Lemma Soft 社区「Average reading speed?」 | https://ja.renpy.org/doc/html/preferences.html ； https://lemmasoft.renai.us/forums/viewtopic.php?p=61847 | 视觉小说既有做法：自动前进、每字速度可调、用户可切换 | 社区资料；非标准 |

- 采用结论（工程默认值，非合规声明）：长台词按中英标点切句、每段不超过 14 字、按约 6 字/秒折算时长并夹在 1.2–4 秒，保留「逐句 / 整段」用户开关。
- 对应实现：`web/src/dialogue.ts`（`splitSentences` / `splitDialogue` / `chunkDurationMs` / `planDialogue`）、`web/src/Stage3D.tsx`（说话气泡逐段显示）、`web/src/App.tsx`（工具栏开关）。
- 验证方式：用项目自带 esbuild 转译后跑样例输入，核对分段与时长输出（结果记入验收文档）；构建类型检查通过。未做浏览器人工观感验收。
- 限制：上述数值是可配置默认值，**不声称符合任何标准**；待读过原文后再评估是否按标准调整。
