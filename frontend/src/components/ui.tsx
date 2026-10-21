import { useState, type ReactNode } from "react";

/** 설명·가정 등 부가 정보는 접어 둔다 */
export function More({ label = "자세히 보기", children, className = "" }: { label?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <details className={`more ${className}`}>
      <summary>{label}</summary>
      <div className="more-body">{children}</div>
    </details>
  );
}

const GRADE_LABEL: Record<string, string> = { rare: "레어", epic: "에픽", unique: "유니크", legendary: "레전" };

export function Grade({ g }: { g: string | null | undefined }) {
  if (!g) return null;
  return <span className={`grade ${g}`}>{GRADE_LABEL[g] ?? g}</span>;
}

/** 아이템 아이콘. src 가 없으면 이름으로 서버에서 찾는다 (장착 장비 = 넥슨 아이콘, 그 외 = 카탈로그) */
export function ItemIcon({ src, name, size = 40, grade, star }: {
  src?: string | null; name?: string | null; size?: number; grade?: string | null; star?: number | null;
}) {
  const [fails, setFails] = useState(0);  // 외부 아이콘 서버가 느릴 때를 위해 한 번 다시 시도
  const base = src || (name ? `/api/icon/by-name?name=${encodeURIComponent(name)}` : null);
  const url = base && fails === 1 ? `${base}${base.includes("?") ? "&" : "?"}retry=1` : base;
  return (
    <span className={`item-icon ${grade ?? ""}`} style={{ width: size, height: size }}>
      {url && fails < 2
        ? <img key={url} src={url} alt="" loading="lazy" onError={() => setTimeout(() => setFails((f) => f + 1), fails ? 0 : 1500)} />
        : <span className="ph">{name?.[0] ?? "?"}</span>}
      {!!star && <span className="star-badge">★{star}</span>}
    </span>
  );
}

export function Stat({ label, value, sub, tone, icon }: {
  label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: "good" | "bad" | "accent"; icon?: IconName;
}) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <span className="stat-label">{icon && <Icon name={icon} size={14} />}{label}</span>
      <b className="stat-value">{value}</b>
      {sub && <small className="stat-sub">{sub}</small>}
    </div>
  );
}

export function Seg<T extends string>({ value, options, onChange }: {
  value: T; options: readonly (readonly [T, ReactNode])[]; onChange: (v: T) => void;
}) {
  return (
    <div className="seg" role="tablist">
      {options.map(([id, label]) => (
        <button key={id} type="button" role="tab" aria-selected={value === id} className={value === id ? "on" : ""} onClick={() => onChange(id)}>{label}</button>
      ))}
    </div>
  );
}

export function Empty({ icon = "box", children }: { icon?: IconName; children: ReactNode }) {
  return <div className="panel empty"><Icon name={icon} size={32} /><div>{children}</div></div>;
}

// lucide 스타일 선 아이콘 (24x24, stroke)
const PATHS = {
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  sparkles: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9zM5 3l.6 1.4L7 5l-1.4.6L5 7l-.6-1.4L3 5l1.4-.6z",
  tag: "M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8zM7.5 7.5h.01",
  hammer: "M15 12l-8.5 8.5a2.1 2.1 0 0 1-3-3L12 9M17.6 15L22 10.6M20 12.5l-6.5-6.5L16 3.5l2 .5 3 3 .5 2z",
  chart: "M3 3v18h18M7 15l4-4 3 3 6-6",
  wallet: "M20 7H5a2 2 0 0 1 0-4h13v4M3 5v14a2 2 0 0 0 2 2h15V7M16 14h.01",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  copy: "M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
  check: "M20 6L9 17l-5-5",
  arrow: "M5 12h14M12 5l7 7-7 7",
  up: "M12 19V5M5 12l7-7 7 7",
  refresh: "M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15",
  box: "M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7zM3.3 7L12 12l8.7-5M12 22V12",
  x: "M18 6L6 18M6 6l12 12",
  alert: "M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  star: "M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z",
} as const;
export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={PATHS[name]} />
    </svg>
  );
}

export function CopyButton({ text, label = "검색 조건 복사" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    } catch {
      /* 클립보드 권한 없음 */
    }
  };
  return (
    <button type="button" className={`icon-btn ${done ? "done" : ""}`} title={`${label}: ${text}`} onClick={copy}>
      <Icon name={done ? "check" : "copy"} size={15} />
    </button>
  );
}
