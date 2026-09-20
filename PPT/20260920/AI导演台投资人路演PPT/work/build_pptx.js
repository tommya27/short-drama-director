const { PptxGenJS, fs, path, SLIDE_W, SLIDE_H, imgOpts, imgMap, gradientMaskB64 } = require("./build_header.js");

// ═══ Style Card：Simple Dark（暗色氛围 · 单一琥珀强调） ═══
const C = {
  canvas: "0A0A0F",   // 深岩黑：页面底色
  panel: "12121A",    // 石墨层：图表与面板底
  raised: "1A1A24",   // 抬升层：玻璃面板
  ink: "FAFAFA",      // 近白：正文与标题
  body: "D4D4D8",     // 次白：说明文字
  accent: "F59E0B",   // 琥珀金：唯一强调色
  zinc: "A1A1AA",     // 锌灰：次要说明
  faint: "71717A",    // 淡灰：注脚与来源
  hair: "FFFFFF",     // 发丝线基色（配 transparency 使用）
  rule: "26262E",     // 暗分隔线
};
const FONTS = { display: "微软雅黑", body: "微软雅黑", mono: "Courier New" };
const FS = { display: [46, 54], heading: [30, 34], sub: [20, 22], body: [15, 17], label: [12, 14] };
const RADIUS = 0.17;

// ═══ 通用 helper ═══
// 取整页背景图的绝对路径（配图失败时返回 null → 回退纯色底）
const bgPath = (key) => {
  const e = imgMap()[key];
  if (!e || e.failed) return null;
  const abs = path.resolve(__dirname, e.src);
  return fs.existsSync(abs) ? abs : null;
};

// 页底色 + 可选整页背景图（内容页统一复用同一张）
const paintBase = (s, key) => {
  const p = bgPath(key);
  if (p) {
    s.background = { path: p };
    // 画布色半透明压层：压低底图明度，保证近白正文的主导地位
    s.addShape("rect", {
      x: 0, y: 0, w: SLIDE_W, h: SLIDE_H,
      fill: { color: C.canvas, transparency: 16 }, line: { type: "none" },
    });
  } else {
    s.background = { color: C.canvas };
  }
};

// 标题下琥珀短横线（全篇统一的签名标记）
const accentRule = (s, x, y, w) => {
  s.addShape("rect", { x, y, w: w || 0.85, h: 0.045, fill: { color: C.accent }, line: { type: "none" } });
};

// 氛围光斑：3 层同心椭圆模拟柔和光晕（pptx 无法真模糊）
const ambientOrb = (s, cx, cy, d) => {
  s.addShape("ellipse", { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { color: C.accent, transparency: 94 }, line: { type: "none" } });
  s.addShape("ellipse", { x: cx - d * 0.34, y: cy - d * 0.34, w: d * 0.68, h: d * 0.68, fill: { color: C.accent, transparency: 90 }, line: { type: "none" } });
  s.addShape("ellipse", { x: cx - d * 0.18, y: cy - d * 0.18, w: d * 0.36, h: d * 0.36, fill: { color: C.accent, transparency: 86 }, line: { type: "none" } });
};

// 发丝分隔线
const hairline = (s, x, y, w, vertical, h) => {
  s.addShape("line", {
    x, y, w: vertical ? 0 : w, h: vertical ? (h || w) : 0,
    line: { color: C.hair, width: 1, transparency: 90 },
  });
};

const deck = new PptxGenJS();
deck.layout = "LAYOUT_WIDE";
deck.author = `可视化 AI 导演台`;
deck.title = `可视化 AI 导演台 · 投资人路演`;

// ══════════════════════════════════════════════════════════
// 第 1 页｜封面：一句话主张
// ══════════════════════════════════════════════════════════
const s1 = deck.addSlide();
const coverBg = bgPath("cover_main");
if (coverBg) {
  s1.background = { path: coverBg };
  // 左侧渐变蒙版：贴画布左边，端点 100% 背景色 → 完全透明，标题落在实底上
  s1.addImage({
    data: gradientMaskB64({ w: 512, h: 512, color: C.canvas, dir: "right", stops: [[0, 1], [0.5, 0.86], [1, 0]] }),
    x: 0, y: 0, w: 9.1, h: SLIDE_H,
  });
  // 底部压层，稳住页脚文字
  s1.addImage({
    data: gradientMaskB64({ w: 512, h: 256, color: C.canvas, dir: "bottom", stops: [[0, 0], [0.6, 0.55], [1, 0.92]] }),
    x: 0, y: 5.4, w: SLIDE_W, h: 2.1,
  });
} else {
  s1.background = { color: C.canvas };
  ambientOrb(s1, 11.1, 1.5, 6.4);
}

