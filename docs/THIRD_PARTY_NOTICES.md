# 第三方代码与资产声明

## FeiControl：仅设计参考

来源：[Fibi66/FeiControl](https://github.com/Fibi66/FeiControl)，固定 commit `6c3f7ff2de9dd8b24e153ede615176f7a0c0a61d`。

已核对缓存 LICENSE：MIT，`Copyright (c) 2026 Mission Control Contributors`。已核对 ATTRIBUTION：FeiControl 改编自 [TenacitOS](https://github.com/carlosazaustre/tenacitOS)，原作者 Carlos Azaustre，上游声明为 MIT。

本项目参考状态驱动舞台、相机预设和占位角色思路，没有复制 FeiControl/TenacitOS 源代码、GLB、贴图、图标、数据、API 或页面结构。上述 MIT 不是本项目整体许可证，也不能推定覆盖全部截图、GLB 或 OpenClaw 数据。若未来复制任何文件，须保留适用版权、MIT 文本、上游署名链，并单独核对资产许可。

## 运行依赖

2026-09-19 追加参考范围：AgentDesk 的小字号名称与选中提示、Office3D 的详情面板分层。新标注排布算法与界面代码为本项目独立实现，未引入 FeiControl 的源文件或素材；MIT/上游署名信息沿用上文。

根目录 `requirements.txt` 锁定本次 Python 直接依赖；前端完整解析版本见 `web/package-lock.json`。安装目录中的 LICENSE/NOTICE 是对应包的许可依据，发布依赖包时应保留。

本轮读取了 three、React、Drei 的 MIT 文件，Vite 的 LICENSE.md 和 TypeScript 的 Apache-2.0 文本开头。此范围不等于完成所有传递依赖许可证审计；不虚称全量审计通过。

## 内部来源和自有资产

旧项目代码的来源版本与权属边界见 `PROVENANCE.md`。本项目角色和舞台采用自有程序化几何体，无外部 GLB/图片/音视频资产。后续实际引入素材时逐项追加来源、作者、许可、署名和修改记录。
