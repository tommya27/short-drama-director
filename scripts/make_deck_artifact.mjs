import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const root = 'D:/Deepseek harness workplace/short-drama-director';
const build = path.join(root, '.codex-ppt-build');
const candidate = path.join(build, 'pitch-deck-candidate.pptx');
const imagePath = path.join(root, 'data/assets/71c10159a38ff6b4.png');
const FONT = 'Microsoft YaHei';
const C = {
  paper: '#F5F3EC',
  ink: '#23302B',
  muted: '#68736D',
  accent: '#2F705D',
  warm: '#B2784F',
  rule: '#C8D0C8',
};

await fs.mkdir(build, { recursive: true });
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function box(slide, name, left, top, width, height, text, style = {}) {
  const shape = slide.shapes.add({
    geometry: 'textbox', name, position: { left, top, width, height },
    fill: 'none', line: { fill: 'none', width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: style.typeface ?? FONT,
    fontSize: style.fontSize ?? 18,
    bold: style.bold ?? false,
    color: style.color ?? C.ink,
    align: style.align ?? 'left',
    verticalAlign: style.verticalAlign ?? 'top',
    ...(style.italic ? { italic: true } : {}),
  };
  return shape;
}

function line(slide, name, left, top, width, color = C.rule, height = 2) {
  return slide.shapes.add({ geometry: 'rect', name, position: { left, top, width, height }, fill: color, line: { fill: color, width: 0 } });
}

function header(slide, number, cn, en) {
  box(slide, 'section-number', 60, 36, 70, 34, number, { fontSize: 17, bold: true, color: C.accent });
  box(slide, 'section-title-cn', 130, 31, 610, 48, cn, { fontSize: 28, bold: true, color: C.ink });
  box(slide, 'section-title-en', 130, 82, 1000, 28, en, { fontSize: 14, color: C.muted });
  line(slide, 'header-rule', 60, 124, 1160, C.rule, 2);
}

function sectionLabel(slide, name, x, y, cn, en) {
  box(slide, `${name}-cn`, x, y, 520, 30, cn, { fontSize: 18, bold: true, color: C.accent });
  box(slide, `${name}-en`, x, y + 32, 520, 24, en, { fontSize: 12, color: C.muted });
}

function notes(slide, text) {
  slide.speakerNotes.textFrame.setText(text);
}

function addBulletLines(slide, name, x, y, width, lines, size = 16, gap = 13) {
  let current = y;
  for (let i = 0; i < lines.length; i += 1) {
    const [text, kind] = Array.isArray(lines[i]) ? lines[i] : [lines[i], 'body'];
    const h = kind === 'heading' ? 32 : 26 * String(text).split('\n').length;
    box(slide, `${name}-${i}`, x, current, width, h, text, {
      fontSize: kind === 'heading' ? size + 1 : size,
      bold: kind === 'heading',
      color: kind === 'heading' ? C.accent : C.ink,
    });
    current += h + (kind === 'heading' ? 2 : gap);
  }
}

// 1. Cover
{
  const slide = presentation.slides.add();
  slide.background.fill = C.paper;
  box(slide, 'cover-kicker', 68, 64, 640, 26, 'BAYTECH 2026  /  AI 应用与工程赛道', { fontSize: 14, bold: true, color: C.accent });
  box(slide, 'cover-title', 68, 132, 670, 70, '可视化 AI 导演台', { fontSize: 45, bold: true });
  box(slide, 'cover-subtitle', 70, 220, 650, 38, '让角色先演一遍，你来定稿', { fontSize: 23, bold: true, color: C.accent });
  box(slide, 'cover-en', 70, 275, 650, 46, "A Visual Director's Desk for Short Drama\nLet the cast play the scene out. You decide.", { fontSize: 16, color: C.muted });
  line(slide, 'cover-rule', 70, 355, 610, C.warm, 3);
  box(slide, 'cover-one-line', 70, 390, 640, 92, '多个角色在同一个沙盘里行动、交流、互相影响。\n导演观察、干预、确认，再整理成剧本与分镜草稿。', { fontSize: 18 });
  box(slide, 'cover-one-line-en', 70, 490, 650, 46, 'Multiple characters act and influence one another in a shared sandbox.\nThe director observes, intervenes and approves the scene.', { fontSize: 13, color: C.muted });
  box(slide, 'cover-tags', 70, 570, 660, 42, '多角色沙盘 / Multi-agent sandbox   事实透镜 / Fact lens   人工确认 / Human approval   2.5D / 3D 显现 / Visualization', { fontSize: 11, color: C.muted });
  const image = new Uint8Array(await fs.readFile(imagePath));
  slide.images.add({ blob: image, contentType: 'image/png', alt: '工具生成的董事会会议室背板', fit: 'cover', geometry: 'roundRect', borderRadius: 'rounded-3xl', position: { left: 805, top: 86, width: 385, height: 385 } });
  box(slide, 'cover-image-caption', 805, 494, 385, 34, '封面图：本工具生成的场景背板', { fontSize: 12, color: C.muted, align: 'center' });
  box(slide, 'cover-footer', 70, 658, 1120, 26, '24 小时原型   ·   short-drama-director   ·   3 分钟演示', { fontSize: 12, color: C.muted });
  notes(slide, '0:00–0:20\n我们是 AI 应用与工程赛道。一句话：让角色先演一遍，你来定稿。这是一个可干预的导演台：多个角色在同一个沙盘里行动，作者观察、插手、最后确认。右侧是工具生成的董事会会议室背板。');
}

// 2. Problem
{
  const slide = presentation.slides.add();
  slide.background.fill = C.paper;
  header(slide, '01', '问题与场景价值', 'The problem and the value of a scene-first workflow');
  sectionLabel(slide, 'problem', 70, 158, '写戏时，用户缺的是过程', 'Writers need to see the process, not only the text');
  addBulletLines(slide, 'problem-cn', 70, 230, 535, [
    'AI 给出一段对白，却没有解释角色为什么这样说。',
    '新手很难同时守住冲突、信息差、道具和人物目标。',
    '改一处台词，下一次生成可能覆盖已有决定。',
  ], 17, 22);
  line(slide, 'problem-divider', 640, 158, 2, C.rule, 458);
  sectionLabel(slide, 'value', 700, 158, '我们先帮助用户写成一场戏', 'We help a beginner finish one playable scene');
  addBulletLines(slide, 'value-en', 700, 230, 500, [
    'Start with one premise. The system asks for characters, place, goals and secrets.',
    'Characters act in a shared sandbox. The director can inspect causes, effects and state changes.',
    'Candidate story changes are previewed first. The author approves the formal version.',
  ], 15, 25);
  box(slide, 'target-cn', 70, 565, 535, 58, '目标用户：短剧编剧、导演/制片、剧情号创作者，以及没有编剧训练但有故事想法的人', { fontSize: 14, bold: true, color: C.accent });
  box(slide, 'target-en', 700, 565, 500, 58, 'Users: short-drama writers, directors and producers, scripted-video creators, and first-time storytellers.', { fontSize: 13, color: C.muted });
  notes(slide, '0:20–0:50\n现有 AI 剧本工具给你一段文字，但你看不见角色为什么这么说，过程是黑盒。对短剧新手来说，冲突、信息差、道具和人物目标很容易互相打架；改好的台词也可能被下一次生成覆盖。我们的入口很具体：从一句话想法开始，帮助没有编剧训练的用户先完成一场可检查、可修改的戏。');
}

// 3. Increment
{
  const slide = presentation.slides.add();
  slide.background.fill = C.paper;
  header(slide, '02', '24 小时增量：剧情结构先跑通', 'What we built in the 24-hour sprint');
  box(slide, 'increment-lead-cn', 70, 153, 520, 44, '核心增量：把 Agent 互动变成一场有结构的戏', { fontSize: 20, bold: true, color: C.accent });
  box(slide, 'increment-lead-en', 700, 153, 500, 44, 'Core increment: turn agent interaction into a structured scene', { fontSize: 15, bold: true, color: C.accent });
  const cn = [
    ['1  剧情结构层', '本场契约、5 个剧情节拍、8 项规则检查。'],
    ['2  过程可见', '点事件看提议、事实检查、最终动作和状态变化。'],
    ['3  作者掌控', '预览、锁定、导演指令、分支试演，作者推进节拍。'],
    ['4  来源诚实', '角色事件标注 live/offline；素材、输出和润色保留来源。'],
    ['5  一句话开场', '角色、道具、事实和舞台布局一起生成，场景随题材适配。'],
  ];
  const en = [
    ['1  Dramatic structure', 'A scene contract, five beats and eight rule-based checks.'],
    ['2  Visible process', 'Inspect proposal, fact checks, final action and state change.'],
    ['3  Author control', 'Preview, lock, direct, branch and advance beats by choice.'],
    ['4  Honest provenance', 'Label live/offline events, assets, outputs and polish.'],
    ['5  One-line opening', 'Cast, props, facts and stage layout adapt to the premise.'],
  ];
  let y = 220;
  for (let i = 0; i < cn.length; i += 1) {
    box(slide, `inc-cn-head-${i}`, 70, y, 500, 28, cn[i][0], { fontSize: 16, bold: true, color: C.accent });
    box(slide, `inc-cn-body-${i}`, 70, y + 30, 500, 35, cn[i][1], { fontSize: 13 });
    box(slide, `inc-en-head-${i}`, 700, y, 500, 28, en[i][0], { fontSize: 15, bold: true, color: C.accent });
    box(slide, `inc-en-body-${i}`, 700, y + 30, 500, 35, en[i][1], { fontSize: 12.5, color: C.ink });
    y += 78;
  }
  notes(slide, '0:50–1:50\n24 小时里最核心的是剧情结构层。以前多角色沙盘容易变成角色轮流说话；现在每场戏有一份契约，写清主角、对手、失败代价和必须发生的变化，再拆成五个节拍。每轮生成后，规则检查提示冲突、推进、信息变化、因果、压力、人物主动性、可拍性和结尾准备。除此之外，过程可见，作者能预览、锁定、干预和分支试演；模型、规则、素材和输出都标注来源；一句话还可以生成开场设定与舞台布局。');
}

// 4. Stack and boundaries
{
  const slide = presentation.slides.add();
  slide.background.fill = C.paper;
  header(slide, '03', '技术与边界', 'Stack and honest boundaries');
  sectionLabel(slide, 'stack', 70, 160, '独立平台', 'Standalone platform');
  addBulletLines(slide, 'stack-cn', 70, 230, 520, [
    'React + TypeScript + three.js：导演台与 2.5D / 3D 舞台\nReact + TypeScript + three.js: director desk and 2.5D / 3D stage',
    'FastAPI + SQLite：共享世界状态、版本、分支与审计\nFastAPI + SQLite: shared state, revisions, branches and audit trail',
    'OpenAI 兼容模型：角色候选、开场规划和作者主动润色\nOpenAI-compatible models: candidates, opening plans and author-triggered polish',
    'Seedream：场景背板与角色立绘，作为视觉层保存来源信息\nSeedream: backdrops and portraits with visual-layer provenance',
  ], 15, 17);
  line(slide, 'tech-divider', 640, 160, 2, C.rule, 430);
  sectionLabel(slide, 'boundaries', 700, 160, '诚实边界', 'What the prototype does not claim');
  addBulletLines(slide, 'boundary-en', 700, 230, 500, [
    'The live/offline mode is visible. Explicit live without a key refuses to start.',
    'The reused narrative core is the user’s own. Source hashes and edits are recorded.',
    '3D interaction references FeiControl (MIT). No code or assets were copied.',
    'This is not one-click full-length generation. The 3D is not cinematic, and checks are advisory.',
  ], 13.5, 20);
  box(slide, 'boundary-en-note', 700, 586, 500, 46, 'The platform records provenance for the core, model calls, generated assets and outputs.', { fontSize: 12, color: C.muted });
  notes(slide, '1:50–2:20\n技术上，这是独立的 React、three.js、FastAPI 和 SQLite 平台。live 与 offline 模式会在界面上明确显示，显式 live 但没有密钥会拒绝启动，不会把规则演示伪装成模型结果。叙事内核来自用户自己的旧工作区，hash 和改写范围都有记录。3D 只参考 FeiControl 的状态驱动角色、舞台和镜头思路，没有复制它的代码或资产。我们也不把它说成一键生成整部作品，事实检查是作者辅助提示。');
}

// 5. Demo
{
  const slide = presentation.slides.add();
  slide.background.fill = C.paper;
  header(slide, '04', '现场演示与下一步', 'Live demo and next steps');
  sectionLabel(slide, 'demo', 70, 158, '现场演示路径', 'Live demo path');
  const demo = [
    ['01', '输入一句话想法', 'Premise'],
    ['02', '确认契约、角色与舞台', 'Scene setup'],
    ['03', '推进一轮，检查候选事件', 'One agent round'],
    ['04', '修改对白、锁定、预览', 'Edit and preview'],
    ['05', '提交、推进节拍、回放', 'Commit and replay'],
    ['06', '整理场次卡、剧本、分镜', 'Export outputs'],
  ];
  let y = 224;
  for (const [num, cn, en] of demo) {
    box(slide, `demo-num-${num}`, 70, y, 50, 30, num, { fontSize: 15, bold: true, color: C.warm });
    box(slide, `demo-cn-${num}`, 130, y, 520, 42, `${cn}\n${en}`, { fontSize: 14, bold: true, color: C.ink });
    y += 54;
  }
  line(slide, 'demo-divider', 690, 158, 2, C.rule, 430);
  sectionLabel(slide, 'next', 750, 158, '下一步', 'Next');
  addBulletLines(slide, 'next-lines-en', 750, 230, 450, [
    'Evaluate long-run stability and cost for live models.',
    'Add scene manifests and walkable routes for more genres.',
    'Explore image-to-3D assets and multi-user collaboration.',
  ], 14, 26);
  line(slide, 'closing-rule', 750, 478, 390, C.warm, 3);
  box(slide, 'closing-cn', 750, 515, 450, 70, '把最难观察和修改的角色互动，\n变成看得见、能干预、可追溯的工作台。', { fontSize: 18, bold: true, color: C.accent });
  box(slide, 'closing-en', 750, 600, 450, 42, 'Make character interaction visible, steerable and traceable.', { fontSize: 13, color: C.muted });
  notes(slide, '2:20–3:00\n现场我会从一句话想法开始，确认契约、角色和舞台，推进一轮，看候选事件与剧情检查，改一句对白并锁定，再预览、提交、推进下一段，最后回放并整理成场次卡、剧本和分镜。下一步是评估真实模型的稳定性与成本，增加更多题材的场景路线，继续做 image-to-3D 资产和多人协作。我们做的不是替作者写完，而是把最难观察和修改的角色互动变成看得见、能干预、可追溯的工作台。');
}

await (await PresentationFile.exportPptx(presentation)).save(candidate);
for (let i = 0; i < presentation.slides.items.length; i += 1) {
  const image = await presentation.slides.items[i].export({ format: 'png', scale: 1 });
  await fs.writeFile(path.join(build, `slide-${i + 1}.png`), new Uint8Array(await image.arrayBuffer()));
}
console.log(candidate);