// overline：琥珀圆点 + 赛道标签
s1.addShape("ellipse", { x: 0.86, y: 1.42, w: 0.13, h: 0.13, fill: { color: C.accent }, line: { type: "none" } });
s1.addText(`AI 应用与工程赛道 · 黑客松路演`, {
  x: 1.14, y: 1.24, w: 7.6, h: 0.42, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.body, fontSize: 15, color: C.accent, charSpacing: 2.5, bold: true,
});

// 主标题（两行两框，第二行琥珀 + 光晕）
s1.addText(`让角色先演一遍，`, {
  x: 0.82, y: 1.98, w: 8.6, h: 1.0, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.display, fontSize: 52, bold: true, color: C.ink, charSpacing: -1, lineSpacingMultiple: 1.05,
});
s1.addText(`你来定稿。`, {
  x: 0.82, y: 2.96, w: 8.6, h: 1.0, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.display, fontSize: 52, bold: true, color: C.accent, charSpacing: -1, lineSpacingMultiple: 1.05,
  shadow: { type: "outer", blur: 34, offset: 0, angle: 45, color: C.accent, opacity: 0.34 },
});

// 副标题
s1.addText(`可视化 AI 导演台 —— 短剧创作的实时沙盘`, {
  x: 0.85, y: 4.16, w: 8.4, h: 0.5, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.body, fontSize: FS.sub[0], color: C.ink, charSpacing: 0.5,
});
hairline(s1, 0.86, 4.86, 7.5);

// 一句话说明
s1.addText(`多个角色 AI 智能体在共享的 3D 世界里行动、交流、互相影响；导演实时观察、干预、确认，`
  + `再把这一场戏整理成可拍的场次卡、剧本与分镜。`, {
  x: 0.85, y: 5.06, w: 7.7, h: 1.0, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 15, color: C.zinc, lineSpacingMultiple: 1.5,
});

// 页脚标签
s1.addText(`DIRECTOR'S DESK  ·  SHORT DRAMA  ·  2026`, {
  x: 0.85, y: 6.72, w: 8.0, h: 0.32, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.mono, fontSize: 12, color: C.faint, charSpacing: 2,
});

// ══════════════════════════════════════════════════════════
// 第 2 页｜市场与痛点
// ══════════════════════════════════════════════════════════
const s2 = deck.addSlide();
paintBase(s2, "bg_content");

s2.addText(`千亿短剧市场，卡点在内容供给端`, {
  x: 0.85, y: 0.58, w: 11.65, h: 0.78, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.display, fontSize: 33, bold: true, color: C.ink, charSpacing: -0.5,
});
accentRule(s2, 0.86, 1.46);

// ── 左栏：创作者的三重困境 ──
s2.addText(`创作者的三重困境`, {
  x: 0.85, y: 1.86, w: 5.2, h: 0.34, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 15, bold: true, color: C.accent, charSpacing: 1.5,
});
s2.addText([
  { text: `黑盒生成`, options: { bold: true, color: C.ink, fontSize: 17, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 3 } },
  { text: `AI 给出一段对白，却不解释角色为什么这么说——作者无从判断该不该信、能不能拍。`, options: { color: C.body, fontSize: 15, breakLine: true, paraSpaceAfter: 16 } },
  { text: `一致性失控`, options: { bold: true, color: C.ink, fontSize: 17, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 3 } },
  { text: `冲突、信息差、道具归属与人物目标互相打架，没有编剧训练的人守不住一场戏的逻辑。`, options: { color: C.body, fontSize: 15, breakLine: true, paraSpaceAfter: 16 } },
  { text: `修改被覆盖`, options: { bold: true, color: C.ink, fontSize: 17, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 3 } },
  { text: `改好的一句台词，下一次生成可能连同已经确认的决定一起冲掉。`, options: { color: C.body, fontSize: 15, paraSpaceAfter: 0 } },
], {
  x: 0.85, y: 2.32, w: 5.15, h: 3.5, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, lineSpacingMultiple: 1.38,
});

