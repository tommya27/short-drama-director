// build_header.js — build_pptx.js 固定样板（所有 deck 相同，由 init_deck_dir.py 预写到 work/）
// 模型严禁重复输出本文件代码；build_pptx.js 以 require("./build_header.js") 起头，开头段+全部页区块+收尾段一次 Write 写完。
// 导出：PptxGenJS / fs / path / zlib / SLIDE_W / SLIDE_H / imgOpts / gradientMaskB64 / pngChunk / crc32
const PptxGenJS = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const zlib = require("zlib"); // 渐变蒙版 PNG 生成用（Node 内置，零依赖）

const SLIDE_W = 13.33, SLIDE_H = 7.5; // LAYOUT_WIDE

// ═══ 配图（运行时从 img_map.json 读取：{key: {src, w, h[, candidates]}}，懒加载） ═══
// candidates = 搜图 top3 候选（按相关度排序，均带实际 w/h）
let _IMG_MAP = null;
function imgMap() {
  if (_IMG_MAP) return _IMG_MAP;
  const p1 = path.join(__dirname, "img_map.json");           // build_pptx.js 与 img_map 同目录（work/）
  const p2 = path.join(__dirname, "work", "img_map.json");   // 兼容放在 deck 根的旧布局
  const p = fs.existsSync(p1) ? p1 : p2;
  _IMG_MAP = fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf-8")) : {};
  return _IMG_MAP;
}

// imgOpts：图框（x/y/w/h）由版面布局先行定死 → 校验文件存在 → 按图框宽高比从候选选比例最接近的一张
// → 自行计算 cover 居中裁剪，经 sizing:crop 表达（绝不拉伸、图框尺寸不变）
// ❗ pptxgenjs 4.x 的 sizing:{type:'cover'} 是死功能——库从不读取图片原始尺寸（getSizeFromImage 被注释，
//    FIXME: currently unused），srcRect 恒为全零 = 永远拉伸填充。因此必须用 img_map 的实际像素尺寸自算裁剪。
// ❗❗ sizing:crop 的真实语义（极易搞错，已实测验证）：
//    · 最终显示尺寸 = sizing.w × sizing.h（库内 imgWidth=boxW 会覆写形状尺寸）——所以 sizing.w/h 必须填图框 w/h；
//    · srcRect 百分比以**外层 options.w/h** 为分母——所以外层 w/h 要填“裁剪前坐标空间”尺寸（图框按裁剪方向放大）；
//    · 位置不偏移：裁剪后的内容填满整个图框、仍位于 x/y。
const imgOpts = (key, x, y, w, h) => {
  const e = imgMap()[key];
  if (!e || e.failed) return null; // null / 失败槽位（failed=true）→ 该页不配图
  const list = e.candidates || [e];
  const diff = (c) => (c.w && c.h) ? Math.abs(c.w / c.h - w / h) : 9e9;
  const best = list.reduce((a, b) => (diff(b) < diff(a) ? b : a));
  const abs = path.resolve(__dirname, best.src);
  if (!fs.existsSync(abs)) return null; // 文件不存在 → 不配图（严禁把死路径传给 addImage）
  // 自算 cover 裁剪：外层 w/h = 裁剪前坐标空间（srcRect 分母），sizing.w/h = 图框（最终显示尺寸）
  if (best.w && best.h) {
    const imgR = best.w / best.h, boxR = w / h;
    let ow = w, oh = h, sx = 0, sy = 0;
    if (imgR > boxR + 0.001) {        // 图相对更宽 → 裁左右
      ow = w * (imgR / boxR); sx = (ow - w) / 2;
    } else if (imgR < boxR - 0.001) { // 图相对更高 → 裁上下
      oh = h * (boxR / imgR); sy = (oh - h) / 2;
    }
    return { path: abs, x, y, w: ow, h: oh, sizing: { type: "crop", x: sx, y: sy, w, h } };
  }
  return { path: abs, x, y, w, h };   // 无尺寸信息（极罕见）→ 无 sizing 兜底
};
// 用法：const o = imgOpts("p3_1", 7.9, 1.6, 4.9, 5.2); if (o) s3.addImage(o);
// 照片类 addImage 一律经 imgOpts（cover 裁剪内建）；严禁手写不带 sizing 的照片 addImage（= 拉伸变形）；
// 严禁绕过选图直接取 .src / 固定取某一张；严禁用“固定一边 × 原始宽高比”反推图框另一边

