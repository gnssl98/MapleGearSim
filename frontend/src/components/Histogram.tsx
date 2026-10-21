import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Histogram as H } from "../api";
import { meso } from "../format";

type Props = {
  data: H;
  markers?: { value: number; label: string; color: string }[];
};

export function Histogram({ data, markers = [] }: Props) {
  const total = data.reduce((s, d) => s + d.count, 0) || 1;
  const rows = data.map((d, i) => ({ i, lo: d.lo, hi: d.hi, share: d.count / total }));
  // 카테고리 축이므로 마커는 해당 값이 속한 구간 인덱스에 표시 (범위 밖이면 양 끝)
  const binOf = (v: number) => {
    const idx = rows.findIndex((r) => v >= r.lo && v < r.hi);
    if (idx >= 0) return idx;
    return v < (rows[0]?.lo ?? 0) ? 0 : rows.length - 1;
  };
  const tickEvery = Math.max(1, Math.floor(rows.length / 6));
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={rows} margin={{ top: 18, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
          <XAxis dataKey="i" interval={tickEvery - 1} tickFormatter={(i) => meso(rows[i]?.lo)}
                 tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--border)" />
          <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} width={36}
                 tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--border)" />
          <Tooltip
            cursor={{ fill: "var(--hover)" }}
            contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
            labelFormatter={() => ""}
            formatter={(_v, _n, item) => {
              const p = item.payload as (typeof rows)[number];
              return [`${(p.share * 100).toFixed(2)}%`, `${meso(p.lo)} ~ ${meso(p.hi)}`];
            }}
          />
          <Bar dataKey="share" fill="var(--accent)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
          {markers.map((m, k) => (
            <ReferenceLine key={m.label} x={binOf(m.value)} stroke={m.color} strokeDasharray="4 3"
                           label={{ value: `${m.label} ${meso(m.value)}`, position: k % 2 ? "insideTopRight" : "insideTopLeft",
                                    fill: m.color, fontSize: 11 }} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