// 左栏结论：琥珀强调块
s2.addShape("rect", { x: 0.85, y: 5.94, w: 0.04, h: 0.62, fill: { color: C.accent }, line: { type: "none" } });
s2.addText(`分发端已经跑起来，供给端还在手工作坊。`, {
  x: 1.08, y: 5.92, w: 4.92, h: 0.66, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.body, fontSize: 16, bold: true, color: C.ink, lineSpacingMultiple: 1.3,
});

// ── 右栏：市场规模柱状图 ──
s2.addText(`中国微短剧市场规模（亿元）`, {
  x: 6.45, y: 1.86, w: 6.05, h: 0.34, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 15, bold: true, color: C.accent, charSpacing: 1.5,
});
s2.addChart(deck.charts.BAR, [{
  name: `市场规模`, labels: [`2024`, `2025`, `2026E`], values: [504.4, 1000, 1210],
}], {
  x: 6.45, y: 2.24, w: 6.05, h: 2.42, barDir: "col",
  chartColors: [C.accent],
  chartArea: { fill: { color: C.panel } },
  plotArea: { fill: { color: C.panel } },
  catAxisLabelColor: C.zinc, catAxisLabelFontSize: 13, catAxisLabelFontFace: FONTS.body,
  catAxisLineShow: false, valAxisHidden: true,
  valGridLine: { style: "none" }, catGridLine: { style: "none" },
  showValue: true, dataLabelPosition: "outEnd", dataLabelColor: C.ink,
  dataLabelFontSize: 13, dataLabelFontFace: FONTS.body, dataLabelFontBold: true,
  showLegend: false, showTitle: false, barGapWidthPct: 78,
});
s2.addText(`2024 年首次超越同年电影票房（470 亿元）；2025 年约为同期电影票房 518 亿元的近两倍。`, {
  x: 6.45, y: 4.72, w: 6.05, h: 0.34, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 12, color: C.faint, lineSpacingMultiple: 1.3,
});

// 右栏：两个大数字（发丝线分隔，非卡片平铺）
hairline(s2, 6.45, 5.28, 6.05);
s2.addText(`+126%`, {
  x: 6.45, y: 5.44, w: 2.9, h: 0.56, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.display, fontSize: 38, bold: true, color: C.accent, charSpacing: -1,
  shadow: { type: "outer", blur: 24, offset: 0, angle: 45, color: C.accent, opacity: 0.22 },
});
s2.addText(`2025 年海外短剧应用内购收入同比增速，规模达 20.6 亿美元、下载 21.5 亿次`, {
  x: 6.45, y: 6.04, w: 2.9, h: 0.74, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 12.5, color: C.zinc, lineSpacingMultiple: 1.34,
});
s2.addShape("line", { x: 9.58, y: 5.46, w: 0, h: 1.26, line: { color: C.hair, width: 1, transparency: 90 } });
s2.addText(`20:1`, {
  x: 9.86, y: 5.44, w: 2.64, h: 0.56, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.display, fontSize: 38, bold: true, color: C.ink, charSpacing: -1,
});
s2.addText(`微短剧剧本供需比：2025 年参与剧本创作的人员已超 10 万人，仍供不应求`, {
  x: 9.86, y: 6.04, w: 2.64, h: 0.74, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 12.5, color: C.zinc, lineSpacingMultiple: 1.34,
});

// 整页来源注脚
hairline(s2, 0.85, 6.98, 11.65);
s2.addText(`数据来源：中国网络视听协会《中国微短剧行业发展白皮书（2024）》、DataEye《2025 年微短剧行业数据报告》及 2026 年预估、国家广播电视总局、央视网《2025 微短剧行业生态洞察报告》、Appfigures`, {
  x: 0.85, y: 7.04, w: 11.65, h: 0.3, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 12, color: C.faint,
});

// ══════════════════════════════════════════════════════════
// 第 3 页｜产品核心机制
// ══════════════════════════════════════════════════════════
const s3 = deck.addSlide();
paintBase(s3, "bg_content");

s3.addText(`不是替你写完，而是让这场戏先演一遍`, {
  x: 0.85, y: 0.58, w: 11.65, h: 0.78, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.display, fontSize: 33, bold: true, color: C.ink, charSpacing: -0.5,
});
accentRule(s3, 0.86, 1.46);

