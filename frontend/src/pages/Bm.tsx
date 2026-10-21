import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type BmEvalReq, type Settings } from "../api";
import { WonRate } from "../components/WonRate";
import { Empty, Icon, More, Stat } from "../components/ui";
import { meso, num, pct, won } from "../format";

type Row = { group: string; item: string; prob: number };
export type BmProduct = {
  id: string; name: string; url: string; tables: { title: string; rows: Row[]; total: number }[];
  kind: "fixed" | "event"; source: "snapshot" | "monthly"; tables_date: string | null;
  default_price: number | null; price_date: string | null; price_source: string | null;
  options: BuyOption[]; best_option: number | null; note: string | null;
  notice: { title: string; url: string; date: string | null } | null; price_maybe_changed: boolean;
};
type Status = { refreshing: boolean; error: string | null; event_fetched_at: string | null; stale: boolean; started: boolean };
/** 기간별 표(원더베리 등)는 가장 최근 기간을 기본으로 */
const defaultTable = (p: BmProduct) => (p.tables.length > 1 && p.tables.every((t) => /\d{4}-\d{2}-\d{2}/.test(t.title)) ? p.tables.length - 1 : 0);
export type BuyOption = { label: string; count: number; price: number; unit: number; where: string };
/** 고른 구매 방법 (번호, -1 = 직접 입력). 고른 적 없으면 개당 가장 싼 묶음 */
export const optionIndex = (s: Settings, p: BmProduct) => {
  const i = s.bm.options[p.id];
  if (i === -1 || (i != null && p.options[i])) return i;
  return s.bm.unit_prices[p.id] != null ? -1 : p.best_option ?? -1;
};
/** 1회 가격과 묶음: 고른 묶음 > 직접 입력 가격 */
export function purchase(s: Settings, p: BmProduct): { unit: number | null; bundle: BuyOption | null } {
  const i = optionIndex(s, p);
  const o = i >= 0 ? p.options[i] : null;
  return o ? { unit: o.unit, bundle: o } : { unit: s.bm.unit_prices[p.id] ?? null, bundle: null };
}
type Res = {
  pulls: number; spend_won: number; spend_meso: number; ev_per_pull: number; expected: number; recovery: number;
  breakeven_price_won: number; jackpot_prob: number; jackpot_value: number; jackpot_expected: number; baseline: number;
  need: number | null; need_prob: number | null; pmf: number[]; profit_prob: number; percentiles: Record<string, number>;
  rows: { item: string; prob: number; value: number; ev: number; jackpot: boolean }[]; warnings: string[]; fee: number;
};

const SPENDS = [50_000, 100_000, 300_000, 500_000, 1_000_000];
export const tableKey = (p: string, t: number) => `${p}|${t}`;

