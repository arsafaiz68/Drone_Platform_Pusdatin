// Ikon garis sederhana (tanpa dependensi tambahan).
const P = {
  import: "M12 3v12m0 0l-4-4m4 4l4-4M4 17v3h16v-3",
  split: "M6 3v18M18 3v18M10 8l-4 4 4 4M14 8l4 4-4 4",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
  undo: "M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3",
  redo: "M15 14l5-5-5-5M20 9H10a6 6 0 000 12h3",
  save: "M5 3h11l3 3v15H5zM8 3v6h8V3M8 21v-7h8v7",
  export: "M12 15V3m0 0l-4 4m4-4l4 4M4 13v8h16v-8",
  play: "M7 4l13 8-13 8z",
  pause: "M7 4h4v16H7zM13 4h4v16h-4z",
  stop: "M6 6h12v12H6z",
  prev: "M6 5v14M18 5L9 12l9 7z",
  next: "M18 5v14M6 5l9 7-9 7z",
  stepb: "M15 6l-6 6 6 6",
  stepf: "M9 6l6 6-6 6",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zm10 3a3 3 0 100-6 3 3 0 000 6z",
  eyeoff: "M3 3l18 18M10.6 5.1A10 10 0 0112 5c6 0 10 7 10 7a17 17 0 01-3.2 3.9M6.6 6.6C3.9 8.4 2 12 2 12s4 7 10 7a9.6 9.6 0 004.2-1",
  vol: "M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 010 6M18.5 6.5a8 8 0 010 11",
  mute: "M4 9h4l5-4v14l-5-4H4zM17 9l5 6M22 9l-5 6",
  lock: "M6 11h12v10H6zM8 11V7a4 4 0 018 0v4",
  unlock: "M6 11h12v10H6zM8 11V7a4 4 0 017.5-2",
  up: "M12 5l-6 6h12z", down: "M12 19l-6-6h12z",
  zoomin: "M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-5-5M8 11h6M11 8v6",
  zoomout: "M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-5-5M8 11h6",
  fit: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  plus: "M12 5v14M5 12h14", x: "M6 6l12 12M18 6L6 18",
  video: "M3 6h12v12H3zM15 10l6-3v10l-6-3", audio: "M9 18V5l11-2v13M9 18a3 3 0 11-6 0 3 3 0 016 0zM20 16a3 3 0 11-6 0 3 3 0 016 0z",
  image: "M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M15 9a1.5 1.5 0 100-.1", text: "M5 6V4h14v2M12 4v16M9 20h6",
  folder: "M3 6h6l2 2h10v11H3z", file: "M6 3h8l5 5v13H6zM14 3v5h5", back: "M15 5l-7 7 7 7",
  copy: "M8 8h12v12H8zM4 16V4h12", edit: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4", home: "M3 11l9-7 9 7v9H3zM9 20v-6h6v6",
  magnet: "M6 3v8a6 6 0 0012 0V3h-4v8a2 2 0 01-4 0V3z", film: "M4 4h16v16H4zM8 4v16M16 4v16M4 8h4M4 12h4M4 16h4M16 8h4M16 12h4M16 16h4",
};

export default function Icon({ n, size = 16, stroke = 1.8, fill }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill={fill ? "currentColor" : "none"} stroke="currentColor"
      strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={P[n] || ""} />
    </svg>
  );
}