// 左栏：五步机制（编号方块 + 引导词 + 说明）
const steps = [
  { n: `01`, t: `一句话开场`, d: `输入一个想法，自动生成剧名、角色（公开目标／隐藏目标／秘密）、道具、事实，以及舞台布局、配色与区域坐标。` },
  { n: `02`, t: `多智能体独立决策`, d: `每个角色是一个独立智能体，只看到自己该看到的信息，各自提出下一步动作与对白——不是轮流念台词。` },
  { n: `03`, t: `契约与五个节拍`, d: `每场戏有一份契约：主角、对手、失败代价、必须发生的变化；拆成 5 个节拍，由作者手动推进，系统绝不自动跳拍。` },
  { n: `04`, t: `八项剧情检查`, d: `冲突、推进、信息变化、因果、压力升级、人物主动性、可拍性、结尾准备——逐项给出通过／偏弱／未发生与依据。` },
  { n: `05`, t: `3D 舞台显现与定稿`, d: `走位、说话气泡、对话连线全部由真实事件驱动；确认后一键整理成场次卡、剧本与分镜，逐镜可回溯到来源事件。` },
];
let sy = 1.86;
steps.forEach((st) => {
  s3.addShape("roundRect", {
    x: 0.85, y: sy + 0.02, w: 0.52, h: 0.4, rectRadius: 0.08,
    fill: { color: C.raised, transparency: 35 }, line: { color: C.accent, width: 1, transparency: 62 },
  });
  s3.addText(st.n, {
    x: 0.85, y: sy + 0.02, w: 0.52, h: 0.4, margin: 0, valign: "middle", align: "center",
    fontFace: FONTS.mono, fontSize: 13, bold: true, color: C.accent,
  });
  s3.addText(st.t, {
    x: 1.56, y: sy, w: 7.1, h: 0.36, margin: 0, valign: "top", align: "left",
    fontFace: FONTS.body, fontSize: 17, bold: true, color: C.ink,
  });
  s3.addText(st.d, {
    x: 1.56, y: sy + 0.38, w: 7.1, h: 0.6, margin: 0, valign: "top", align: "left",
    fontFace: FONTS.body, fontSize: 14.5, color: C.zinc, lineSpacingMultiple: 1.32,
  });
  sy += 1.02;
});

// 右栏：3D 舞台竖图 + 玻璃底框
s3.addShape("roundRect", {
  x: 9.14, y: 1.8, w: 3.42, h: 5.06, rectRadius: RADIUS,
  fill: { color: C.raised, transparency: 40 }, line: { color: C.hair, width: 1, transparency: 92 },
  shadow: { type: "outer", blur: 22, offset: 5, angle: 90, color: "000000", opacity: 0.4 },
});
const stageImg = imgOpts("p3_stage", 9.22, 1.88, 3.26, 4.9);
if (stageImg) s3.addImage(stageImg);
// 图底部渐变压条，托住说明文字
s3.addImage({
  data: gradientMaskB64({ w: 256, h: 128, color: C.canvas, dir: "bottom", stops: [[0, 0], [0.45, 0.62], [1, 0.96]] }),
  x: 9.22, y: 5.86, w: 3.26, h: 0.92,
});
s3.addText(`实时 3D 舞台`, {
  x: 9.4, y: 6.06, w: 2.9, h: 0.3, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.body, fontSize: 15, bold: true, color: C.ink,
});
s3.addText(`程序化布景 · 角色行走 · 对话气泡`, {
  x: 9.4, y: 6.36, w: 2.9, h: 0.28, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.body, fontSize: 12, color: C.zinc,
});

// ══════════════════════════════════════════════════════════
// 第 4 页｜技术护城河 + 工程证据
// ══════════════════════════════════════════════════════════
const s4 = deck.addSlide();
paintBase(s4, "bg_content");

s4.addText(`护城河：把不可见的创作过程，变成可审计的工程系统`, {
  x: 0.85, y: 0.58, w: 11.65, h: 0.78, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.display, fontSize: 30, bold: true, color: C.ink, charSpacing: -0.5,
});
accentRule(s4, 0.86, 1.46);

