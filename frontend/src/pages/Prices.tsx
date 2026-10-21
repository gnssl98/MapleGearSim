import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Meta, type Settings } from "../api";
import { ItemIcon, More, Stat } from "../components/ui";
import { eokToMeso, meso, pct, won } from "../format";

type CompareRes = {
  compare: {
    base_price: number; craft_expected: number; breakeven_price: number; market_price: number | null;
    resale_net: number; market_net: number | null; expected_profit: number | null; loss_probability: number | null;
    percentiles: Record<string, number>; cumulative_breakeven: { name: string; expected: number; cumulative: number }[];
  };
  listing: Record<string, string>;
  target: { star: number; flame_score?: number; potential?: { grade: string; conditions: { keys: string[]; min: number; mode: string }[] }; additional?: { grade: string; conditions: { keys: string[]; min: number; mode: string }[] } };
  base_source: string;
  warnings: string[];
};

const condText = (c: { keys: string[]; min: number; mode: string }) =>
  c.mode === "count" ? `${c.keys.join("/")} ${c.min}줄` : `${c.keys.join("+")} 합 ${c.min}+`;

const effPrice = (r: Record<string, string>) => Number(r.price_meso) * (r.world_type === "other" ? 1.1 : 1);

/** 유사 매물: 같은 아이템, 성 ±1, 같은 잠재 등급 */
const isSimilar = (a: Record<string, string>, b: Record<string, string>) =>
  a.item_name === b.item_name && Math.abs(Number(a.star || 0) - Number(b.star || 0)) <= 1 &&
  (a.potential_grade || "") === (b.potential_grade || "");

type Listing = Record<string, string>;

const EMPTY = {
  item_name: "", slot: "", item_level: "", star: "", potential_grade: "", pot1: "", pot2: "", pot3: "",
  additional_grade: "", add1: "", add2: "", add3: "", flame_score: "", cuttable_count: "",
  price_eok: "", world_type: "own", note: "",
};