// ═══ 渐变蒙版：构建时现生成线性渐变透明 PNG（纯 Node zlib 实现，零依赖），作为单个 addImage 覆盖 ═══
// ——PowerPoint 渲染 PNG alpha 连续平滑、无色带拼接感（色带拼接是禁止的替代方案，见 api-pptxgenjs.md → gradient）。
// ——模板渐变（含斜切渐变）的正规实现：纯色底 shape + 本 helper 渐变蒙版叠层（dir 选 bottom/right/diag），
//    构建时现生成、零外部图；禁降级为外部预渲染背景图、禁宣称“库不支持渐变”（见 references/from-template/build-template.md §2）。
// 用法：s.addImage({ data: gradientMaskB64({ w:512, h:128, color:"0A0A0F", dir:"bottom", a0:0.88, a1:0.3 }), x, y, w:框宽, h:框高 });
// ⚠️ 蒙版不贴画布边时，边缘必须从全透明起（用 stops，如 [[0,0],[0.28,0.88],[1,0.3]])——
// 否则蒙版自身顶边会形成可见硬边界（已知 badcase）；贴边蒙版（如从页底/页侧起）可直接用 a0→a1。
// ⚠️ 首页（封面）蒙版端点硬性：a0=1（100% 背景色全不透）→ a1=0（完全透明），如 stops [[0,1],[0.45,0.75],[1,0]]；严禁半程薄纱。
// 属合成图（非照片）——不需 imgOpts / sizing，但图框宽高比应与 PNG 宽高比大致一致。
const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
function pngChunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}
// dir='bottom'：alpha 沿高度变化（顶→底）；dir='right'：沿宽度（左→右）；dir='diag'：斜切（左上→右下对角）
// stops：可选分段线性锚点 [[t0,a0],[t1,a1],...]（t∈0~1 升序、a 为不透明度）——
// 用于"从透明平滑爬升/降落"的蒙版，避免蒙版边缘自身出现硬边界；缺省时按 a0→a1 线性
function gradientMaskB64({ w = 256, h = 256, color = "0A0A0F", dir = "bottom", a0 = 0.88, a1 = 0.3, stops = null }) {
  const r = parseInt(color.slice(0, 2), 16), g = parseInt(color.slice(2, 4), 16), b = parseInt(color.slice(4, 6), 16);
  const alphaAt = (tt) => {
    if (!stops) return a0 + (a1 - a0) * tt;
    if (tt <= stops[0][0]) return stops[0][1];
    for (let i = 1; i < stops.length; i++) {
      if (tt <= stops[i][0]) {
        const [t0, v0] = stops[i - 1], [t1, v1] = stops[i];
        return v0 + (v1 - v0) * ((tt - t0) / (t1 - t0));
      }
    }
    return stops[stops.length - 1][1];
  };
  const raw = Buffer.alloc(h * (1 + w * 4));
  for (let y = 0; y < h; y++) {
    const rowOff = y * (1 + w * 4);
    raw[rowOff] = 0; // filter: none
    for (let x = 0; x < w; x++) {
      const tt = dir === "right" ? x / (w - 1) : dir === "diag" ? (x / (w - 1) + y / (h - 1)) / 2 : y / (h - 1);
      const o = rowOff + 1 + x * 4;
      raw[o] = r; raw[o + 1] = g; raw[o + 2] = b;
      raw[o + 3] = Math.round(alphaAt(tt) * 255);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 6; // 8-bit RGBA
  const png = Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
  return "image/png;base64," + png.toString("base64");
}

// ═══ 文本形态守卫 + 自动修复：pptxgenjs 不校验 text 类型，对象/数组会被静默强转 "[object Object]" 垃圾串 ═══
// （真实 badcase：内容页 bullet 正文全变 [object Object],[object Object]）。
// 策略：构建时确定性自动展平、无需模型介入（FIX-1~5 同哲学）：text: 下嵌套的 runs 数组/对象
// 展开回 addText 首参——段级选项（bullet 等）只挂首 run（每 run 都挂会重复开 bullet 段），
// run 级选项并入每个 run（嵌套 run 自身 options 优先），同段 runs 以 breakLine:false 连接。
// 内容不可恢复（嵌套对象无字符串 text 字段）才抛错回模型；产物层 check.py 仍扫 '[object ' 垃圾串兜底
// （仅绕过 build_header 直接 require pptxgenjs 时才会命中）。
(() => {
  const proto = Object.getPrototypeOf(new PptxGenJS().addSlide());
  const origAddText = proto.addText;
  const isObj = (v) => v !== null && typeof v === "object";
  const isTextual = (v) => typeof v === "string" || typeof v === "number";
  // 段级选项键（只挂首 run）；其余视为 run 级并入每个 run
  const PARA_KEYS = new Set(["bullet", "indentLevel", "align", "paraSpaceBefore",
    "paraSpaceAfter", "lineSpacing", "lineSpacingMultiple"]);
  const needsFlat = (it) => isObj(isObj(it) ? it.text : it);
  // 展平单个 item；返回 null = 内容不可恢复。changed 标记是否发生了改写
  const flatItem = (it) => {
    const t = isObj(it) ? it.text : it;
    if (!isObj(t)) return { out: [it], changed: false }; // 正常形态：字符串/数字/{text:字符串}
    if (!Array.isArray(t)) { // 嵌套单个 run 对象：解包合并 options
      if (!isTextual(t.text)) return null;
      return { out: [{ text: t.text, options: { ...((isObj(it) && it.options) || {}), ...(t.options || {}) } }], changed: true };
    }
    const runs = t.map((r) => isObj(r)
      ? (isTextual(r.text) ? { text: r.text, ro: r.options || {} } : null)
      : (isTextual(r) ? { text: r, ro: {} } : null));
    if (runs.some((r) => !r)) return null;
    const O = (isObj(it) && it.options) || {};
    const para = {}, runl = {};
    for (const [k, v] of Object.entries(O)) (PARA_KEYS.has(k) ? para : runl)[k] = v;
    return {
      out: runs.map((r, i) => ({
        text: r.text,
        options: {
          ...runl, ...r.ro, ...(i === 0 ? para : {}),
          breakLine: i < runs.length - 1 ? false : (O.breakLine !== undefined ? O.breakLine : true),
        },
      })),
      changed: true,
    };
  };
  proto.addText = function (text, opts) {
    const items = Array.isArray(text) ? text : [text];
    if (!items.some(needsFlat)) return origAddText.call(this, text, opts);
    const parts = items.map(flatItem);
    if (parts.some((p) => !p)) {
      throw new Error("addText 文本形态错误：text 值为对象/数组且无字符串 text 字段，内容不可恢复、无法自动修复"
        + "——runs 数组应展开为 addText 首参（见 api-pptxgenjs.md bullets 示例），或取字符串字段使 text 为字符串");
    }
    const nFixed = parts.filter((p) => p.changed).length;
    console.warn(`[build_header] TEXT_AUTOFLAT ×${nFixed}：text: 下嵌套 runs 数组/对象已自动展平为 addText 首参（坑点 12e；建议源码直接写正确形态）`);
    return origAddText.call(this, parts.flatMap((p) => p.out), opts);
  };
})();

module.exports = { PptxGenJS, fs, path, zlib, SLIDE_W, SLIDE_H, imgOpts, imgMap, gradientMaskB64, pngChunk, crc32 };