const moats = [
  { x: 0.85, y: 1.92, w: 5.45, t: `剧情结构层`, d: `纯符号实体状态机做事实裁决：道具的持有者与所在地点互斥、状态可销毁，角色无法披露自己不知道的事实。规则可复现，不依赖模型自觉。` },
  { x: 6.98, y: 1.92, w: 5.52, t: `作者控制链路`, d: `预览在副本上裁决，锁定保护已确认字段，分支从任意版本 fork 完整快照；提交需经预览、幂等键与乐观锁三重校验——改一处不会冲掉别的决定。` },
  { x: 0.85, y: 4.24, w: 5.45, t: `来源诚实`, d: `每一次生成都标注来源：真实模型／离线规则／内置模板／确定性渲染。声明用模型却缺密钥时拒绝启动，绝不把规则演示伪装成模型结果。` },
  { x: 6.98, y: 4.24, w: 5.52, t: `一句话到一座舞台`, d: `程序化零件库覆盖室内、街景、载具、矿洞、室外五种形态；场景配置驱动布景、配色、区域坐标与相机预设，新增题材无需改一行渲染代码。` },
];
moats.forEach((m) => {
  s4.addShape("rect", { x: m.x, y: m.y + 0.07, w: 0.1, h: 0.1, fill: { color: C.accent }, line: { type: "none" } });
  s4.addText(m.t, {
    x: m.x + 0.28, y: m.y - 0.06, w: m.w - 0.28, h: 0.36, margin: 0, valign: "top", align: "left",
    fontFace: FONTS.body, fontSize: 18, bold: true, color: C.ink,
  });
  s4.addText(m.d, {
    x: m.x + 0.28, y: m.y + 0.36, w: m.w - 0.28, h: 1.5, margin: 0, valign: "top", align: "left",
    fontFace: FONTS.body, fontSize: 14.5, color: C.zinc, lineSpacingMultiple: 1.42,
  });
});
// 分区发丝线：中竖 + 横
s4.addShape("line", { x: 6.68, y: 1.92, w: 0, h: 4.14, line: { color: C.hair, width: 1, transparency: 91 } });
s4.addShape("line", { x: 0.85, y: 4.02, w: 11.65, h: 0, line: { color: C.hair, width: 1, transparency: 91 } });

// 底部：工程证据带
s4.addShape("roundRect", {
  x: 0.85, y: 6.34, w: 11.65, h: 0.82, rectRadius: 0.11,
  fill: { color: C.raised, transparency: 42 }, line: { color: C.hair, width: 1, transparency: 92 },
});
const proofs = [
  { v: `94 项`, l: `后端自动化测试全部通过` },
  { v: `4.8 秒`, l: `真实模型生成 3 个角色候选` },
  { v: `20+`, l: `程序化 3D 零件，零外部模型依赖` },
  { v: `3 份`, l: `可拍输出：场次卡／剧本／分镜` },
];
proofs.forEach((p, i) => {
  const px = 1.15 + i * 2.79;
  s4.addText(p.v, {
    x: px, y: 6.42, w: 2.6, h: 0.38, margin: 0, valign: "middle", align: "left",
    fontFace: FONTS.display, fontSize: 21, bold: true, color: i === 1 ? C.accent : C.ink, charSpacing: -0.5,
  });
  s4.addText(p.l, {
    x: px, y: 6.8, w: 2.6, h: 0.3, margin: 0, valign: "top", align: "left",
    fontFace: FONTS.body, fontSize: 12, color: C.zinc,
  });
  if (i > 0) s4.addShape("line", { x: px - 0.16, y: 6.5, w: 0, h: 0.5, line: { color: C.hair, width: 1, transparency: 89 } });
});

// ══════════════════════════════════════════════════════════
// 第 5 页｜商业化路径 · 当前进展 · 路线图 · 收尾
// ══════════════════════════════════════════════════════════
const s5 = deck.addSlide();
paintBase(s5, "bg_content");

s5.addText(`从创作工具，到短剧的实时生产管线`, {
  x: 0.85, y: 0.58, w: 11.65, h: 0.78, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.display, fontSize: 32, bold: true, color: C.ink, charSpacing: -0.5,
});
accentRule(s5, 0.86, 1.46);

// 左栏：商业化路径（规划中）
s5.addText(`商业化路径 · 规划中`, {
  x: 0.85, y: 1.82, w: 5.5, h: 0.32, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 15, bold: true, color: C.accent, charSpacing: 1.5,
});
s5.addText([
  { text: `创作者订阅`, options: { bold: true, color: C.ink, fontSize: 16, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 2 } },
  { text: `按席位与生成额度收费，面向短剧编剧、MCN 内容团队与网文改编方。`, options: { color: C.zinc, fontSize: 14, breakLine: true, paraSpaceAfter: 11 } },
  { text: `制作方管线`, options: { bold: true, color: C.ink, fontSize: 16, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 2 } },
  { text: `把场次卡、剧本、分镜接进既有拍摄流程，按项目授权与集数计费。`, options: { color: C.zinc, fontSize: 14, breakLine: true, paraSpaceAfter: 11 } },
  { text: `平台侧能力`, options: { bold: true, color: C.ink, fontSize: 16, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 2 } },
  { text: `为短剧平台与出海应用提供剧本预审、结构化生产与素材溯源工具。`, options: { color: C.zinc, fontSize: 14, paraSpaceAfter: 0 } },
], {
  x: 0.85, y: 2.22, w: 5.45, h: 2.2, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, lineSpacingMultiple: 1.3,
});