export function Bm({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [products, setProducts] = useState<BmProduct[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [snapAt, setSnapAt] = useState<string | null>(null);
  const [pid, setPid] = useState("");
  const [ti, setTi] = useState(0);
  const [unit, setUnit] = useState<number | "">("");  // 직접 입력 1회 가격
  const [opt, setOpt] = useState(-1);
  const [spend, setSpend] = useState<number | "">(100_000);
  const [values, setValues] = useState<Record<string, number | "">>({});
  const [jackpots, setJackpots] = useState<Set<string>>(new Set());
  const [market, setMarket] = useState<Record<string, { eok: number; n: number }>>({});
  const [filter, setFilter] = useState("");
  const [res, setRes] = useState<Res | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadProducts = (first = false) => api<{ products: BmProduct[]; snapshot_at: string; status: Status }>("/bm/products").then((r) => {
    setProducts(r.products);
    setStatus(r.status);
    setSnapAt(r.snapshot_at);
    if (first && r.products[0]) setPid(r.products[0].id);
    // 이벤트성 상품 확률표를 받는 중이면 잠시 뒤 다시 불러온다
    if (r.status.refreshing) setTimeout(() => loadProducts(), 12000);
  }).catch((e) => setError(e.message));
  useEffect(() => { loadProducts(true); }, []);

  const product = products.find((p) => p.id === pid);
  const table = product?.tables[ti];
  const key = tableKey(pid, ti);

  // 상품·표가 바뀌면 저장된 입력 불러오기
  useEffect(() => {
    if (!product) return;
    setOpt(optionIndex(settings, product));
    setUnit(settings.bm.unit_prices[pid] ?? "");
    const v: Record<string, number | ""> = {};
    for (const r of table?.rows ?? []) if (settings.bm.values[r.item] != null) v[r.item] = settings.bm.values[r.item];
    setValues(v);
    setJackpots(new Set(settings.bm.jackpots[key] ?? []));
    setRes(null);
    api<typeof market>(`/bm/market?product=${pid}&table=${ti}`).then(setMarket).catch(() => setMarket({}));
  }, [pid, ti, products.length, product?.source]);

  const valueOf = (item: string) => {
    const v = values[item];
    return v === "" || v == null ? market[item]?.eok ?? 0 : v;
  };
  const rows = useMemo(() => {
    const f = filter.trim();
    return (table?.rows ?? []).filter((r) => !f || r.item.includes(f) || r.group.includes(f));
  }, [table, filter]);

  const run = async () => {
    if (!table || effUnit == null || spend === "") return;
    setLoading(true);
    setError("");
    const values_eok: Record<string, number> = {};
    for (const r of table.rows) if (valueOf(r.item) > 0) values_eok[r.item] = valueOf(r.item);
    const body: BmEvalReq = {
      product: pid, table: ti, unit_price_won: effUnit, spend_won: spend, values_eok, jackpots: [...jackpots],
      bundle: bundle ? { count: bundle.count, price: bundle.price } : null,
    };
    try {
      setRes(await api<Res>("/bm/evaluate", { body }));
      // 입력 저장 (다음에 그대로, MVP 작 탭에서도 사용)
      const own: Record<string, number> = {};
      for (const [k, v] of Object.entries(values)) if (v !== "") own[k] = v;
      onSettings(await api<Settings>("/settings", {
        method: "PUT", body: {
          ...settings, bm: {
            unit_prices: opt === -1 && unit !== "" ? { ...settings.bm.unit_prices, [pid]: unit } : settings.bm.unit_prices,
            options: { ...settings.bm.options, [pid]: opt },
            values: { ...settings.bm.values, ...own },
            jackpots: { ...settings.bm.jackpots, [key]: [...jackpots] },
          },
        },
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggleJ = (item: string) => setJackpots((s) => {
    const n = new Set(s);
    n.has(item) ? n.delete(item) : n.add(item);
    return n;
  });
  const w = settings.won_per_eok;
  const bundle = product && opt >= 0 ? product.options[opt] ?? null : null;
  const effUnit = bundle ? bundle.unit : unit === "" ? null : unit;

  return (
    <div className="bm">
      <section className="panel toolbar-panel">
        <WonRate settings={settings} onSettings={onSettings} />
        <div className="product-grid">
          {products.map((p) => (
            <button key={p.id} type="button" className={`product ${pid === p.id ? "on" : ""}`} onClick={() => { setPid(p.id); setTi(defaultTable(p)); setFilter(""); }}>
              <b>{p.name}</b>
              <small className="muted">
                {(() => {
                  const b = purchase(settings, p);
                  if (p.note && !b.unit) return p.note.includes("판매 종료") ? "판매 종료" : "직접 구매 불가";
                  if (!b.unit) return "가격 미입력";
                  return `${b.bundle && b.bundle.count > 1 ? `${b.bundle.count}개 묶음 · ` : ""}1회 ${num(b.unit, 0)}원${b.bundle && p.price_maybe_changed ? " ⚠" : ""}`;
                })()}
              </small>
              <span className={`kind-tag ${p.kind}`}>{p.kind === "fixed" ? "고정" : "이벤트"}</span>
            </button>
          ))}
        </div>
        {error && <p className="error">{error}</p>}
        <More>
          <p>넥슨 공식 확률 공개 페이지의 확률표로 기댓값을 계산합니다.</p>
          <ul>
            <li><b>고정</b> 상품(루나 크리스탈·골드 애플·알쏭달쏭 상자 등)은 앱에 넣어 둔 확률표({snapAt ?? "-"} 기준)를 씁니다.</li>
            <li><b>이벤트</b> 상품(로얄·마스터피스·콜라보·원더베리 등 구성이 바뀌는 것)은 30일마다 공식 페이지에서 새로 받습니다
              (최근: {status?.event_fetched_at?.slice(0, 10) ?? "아직 없음"}{status?.refreshing ? " · 지금 받는 중" : ""}{status?.error ? ` · 실패: ${status.error}` : ""}). 받기 전에는 넣어 둔 확률표를 씁니다.</li>
            <li><b>1회 가격</b>: 출처가 있는 상품만 기본값을 넣었습니다. 공식 캐시샵 공지는 가격이 이미지라 자동으로 읽지 못해서, 30일마다 공지 목록만 확인해 기본값 기준일 이후 새 공지가 있으면 ⚠로 알려 드립니다. 직접 넣은 가격이 있으면 그 값을 씁니다.</li>
            <li><b>경매장 가격</b>은 넥슨 오픈 API에 없어 직접 넣습니다. 시세 기록 탭에 같은 이름으로 기록한 매물이 있으면 그 중앙값을 기본값으로 씁니다.</li>
          </ul>
          <ul>
            <li>회수 메소 = 나온 아이템의 경매장 가격 × (1 − 판매 수수료 {pct(res?.fee ?? (settings.mvp === "none" || settings.mvp === "bronze" ? 0.05 : 0.03), 0)})</li>
            <li><b>당첨</b>으로 체크한 아이템이 몇 개 나와야 본전인지(나머지 아이템 기대 회수 포함)와 그럴 확률(이항분포)을 보여 줍니다.</li>
            <li>본전 이상 확률·분위수는 다항분포 모의실험(2만 회) 결과입니다.</li>
            <li>가격이 0인 아이템(치장 등 안 팔 것)은 회수 0으로 계산합니다. 상품 구성이 바뀌면 <code>scripts/fetch_bm_tables.py</code> 로 다시 받으세요.</li>
          </ul>
        </More>
      </section>

      {product && table && (
        <div className="bm-layout">
          <section className="panel">
            <div className="toolbar wrap">
              <h3 style={{ margin: 0 }}>{product.name}</h3>
              <span className={`kind-tag ${product.kind}`}>{product.kind === "fixed" ? "고정 확률" : "이벤트 · 30일마다 갱신"}</span>
              <a className="small" href={product.url} target="_blank" rel="noreferrer">공식 확률표 ↗</a>
            </div>
            <p className="muted small" style={{ margin: "4px 0 0" }}>
              확률표 {product.tables_date ?? "-"} 기준{product.source === "snapshot" && product.kind === "event" ? " (넣어 둔 값, 아직 새로 못 받음)" : ""}
            </p>
            {product.note && <p className="hint"><Icon name="info" size={14} /> {product.note}</p>}
            {product.price_maybe_changed && bundle && (
              <p className="hint"><Icon name="alert" size={14} />
                기본 가격({product.price_date} 기준) 이후 캐시샵 공지가 있어요: <a href={product.notice!.url} target="_blank" rel="noreferrer">{product.notice!.title}</a> — 가격이 바뀌었는지 확인하세요
              </p>
            )}
            {product.tables.length > 1 && (
              <select value={ti} onChange={(e) => setTi(Number(e.target.value))} style={{ margin: "8px 0" }}>
                {product.tables.map((t, i) => <option key={i} value={i}>{t.title}</option>)}
              </select>
            )}
            <div className="row" style={{ marginTop: 8 }}>
              <span>구매 방법</span>
              <div className="buy-options">
                {product.options.map((o, i) => (
                  <button key={i} type="button" className={`buy-option ${opt === i ? "on" : ""}`} onClick={() => setOpt(i)} title={o.where}>
                    <b>{o.label}</b>
                    <span>{num(o.price, 0)}원</span>
                    <small className={i === product.best_option ? "ok" : "muted"}>개당 {num(o.unit, 0)}원{i === product.best_option && product.options.length > 1 ? " · 최저" : ""}</small>
                  </button>
                ))}
                <button type="button" className={`buy-option ${opt === -1 ? "on" : ""}`} onClick={() => setOpt(-1)}>
                  <b>직접 입력</b><span>1회 가격</span><small className="muted">이벤트 할인 등</small>
                </button>
              </div>
              {product.price_source && <small className="muted">가격 출처: {product.price_source}</small>}
            </div>
            <div className="grid2">
              {opt === -1 ? (
                <label className="row"><span>1회 가격</span>
                  <span className="num-input"><input type="number" min={0} step={100} value={unit} placeholder="캐시"
                    onChange={(e) => setUnit(e.target.value === "" ? "" : Number(e.target.value))} /><em>원</em></span>
                </label>
              ) : (
                <div className="row"><span>살 수량</span>
                  <b className="buy-preview">{bundle && spend !== "" && Math.floor(spend / bundle.price) > 0
                    ? `${bundle.label} × ${Math.floor(spend / bundle.price)} = ${num(Math.floor(spend / bundle.price) * bundle.count, 0)}회 · ${num(Math.floor(spend / bundle.price) * bundle.price, 0)}원`
                    : bundle ? `묶음 1개 ${num(bundle.price, 0)}원 이상 필요` : "-"}</b>
                </div>
              )}
              <label className="row"><span>현질할 금액</span>
                <span className="num-input"><input type="number" min={0} step={10000} value={spend}
                  onChange={(e) => setSpend(e.target.value === "" ? "" : Number(e.target.value))} /><em>원</em></span>
              </label>
            </div>
            <div className="chips" style={{ marginBottom: 10 }}>
              {SPENDS.map((s) => <button key={s} type="button" className={`chip ${spend === s ? "on" : ""}`} onClick={() => setSpend(s)}>{num(s / 10000, 0)}만원</button>)}
            </div>
            <div className="toolbar">
              <span className="small muted">아이템 {table.rows.length}개 · 당첨 {jackpots.size}개 선택</span>
              {table.rows.length > 12 && <input className="search" placeholder="아이템 검색" value={filter} onChange={(e) => setFilter(e.target.value)} />}
            </div>
            <div className="table-wrap bm-items">
              <table className="dense">
                <thead><tr><th>당첨</th><th>아이템</th><th>확률</th><th>경매장 가격</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.item} className={jackpots.has(r.item) ? "jackpot" : ""}>
                      <td><input type="checkbox" checked={jackpots.has(r.item)} onChange={() => toggleJ(r.item)} style={{ width: "auto" }} /></td>
                      <td className="item-col opts">{r.item}{r.group && r.group !== product.name && <small className="muted"> · {r.group}</small>}</td>
                      <td>{pct(r.prob, r.prob < 0.001 ? 4 : 2)}</td>
                      <td>
                        <span className="num-input compact">
                          <input type="number" min={0} step={0.1} value={values[r.item] ?? ""}
                            placeholder={market[r.item] ? `${num(market[r.item].eok, 2)} (기록)` : "0"}
                            onChange={(e) => setValues({ ...values, [r.item]: e.target.value === "" ? "" : Number(e.target.value) })} />
                          <em>억</em>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button className="btn primary block" onClick={run} disabled={loading || effUnit == null || !w}>
              {loading ? "계산 중…" : !w ? "1억 메소당 원 시세를 먼저 정하세요" : effUnit == null ? "1회 가격을 넣으세요" : "기댓값 계산"}
            </button>
          </section>

          <section className="bm-result">
            {!res ? <Empty icon="sparkles">1회 가격·금액·경매장 가격을 넣고 <b>기댓값 계산</b>을 누르세요.<br />크게 팔리는 아이템에 <b>당첨</b> 체크를 하면 손익분기 개수를 알려 드려요.</Empty> : (
              <>
                {res.warnings.map((x) => <p key={x} className="hint"><Icon name="alert" size={14} /> {x}</p>)}
                {res.need != null && (
                  <section className={`panel verdict-card ${res.need_prob != null && res.need_prob >= 0.5 ? "good" : "bad"}`}>
                    <small className="muted">손익분기</small>
                    <h2>{num(res.pulls, 0)}회 중 당첨 <b>{res.need}개</b> 이상이면 본전</h2>
                    <p className="muted">
                      당첨 기대 {num(res.jackpot_expected, 2)}개 · {res.need}개 이상 나올 확률 <b>{pct(res.need_prob, 1)}</b>
                      {res.need === 0 && " (당첨 없이도 나머지 아이템 기대 회수로 본전)"}
                    </p>
                  </section>
                )}
                <div className="stats-row">
                  <Stat label="기대 회수율" value={pct(res.recovery, 1)} tone={res.recovery >= 1 ? "good" : "bad"} sub={`${num(res.pulls, 0)}회 · ${num(res.spend_won, 0)}원`} />
                  <Stat label="기대 회수" value={meso(res.expected)} sub={`${won(res.expected, w)} · 현질 ${meso(res.spend_meso)}`} />
                  <Stat label="본전 이상 확률" value={pct(res.profit_prob, 1)} tone={res.profit_prob >= 0.5 ? "good" : "bad"} sub="모의실험 2만 회" />
                  <Stat label="손익분기 1회 가격" value={`${num(res.breakeven_price_won, 0)}원`} sub={`1회 기대 회수 ${meso(res.ev_per_pull)}`} tone="accent" />
                </div>
                {res.jackpot_prob > 0 && (
                  <section className="panel">
                    <h3>당첨 개수 분포 <small className="muted">1회 {pct(res.jackpot_prob, 3)} · 1개당 {meso(res.jackpot_value)}</small></h3>
                    <div className="chart">
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={res.pmf.map((p, k) => ({ k, p }))} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                          <XAxis dataKey="k" tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--border)" />
                          <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} width={40} tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--border)" />
                          <Tooltip formatter={(v: number) => pct(v, 2)} labelFormatter={(k) => `당첨 ${k}개`}
                            contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }} />
                          {res.need != null && <ReferenceLine x={res.need} stroke="var(--accent-2)" label={{ value: "본전", fill: "var(--accent-2)", fontSize: 11 }} />}
                          <Bar dataKey="p" isAnimationActive={false}>
                            {res.pmf.map((_, k) => <Cell key={k} fill={res.need != null && k >= res.need ? "var(--good)" : "var(--accent)"} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </section>
                )}
                <section className="panel">
                  <h3>회수 메소 분포</h3>
                  <div className="kv">
                    {(["p10", "p50", "p90", "p99"] as const).map((k) => (
                      <span key={k} style={{ display: "contents" }}>
                        <span>{{ p10: "운 나쁨 (하위 10%)", p50: "보통 (중앙값)", p90: "운 좋음 (상위 10%)", p99: "대박 (상위 1%)" }[k]}</span>
                        <b>{meso(res.percentiles[k])} <small className="muted">{won(res.percentiles[k], w)}</small></b>
                      </span>
                    ))}
                  </div>
                  <More label="아이템별 기대 회수">
                    <table className="dense">
                      <thead><tr><th>아이템</th><th>확률</th><th>가격</th><th>1회 기대</th></tr></thead>
                      <tbody>
                        {[...res.rows].filter((r) => r.ev > 0).sort((a, b) => b.ev - a.ev).map((r) => (
                          <tr key={r.item}><td className="item-col">{r.jackpot && "★ "}{r.item}</td><td>{pct(r.prob, 3)}</td><td>{meso(r.value)}</td><td>{meso(r.ev)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </More>
                </section>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
