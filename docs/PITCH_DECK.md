# 路演材料：5 页双语 PPT + 3 分钟脚本

现场提交版：[PITCH_DECK.pptx](./PITCH_DECK.pptx)（5 页，中英双语）。同一份最终文件也保存在 [PITCH_DECK_FINAL.pptx](./PITCH_DECK_FINAL.pptx)。逐页讲稿见 [PITCH_SCRIPT.md](./PITCH_SCRIPT.md)。

项目：**可视化 AI 导演台**（短剧剧情创作工具）  
赛道：**AI 应用与工程**  
演示时长：3 分钟展示 + 2 分钟问答

## 第 1 页｜封面

**中文**：可视化 AI 导演台——让角色先演一遍，你来定稿。  
**English**：A Visual Director's Desk for Short Drama — Let the cast play the scene out. You decide.

一句话：多个角色在同一个沙盘里行动、交流、互相影响；导演观察、干预、确认，再整理成剧本与分镜草稿。封面图是本工具生成的董事会会议室背板。

## 第 2 页｜问题与场景价值

- AI 给出对白，却没有解释角色为什么这样说，过程是黑盒。
- 短剧新手很难同时守住冲突、信息差、道具和人物目标。
- 改一处台词，下一次生成可能覆盖已有决定。
- 我们从一句话想法开始，帮助用户完成一场可检查、可修改的戏。

English: AI returns text without the reasoning behind a character's line. Beginners struggle to keep conflict, information, props and goals consistent. The product helps them finish one playable scene through visible, author-controlled rehearsal.

## 第 3 页｜24 小时增量

1. **剧情结构层 / Dramatic structure**：本场契约、5 个剧情节拍、8 项规则检查。
2. **过程可见 / Visible process**：检查提议、事实检查、最终动作和状态变化。
3. **作者掌控 / Author control**：预览、锁定、导演指令、分支试演，作者推进节拍。
4. **来源诚实 / Honest provenance**：live/offline、素材、输出和润色均保留来源。
5. **一句话开场 / One-line opening**：角色、道具、事实和舞台布局随题材适配。

## 第 4 页｜技术与边界

- React + TypeScript + three.js；FastAPI + SQLite；OpenAI 兼容模型；Seedream 视觉层。
- live / offline 模式在界面显示；显式 live 缺密钥会拒绝启动。
- 复用的是用户自己的叙事内核，源文件 hash 和改写范围已记录。
- 3D 参考 FeiControl（MIT）的交互思路，没有复制代码或资产。
- 不承诺一键生成整部作品；3D 不是电影级；剧情检查是作者辅助提示。

## 第 5 页｜现场演示与下一步

现场流程：一句话想法 → 确认契约、角色与舞台 → 推进一轮 → 检查候选事件 → 修改对白并锁定 → 预览 → 提交 → 推进节拍与回放 → 整理场次卡、剧本和分镜。

下一步：真模型长时稳定性与费用评估；更多题材的场景 manifest 与可行走路线；image-to-3D 资产；多人协作。

收尾：把最难观察和修改的角色互动，变成看得见、能干预、可追溯的工作台。

## 答辩备用回答

| 问题 | 回答 |
|---|---|
| 和普通 AI 剧本工具有什么区别？ | 它们主要给文本，我们给可控的过程：提议、检查、结果都可查，还能落到可拍的场次与分镜。 |
| 用了 AI 吗？ | 用了，规则允许；界面和事件会标注模型、规则、素材和输出来源。 |
| 事实检查一定正确吗？ | 不一定。它是分级提示，作者可以覆盖，系统不会静默改写正式剧情。 |
| 3D 做到什么程度？ | 交付是可切换的 2.5D / 3D 舞台、程序化布景、角色行走、镜头预设和 WebGL 回退；电影级资产是后续方向。 |
