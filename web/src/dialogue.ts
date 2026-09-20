/**
 * 对白分段与显示时长。
 *
 * 依据（详见 docs/REFERENCES.md 的 REF08–REF12）：
 * - 定时文本普遍按「阅读速度」控制时长，单条有最短/最长时长限制（Netflix Timed Text Style Guide；
 *   Pošta 2012 的标准经二手引用为单条 1–1.5 秒起、有上限）。
 * - 中文行长度通常建议每行不超过约 14–16 字（国家标准《无障碍音视频出版物通用技术规范》起草稿等）。
 * - 视觉小说的既有做法是「自动前进 + 每字速度」可调（Ren'Py preferences / 社区讨论）。
 *
 * 这里的数值是**可配置的工程默认值**，不是对上述标准的合规声明：
 * 我们按「每段 ≤ 14 字、约 6 字/秒」折算时长，并夹在 1.2–4 秒之间。
 */
export const DIALOGUE_DEFAULTS = {
  maxChars: 14,        // 每段最多字数（对齐中文单行字幕的常见上限）
  minChars: 4,         // 过短的标点碎片并入相邻段
  charsPerSecond: 6,   // 中文阅读速度折算：约 6 字/秒
  minDurationMs: 1200, // 单段最短显示时长
  maxDurationMs: 4000, // 单段最长显示时长
};

export type DialogueChunk = { text: string; durationMs: number };

/** 按中英文标点切句，保留标点在句尾；并把过短的碎片并入下一段。 */
export function splitSentences(text: string): string[] {
  const clean = String(text ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return [];
  const parts = clean.match(/[^。！？!?；;，,、…]+[。！？!?；;，,、…]*/g) ?? [clean];
  const merged: string[] = [];
  for (const raw of parts) {
    const piece = raw.trim();
    if (!piece) continue;
    const last = merged[merged.length - 1];
    if (last && last.length < DIALOGUE_DEFAULTS.minChars) merged[merged.length - 1] = last + piece;
    else merged.push(piece);
  }
  return merged;
}

/** 把句子按上限切段：优先在标点处断开，标点孤立时退化为定长切分。 */
export function splitDialogue(text: string, options: Partial<typeof DIALOGUE_DEFAULTS> = {}): string[] {
  const config = { ...DIALOGUE_DEFAULTS, ...options };
  const chunks: string[] = [];
  for (const sentence of splitSentences(text)) {
    let rest = sentence;
    while (rest.length > config.maxChars) {
      const window = rest.slice(0, config.maxChars + 4);
      const cut = Math.max(window.lastIndexOf("，"), window.lastIndexOf("、"), window.lastIndexOf("；"));
      const index = cut >= config.minChars ? cut + 1 : config.maxChars;
      chunks.push(rest.slice(0, index).trim());
      rest = rest.slice(index).trim();
    }
    if (rest) chunks.push(rest);
  }
  return chunks.filter(Boolean);
}

/** 单段显示时长：按字数折算，并夹在最短/最长之间。 */
export function chunkDurationMs(text: string, options: Partial<typeof DIALOGUE_DEFAULTS> = {}): number {
  const config = { ...DIALOGUE_DEFAULTS, ...options };
  const chars = Math.max(1, String(text ?? "").replace(/\s/g, "").length);
  const raw = (chars / config.charsPerSecond) * 1000;
  return Math.round(Math.min(config.maxDurationMs, Math.max(config.minDurationMs, raw)));
}

/** 一步到位：给出该段对白的全部播放段与各自时长。 */
export function planDialogue(text: string, options: Partial<typeof DIALOGUE_DEFAULTS> = {}): DialogueChunk[] {
  return splitDialogue(text, options).map((chunk) => ({ text: chunk, durationMs: chunkDurationMs(chunk, options) }));
}
