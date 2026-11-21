// Penggambar teks Video Compiler. Dipakai untuk preview DAN untuk membuat PNG transparan
// yang dikirim ke backend saat render, sehingga font & tata letak hasil render identik.

export const FONTS = ["Segoe UI", "Arial", "Calibri", "Verdana", "Tahoma", "Trebuchet MS", "Georgia",
  "Times New Roman", "Courier New", "Impact", "Comic Sans MS", "Consolas"];

function hexToRgba(hex, a = 1) {
  const h = (hex || "#000000").replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((x) => x + x).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

/** Hitung kotak teks (untuk hit-test drag di preview). */
export function textLayout(ctx, c, W, H) {
  const k = Math.min(W, H) / 1080;
  const px = Math.max(4, (c.size || 72) * k);
  ctx.font = `${c.italic ? "italic " : ""}${c.bold ? "700" : "400"} ${px}px "${c.font || "Segoe UI"}", sans-serif`;
  const lines = String(c.text ?? "").split("\n");
  const lh = px * 1.22;
  const widths = lines.map((l) => ctx.measureText(l || " ").width);
  const tw = Math.max(...widths, 1), th = lh * lines.length;
  const pad = c.bg ? px * 0.35 : 0;
  const margin = Math.min(W, H) * 0.06;
  const align = c.align || "center";
  let ax = align === "left" ? margin : align === "right" ? W - margin : W / 2;
  let top = c.vpos === "top" ? margin : c.vpos === "middle" ? (H - th) / 2 : H - margin - th;
  ax += (c.offset_x || 0) * W;
  top += (c.offset_y || 0) * H;
  const boxX = align === "left" ? ax - pad : align === "right" ? ax - tw - pad : ax - tw / 2 - pad;
  return { px, lh, lines, widths, tw, th, pad, ax, top, align, box: { x: boxX, y: top - pad, w: tw + pad * 2, h: th + pad * 2 } };
}

export function drawText(ctx, c, W, H, alpha = 1) {
  if (!c.text) return null;
  ctx.save();
  ctx.globalAlpha = alpha;
  const L = textLayout(ctx, c, W, H);
  if (c.bg) {
    ctx.fillStyle = hexToRgba(c.bg_color, c.bg_opacity ?? 0.55);
    roundRect(ctx, L.box.x, L.box.y, L.box.w, L.box.h, L.px * 0.18);
    ctx.fill();
  }
  ctx.textAlign = L.align;
  ctx.textBaseline = "top";
  L.lines.forEach((line, i) => {
    const y = L.top + i * L.lh + (L.lh - L.px) / 2;
    if (c.shadow) {
      ctx.shadowColor = "rgba(0,0,0,0.65)"; ctx.shadowBlur = L.px * 0.15;
      ctx.shadowOffsetX = L.px * 0.04; ctx.shadowOffsetY = L.px * 0.05;
    }
    if (c.outline) {
      ctx.lineJoin = "round"; ctx.lineWidth = Math.max(1, L.px * 0.09);
      ctx.strokeStyle = c.outline_color || "#000"; ctx.strokeText(line, L.ax, y);
      ctx.shadowColor = "transparent";
    }
    ctx.fillStyle = c.color || "#fff";
    ctx.fillText(line, L.ax, y);
    ctx.shadowColor = "transparent";
  });
  ctx.restore();
  return L.box;
}

/** PNG transparan seukuran kanvas output (opacity & fade diterapkan oleh FFmpeg). */
export function textToPNG(c, W, H) {
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  drawText(cv.getContext("2d"), { ...c }, W, H, 1);
  return cv.toDataURL("image/png");
}
