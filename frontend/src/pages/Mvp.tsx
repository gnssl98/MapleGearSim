import { useEffect, useState } from "react";
import { api, type BmEvalReq, type MvpPlan, type Settings } from "../api";
import { WonRate } from "../components/WonRate";
import { Empty, More, Seg, Stat } from "../components/ui";
import { meso, num, pct } from "../format";
import { purchase, tableKey, type BmProduct } from "./Bm";

type Grade = { id: string; name: string; cash: number; starforce: number; sell_fee: number };
type Row = { label: string; kind: string; note: string; recovery: number; pay: number; recovered_won: number; recovered_meso: number; net_cost: number };
type Res = { need: number; base: Grade | null; target: Grade; benefit_meso: number; benefit_won: number; rows: Row[]; won_per_eok: number };

const wonText = (v: number) => `${v < 0 ? "-" : ""}${Math.round(Math.abs(v)).toLocaleString("ko-KR")}원`;

export function Mvp({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [grades, setGrades] = useState<Grade[]>([]);
  const [products, setProducts] = useState<BmProduct[]>([]);
  const [plan, setPlan] = useState<MvpPlan>(settings.mvp_plan);
  const [res, setRes] = useState<Res | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api<{ grades: Grade[] }>("/mvp/grades").then((r) => setGrades(r.grades)).catch((e) => setError(e.message));
    api<{ products: BmProduct[] }>("/bm/products").then((r) => setProducts(r.products)).catch(() => {});
  }, []);

  // 확률형 탭에서 1회 가격을 넣은 상품·표 = 비교 후보
  const candidates: BmEvalReq[] = products.flatMap((p) => p.tables.map((t, i) => {
    const { unit, bundle } = purchase(settings, p);
    if (!unit) return null;
    const values_eok: Record<string, number> = {};
    for (const r of t.rows) if (settings.bm.values[r.item]) values_eok[r.item] = settings.bm.values[r.item];
    if (!Object.keys(values_eok).length) return null;
    return {
      product: p.id, table: i, unit_price_won: unit, spend_won: 0, values_eok, jackpots: settings.bm.jackpots[tableKey(p.id, i)] ?? [],
      bundle: bundle ? { count: bundle.count, price: bundle.price } : null,
    };
  })).filter(Boolean) as BmEvalReq[];
  const labelOf = (b: BmEvalReq) => {
    const p = products.find((x) => x.id === b.product);
    return p ? p.name + (p.tables.length > 1 ? ` · ${p.tables[b.table].title}` : "") : b.product;
  };
  const chosen = new Set(plan.bm.map((b) => tableKey(b.product, b.table)));
  const toggleBm = (b: BmEvalReq) => setPlan((pl) => ({
    ...pl, bm: chosen.has(tableKey(b.product, b.table)) ? pl.bm.filter((x) => tableKey(x.product, x.table) !== tableKey(b.product, b.table)) : [...pl.bm, b],
  }));

  const set = <K extends keyof MvpPlan>(k: K, v: MvpPlan[K]) => setPlan((p) => ({ ...p, [k]: v }));
  const run = async () => {
    setLoading(true);
    setError("");
    // 저장된 최신 가격으로 갱신해서 보낸다
    const bm = plan.bm.map((b) => candidates.find((c) => tableKey(c.product, c.table) === tableKey(b.product, b.table))).filter(Boolean) as BmEvalReq[];
    const body = { ...plan, bm };
    try {
      setRes(await api<Res>("/mvp/compare", { body }));
      onSettings(await api<Settings>("/settings", { method: "PUT", body: { ...settings, mvp_plan: body } }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const w = settings.won_per_eok;
  const num0 = (v: number | "") => (v === "" ? 0 : v);

  return (
    <div className="mvp">
      <section className="panel toolbar-panel">
        <WonRate settings={settings} onSettings={onSettings} />
        <div className="toolbar wrap">
          <span className="field-label">목표 등급</span>
          <Seg value={plan.target} onChange={(v) => set("target", v)}
            options={grades.map((g) => [g.id, <>{g.name} <small className="muted">{num(g.cash / 10000, 0)}만</small></>] as const)} />
        </div>
        <div className="grid2">
          <label className="row"><span>최근 13주 결제 금액 (지금까지)</span>
            <span className="num-input"><input type="number" min={0} step={10000} value={plan.current_cash}
              onChange={(e) => set("current_cash", Number(e.target.value) || 0)} /><em>원 (캐시)</em></span>
          </label>
          <label className="row"><span>메소마켓 회수율</span>
            <span className="num-input"><input type="number" min={0} max={100} step={1} value={Math.round(plan.mesomarket_recovery * 100)}
              onChange={(e) => set("mesomarket_recovery", (Number(e.target.value) || 0) / 100)} /><em>% (1억 = 위 시세로 살 때 100%)</em></span>
          </label>
          <label className="row"><span>13주 동안 1~17성 스타포스에 쓸 메소</span>
            <span className="num-input"><input type="number" min={0} step={10} value={plan.sf_meso_eok}
              onChange={(e) => set("sf_meso_eok", num0(Number(e.target.value)))} /><em>억</em></span>
          </label>
          <label className="row"><span>13주 동안 경매장에 팔 금액</span>
            <span className="num-input"><input type="number" min={0} step={10} value={plan.sell_meso_eok}
              onChange={(e) => set("sell_meso_eok", num0(Number(e.target.value)))} /><em>억</em></span>
          </label>
          <label className="row"><span>기타 혜택 가치 (쿠폰·버프 등)</span>
            <span className="num-input"><input type="number" min={0} step={1000} value={plan.other_won}
              onChange={(e) => set("other_won", Number(e.target.value) || 0)} /><em>원</em></span>
          </label>
        </div>
        <div>
          <span className="field-label">같이 비교할 확률형 상품</span>
          <div className="chips" style={{ marginTop: 6 }}>
            {candidates.map((b) => (
              <button key={tableKey(b.product, b.table)} type="button" className={`chip ${chosen.has(tableKey(b.product, b.table)) ? "on" : ""}`} onClick={() => toggleBm(b)}>{labelOf(b)}</button>
            ))}
            {!candidates.length && <span className="muted small">확률형 BM 탭에서 1회 가격과 경매장 가격을 넣고 한 번 계산하면 여기에 나와요</span>}
          </div>
        </div>
        <button className="btn primary" onClick={run} disabled={loading || !w || !grades.length}>{loading ? "계산 중…" : !w ? "1억 메소당 원 시세를 먼저 정하세요" : "비교"}</button>
        {error && <p className="error">{error}</p>}
        <More>
          <p>다음 MVP 등급까지 모자란 금액을 어떤 방법으로 채우면 실질 비용이 가장 적은지 비교합니다.</p>
          <ul>
            <li>실질 비용 = 결제 금액 − 회수 가치 − MVP 혜택 가치. 음수면 그 방법으로 MVP를 달성하는 게 오히려 이득이라는 뜻입니다.</li>
            <li>회수: 메소마켓은 위 회수율, 확률형 상품은 기댓값(확률형 BM 탭의 가격 기준, 1회 단위로 올림), 치장 캐시템은 0.</li>
            <li>혜택: 스타포스 할인(1~17성 강화 비용 × 할인율), 경매장 판매 수수료(5% → 3%), 기타 입력값. 추가 결제 없이 유지되는 등급과의 차이만 셉니다.</li>
            <li>⚠ 등급 기준(최근 13주: 브론즈 15만·실버 30만·골드 60만·다이아 90만·레드 150만·블랙 250만)은 2025-09-17 개편 정리값이고, 블랙 스타포스 할인은 레드와 같다고 가정했습니다. 메이플포인트 충전이 MVP 금액에 반영되는지도 게임 안내로 확인하세요. <code>data/game/mvp.yaml</code> 에서 고칠 수 있습니다.</li>
          </ul>
        </More>
      </section>

      {!res ? <Empty icon="star">목표 등급과 금액을 넣고 <b>비교</b>를 누르세요.</Empty> : (
        <>
          <div className="stats-row">
            <Stat label={`${res.target.name}까지 모자란 금액`} value={wonText(res.need)} sub={res.base ? `추가 결제 없으면 ${res.base.name}` : "추가 결제 없으면 MVP 없음"} tone="accent" />
            <Stat label="MVP 혜택 가치" value={wonText(res.benefit_won)} sub={`${meso(res.benefit_meso)} + 기타`} tone="good" />
            <Stat label="스타포스 할인 · 판매 수수료" value={`${pct(res.target.starforce, 0)} · ${pct(res.target.sell_fee, 0)}`} sub={res.target.name} />
          </div>
          <section className="panel">
            <h3>채우는 방법 비교 <small className="muted">실질 비용이 낮은 순</small></h3>
            <div className="plan-list mvp-rows">
              {res.rows.map((r, i) => (
                <div key={r.label} className={`plan-item ${i === 0 ? "best" : ""}`}>
                  <span className="rank">{i + 1}</span>
                  <div className="grow">
                    <b>{r.label}</b>
                    <small className="muted">결제 {wonText(r.pay)} · 회수 {meso(r.recovered_meso)} ({pct(r.recovery, 1)}){r.note && ` · ${r.note}`}</small>
                  </div>
                  <div className="right">
                    <b className={r.net_cost <= 0 ? "ok" : "bad-text"}>{r.net_cost <= 0 ? `이득 ${wonText(-r.net_cost)}` : `비용 ${wonText(r.net_cost)}`}</b>
                    <small className="muted">실질 비용</small>
                  </div>
                </div>
              ))}
            </div>
            {res.need === 0 && <p className="hint">이미 목표 등급 기준을 넘었어요. 추가 결제 없이 혜택을 받습니다.</p>}
          </section>
        </>
      )}
    </div>
  );
}