export function Prices({ meta, settings }: { meta: Meta; settings: Settings }) {
  const [rows, setRows] = useState<Listing[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [filter, setFilter] = useState("");
  const [similar, setSimilar] = useState<Listing | null>(null);
  const [cmp, setCmp] = useState<CompareRes | null>(null);
  const [cmpLoading, setCmpLoading] = useState("");
  const [cmpBase, setCmpBase] = useState<number | "">("");

  const compare = async (r: Listing, base: number | "" = cmpBase) => {
    setCmpLoading(r.id);
    setError("");
    try {
      setCmp(await api<CompareRes>("/market/craft-compare", { body: { listing_id: r.id, base_price: base === "" ? null : eokToMeso(base) } }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCmpLoading("");
    }
  };
  const [error, setError] = useState("");

  const load = () => api<Listing[]>("/listings").then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!form.item_name || !form.price_eok) {
      setError("아이템명과 가격은 필수입니다");
      return;
    }
    const { price_eok, ...rest } = form;
    const body: Record<string, unknown> = { ...rest, price_meso: eokToMeso(Number(price_eok)) };
    for (const k of ["item_level", "star", "flame_score", "cuttable_count"]) body[k] = rest[k as keyof typeof rest] === "" ? null : Number(rest[k as keyof typeof rest]);
    try {
      await api("/listings", { body });
      // 같은 아이템 연속 입력이 많으므로 가격·옵션만 비운다
      setForm((f) => ({ ...f, price_eok: "", pot1: "", pot2: "", pot3: "", add1: "", add2: "", add3: "", flame_score: "", note: "" }));
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async (id: string) => {
    await api(`/listings/${id}`, { method: "DELETE" });
    load();
  };

  const partName = (id: string) => meta.parts.find((p) => p.id === id)?.name ?? id;
  const shown = useMemo(() => {
    const f = filter.trim();
    return [...rows].reverse()
      .filter((r) => !f || r.item_name.includes(f) || partName(r.slot).includes(f))
      .filter((r) => !similar || isSimilar(r, similar));
  }, [rows, filter, similar]);

  // 시세 추이: 표시 중인 매물의 관측 시각별 실구매가 (아이템이 한 종류로 좁혀졌을 때 의미 있음)
  const trend = useMemo(() => shown.map((r) => ({ t: new Date(r.observed_at).getTime(), price: effPrice(r) / 1e8, name: r.item_name, star: r.star }))
    .filter((p) => Number.isFinite(p.t)), [shown]);
  const itemKinds = new Set(shown.map((r) => r.item_name)).size;

  const stats = useMemo(() => {
    const prices = shown.map(effPrice).sort((a, b) => a - b);
    if (!prices.length) return null;
    return { n: prices.length, min: prices[0], median: prices[Math.floor(prices.length / 2)] };
  }, [shown]);

  return (
    <div className="prices">
      <form className="panel form" onSubmit={submit}>
        <h2>매물 기록</h2>
        <More>입력할 때마다 <code>data/user/listings.csv</code>에 누적 저장됩니다 (엑셀로 열람 가능).
          노작(베이스)은 <b>성 0, 잠재 등급 비움</b>으로 기록하면 직작 비교·추천·구매 상한가에서 노작 시세로 쓰입니다.</More>
        <div className="grid3">
          <label className="row wide"><span>아이템명 *</span><input value={form.item_name} onChange={set("item_name")} placeholder="에테르넬 나이트헬름" /></label>
          <label className="row"><span>부위</span>
            <select value={form.slot} onChange={set("slot")}>
              <option value="">-</option>
              {meta.parts.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="row"><span>레벨</span><input type="number" value={form.item_level} onChange={set("item_level")} /></label>
          <label className="row"><span>성</span><input type="number" value={form.star} onChange={set("star")} /></label>
          <label className="row"><span>가위 잔여</span><input type="number" value={form.cuttable_count} onChange={set("cuttable_count")} /></label>
        </div>
        <div className="grid4">
          <label className="row"><span>잠재 등급</span>
            <select value={form.potential_grade} onChange={set("potential_grade")}>
              <option value="">-</option>{meta.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </label>
          <label className="row"><span>잠재 1</span><input value={form.pot1} onChange={set("pot1")} placeholder="STR +13%" /></label>
          <label className="row"><span>잠재 2</span><input value={form.pot2} onChange={set("pot2")} /></label>
          <label className="row"><span>잠재 3</span><input value={form.pot3} onChange={set("pot3")} /></label>
          <label className="row"><span>에디 등급</span>
            <select value={form.additional_grade} onChange={set("additional_grade")}>
              <option value="">-</option>{meta.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </label>
          <label className="row"><span>에디 1</span><input value={form.add1} onChange={set("add1")} /></label>
          <label className="row"><span>에디 2</span><input value={form.add2} onChange={set("add2")} /></label>
          <label className="row"><span>에디 3</span><input value={form.add3} onChange={set("add3")} /></label>
        </div>
        <div className="grid4">
          <label className="row"><span>추옵 급수</span><input type="number" value={form.flame_score} onChange={set("flame_score")} /></label>
          <label className="row"><span>가격 *</span><span className="num-input"><input type="number" step="0.01" value={form.price_eok} onChange={set("price_eok")} /><em>억</em></span></label>
          <label className="row"><span>서버</span>
            <select value={form.world_type} onChange={set("world_type")}>
              <option value="own">자서버</option><option value="other">타서버 (+10% MP)</option>
            </select>
          </label>
          <label className="row"><span>메모</span><input value={form.note} onChange={set("note")} /></label>
        </div>
        <button className="btn primary block" type="submit">기록</button>
        {error && <p className="error">{error}</p>}
      </form>

      {cmp && (() => {
        const c = cmp.compare;
        const t = cmp.target;
        const good = (c.expected_profit ?? 0) >= 0;
        return (
          <section className="panel">
            <div className="toolbar">
              <h2>직작 vs 구매 <small className="muted">{cmp.listing.item_name} {t.star}성 매물 기준</small></h2>
              <button className="link" onClick={() => setCmp(null)}>닫기</button>
            </div>
            <p className="small">
              목표 스펙: {t.star}성
              {t.potential && <> · 잠재 {t.potential.grade} ({t.potential.conditions.map(condText).join(", ") || "옵션 무관"})</>}
              {t.additional && <> · 에디 {t.additional.grade} ({t.additional.conditions.map(condText).join(", ") || "옵션 무관"})</>}
              {t.flame_score != null && <> · 추옵 {t.flame_score}급+</>}
            </p>
            <div className="stats-row">
              <Stat label="직작 기대 비용" value={meso(c.breakeven_price)} sub={`노작 ${meso(c.base_price)} (${cmp.base_source}) + 강화 ${meso(c.craft_expected)}`} />
              <Stat label="매물 실구매가" value={meso(c.market_price)} sub={cmp.listing.world_type === "other" ? "타서버 +10% 포함" : "자서버"} />
              <Stat label={good ? "직작이 기대값상 이득" : "구매가 기대값상 이득"} value={meso(Math.abs(c.expected_profit ?? 0))}
                sub={won(Math.abs(c.expected_profit ?? 0), settings.won_per_eok)} tone={good ? "good" : "bad"} />
              <Stat label="직작이 더 비쌀 확률" value={pct(c.loss_probability, 1)} sub={`중앙값 ${meso(c.percentiles.p50)} · 상위 10% ${meso(c.percentiles.p90)}`}
                tone={(c.loss_probability ?? 1) <= 0.5 ? "good" : "bad"} />
            </div>
            <div className="grid2">
              <table className="dense">
                <thead><tr><th>단계</th><th>기대 비용</th><th>누적 (노작 포함)</th></tr></thead>
                <tbody>
                  <tr><td>노작</td><td>{meso(c.base_price)}</td><td>{meso(c.base_price)}</td></tr>
                  {c.cumulative_breakeven.map((s) => <tr key={s.name}><td>{s.name}</td><td>{meso(s.expected)}</td><td>{meso(s.cumulative)}</td></tr>)}
                </tbody>
              </table>
              <div>
                <label className="row"><span>노작 가격 직접 입력 (비우면 기록된 노작 시세)</span>
                  <span className="num-input"><input type="number" step="0.1" value={cmpBase} onChange={(e) => setCmpBase(e.target.value === "" ? "" : Number(e.target.value))} /><em>억</em></span>
                </label>
                <button className="chip" onClick={() => compare(cmp.listing, cmpBase)}>다시 계산</button>
                {cmp.warnings.map((w) => <p key={w} className="error small">{w}</p>)}
                <More>
                  <ul className="small muted">
                    <li>노작 = 같은 아이템, 성 0, 잠재 없음/레어로 기록한 매물. 파괴 시 스페어도 노작 시세로 계산합니다.</li>
                    <li>잠재는 주스탯% 합과 유효 옵션 줄 수가 매물 이상일 확률로 계산합니다. 비용·확률 설정은 설정 탭 기준입니다.</li>
                  </ul>
                </More>
              </div>
            </div>
          </section>
        );
      })()}

      <section className="panel">
        <div className="toolbar">
          <h2>기록된 매물 <small className="muted">{rows.length}건</small></h2>
          <input className="search" placeholder="아이템명/부위 검색" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        {stats && (
          <p className="muted">실구매가 기준(타서버 +10%) — {stats.n}건 · 최저 <b>{meso(stats.min)}</b> · 중앙값 <b>{meso(stats.median)}</b></p>
        )}
        {similar && (
          <p className="chips">
            <span className="chip on">유사 매물: {similar.item_name} {similar.star}±1성 {similar.potential_grade || ""}
              <button type="button" className="chip-x" onClick={() => setSimilar(null)}>×</button>
            </span>
          </p>
        )}
        {trend.length >= 2 && itemKinds <= 3 && (
          <div className="chart">
            <ResponsiveContainer width="100%" height={200}>
              <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid strokeOpacity={0.2} />
                <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time"
                  tickFormatter={(t) => new Date(t).toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" })} fontSize={11} />
                <YAxis dataKey="price" unit="억" fontSize={11} width={56} />
                <Tooltip formatter={(v: number, k: string) => (k === "price" ? `${v.toFixed(2)}억` : new Date(v).toLocaleString("ko-KR"))} />
                <Scatter data={trend} fill="var(--accent)" line={{ stroke: "var(--accent)", strokeOpacity: 0.4 }} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        )}
        {trend.length >= 2 && itemKinds > 3 && <p className="muted small">아이템명으로 검색하면 시세 추이 차트가 표시됩니다.</p>}
        <div className="table-wrap">
          <table className="dense">
            <thead>
              <tr><th>관측</th><th>아이템</th><th>부위</th><th>성</th><th>잠재</th><th>에디</th><th>추옵</th><th>가위</th><th>가격</th><th>서버</th><th /></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td>{r.observed_at.replace("T", " ")}</td>
                  <td className="item-col"><span className="with-icon"><ItemIcon name={r.item_name} size={24} />{r.item_name}{r.note && <small className="muted"> · {r.note}</small>}</span></td>
                  <td>{partName(r.slot)}</td>
                  <td>{r.star}</td>
                  <td className="opts">{[r.pot1, r.pot2, r.pot3].filter(Boolean).join(" / ")}</td>
                  <td className="opts">{[r.add1, r.add2, r.add3].filter(Boolean).join(" / ")}</td>
                  <td>{r.flame_score}</td>
                  <td>{r.cuttable_count}</td>
                  <td title={won(Number(r.price_meso), settings.won_per_eok)}>{meso(Number(r.price_meso))}</td>
                  <td>{r.world_type === "other" ? "타" : "자"}</td>
                  <td>
                    <button className="link" style={{ color: "var(--accent)" }} onClick={() => setSimilar(r)}>유사</button>
                    <button className="link" style={{ color: "var(--accent-2)" }} disabled={!!cmpLoading}
                      title="이 매물과 같은 스펙을 노작부터 직작할 때와 비교" onClick={() => { setCmpBase(""); compare(r, ""); }}>
                      {cmpLoading === r.id ? "계산 중…" : "직작 비교"}
                    </button>
                    <button className="link" onClick={() => remove(r.id)}>삭제</button>
                  </td>
                </tr>
              ))}
              {!shown.length && <tr><td colSpan={11} className="muted center">기록이 없습니다</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