// 右栏：当前已完成
s5.addText(`当前已完成 · 可现场验证`, {
  x: 6.98, y: 1.82, w: 5.52, h: 0.32, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 15, bold: true, color: C.accent, charSpacing: 1.5,
});
s5.addText([
  { text: `端到端真实闭环`, options: { bold: true, color: C.ink, fontSize: 16, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 2 } },
  { text: `一句话开场 → 多轮试演 → 干预锁定 → 提交 → 节拍推进 → 回放 → 三份可拍输出。`, options: { color: C.zinc, fontSize: 14, breakLine: true, paraSpaceAfter: 11 } },
  { text: `真实模型联调通过`, options: { bold: true, color: C.ink, fontSize: 16, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 2 } },
  { text: `预览不改正式状态，提交后版本递增，同一幂等键重复提交结果一致。`, options: { color: C.zinc, fontSize: 14, breakLine: true, paraSpaceAfter: 11 } },
  { text: `素材层实跑`, options: { bold: true, color: C.ink, fontSize: 16, bullet: { code: "25CF", color: C.accent }, breakLine: true, paraSpaceAfter: 2 } },
  { text: `场景背板与角色立绘由文生图产出，逐张记录提示词、模型、尺寸与哈希。`, options: { color: C.zinc, fontSize: 14, paraSpaceAfter: 0 } },
], {
  x: 6.98, y: 2.22, w: 5.52, h: 2.2, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, lineSpacingMultiple: 1.3,
});
s5.addShape("line", { x: 6.68, y: 1.86, w: 0, h: 2.62, line: { color: C.hair, width: 1, transparency: 91 } });

// 中部：路线图时间轴
hairline(s5, 0.85, 4.62, 11.65);
s5.addText(`下一步`, {
  x: 0.85, y: 4.76, w: 4.0, h: 0.32, margin: 0, valign: "top", align: "left",
  fontFace: FONTS.body, fontSize: 15, bold: true, color: C.accent, charSpacing: 1.5,
});
s5.addShape("line", { x: 1.5, y: 5.48, w: 10.35, h: 0, line: { color: C.rule, width: 2 } });
const roadmap = [
  `真实模型长时稳定性与成本评估`,
  `更多题材的场景配置与可行走路线`,
  `image-to-3D 资产管线`,
  `多人协作与团队工作流`,
];
roadmap.forEach((r, i) => {
  const nx = 1.5 + i * 3.45;
  s5.addShape("ellipse", {
    x: nx - 0.12, y: 5.36, w: 0.24, h: 0.24,
    fill: { color: C.accent }, line: { color: C.canvas, width: 2 },
    shadow: { type: "outer", blur: 16, offset: 0, angle: 45, color: C.accent, opacity: 0.42 },
  });
  s5.addText(r, {
    x: nx - 1.42, y: 5.72, w: 2.9, h: 0.62, margin: 0, valign: "top", align: "center",
    fontFace: FONTS.body, fontSize: 13.5, color: C.body, lineSpacingMultiple: 1.3,
  });
});

// 收尾主张
s5.addShape("rect", { x: 0.85, y: 6.5, w: 0.045, h: 0.62, fill: { color: C.accent }, line: { type: "none" } });
s5.addText(`把最难观察、最难修改的角色互动，变成看得见、能干预、可追溯的工作台。`, {
  x: 1.1, y: 6.46, w: 11.4, h: 0.7, margin: 0, valign: "middle", align: "left",
  fontFace: FONTS.body, fontSize: 19, bold: true, color: C.ink, lineSpacingMultiple: 1.25,
});

// 末页署名（硬性）
s5.addText(`千问AI生成`, {
  x: SLIDE_W - 3.1, y: 0.14, w: 2.9, h: 0.34, margin: 0, align: "right", valign: "middle",
  fontFace: FONTS.body, fontSize: 12, color: C.zinc,
});

deck.writeFile({ fileName: path.join(__dirname, "..", `AI导演台投资人路演PPT.pptx`) });
