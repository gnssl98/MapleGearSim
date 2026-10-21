const EOK = 100_000_000;
const MAN = 10_000;

/** 메소를 "16.54억" / "4,500만" 형식으로 */
export function meso(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "-";
  const sign = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 10_000 * EOK) return `${sign}${(a / (10_000 * EOK)).toFixed(2)}조`;
  if (a >= EOK) return `${sign}${(a / EOK).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}억`;
  if (a >= MAN) return `${sign}${Math.round(a / MAN).toLocaleString("ko-KR")}만`;
  return `${sign}${Math.round(a).toLocaleString("ko-KR")}`;
}

/** 원화 병기: 1억 메소당 원 시세가 있을 때 */
export function won(v: number | null | undefined, wonPerEok: number | null): string {
  if (v == null || !wonPerEok || !Number.isFinite(v)) return "";
  const w = (v / EOK) * wonPerEok;
  return `≈ ${Math.round(w).toLocaleString("ko-KR")}원`;
}

/** 큰 정수를 "1억 295만" 형식으로 (만 단위 미만 생략) */
export function koUnit(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "-";
  const a = Math.floor(Math.abs(v));
  const eok = Math.floor(a / EOK);
  const man = Math.floor((a % EOK) / MAN);
  const parts = [eok && `${eok.toLocaleString("ko-KR")}억`, man && `${man.toLocaleString("ko-KR")}만`].filter(Boolean);
  return (v < 0 ? "-" : "") + (parts.length ? parts.join(" ") : a.toLocaleString("ko-KR"));
}

export function pct(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "-";
  const p = v * 100;
  if (p !== 0 && Math.abs(p) < 0.01) return `${p.toPrecision(2)}%`;
  return `${p.toFixed(digits)}%`;
}

export function num(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "-";
  return v.toLocaleString("ko-KR", { maximumFractionDigits: digits });
}

export const eokToMeso = (eok: number) => eok * EOK;
export const mesoToEok = (m: number) => m / EOK;
