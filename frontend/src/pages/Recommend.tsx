import { useMemo, useState } from "react";
import { api, presetText, type Assumptions, type HwansanRow, type PresetInfo, type Settings } from "../api";
import { ItemIcon, More, Stat } from "../components/ui";
import { TicketHint } from "./Shopping";
import { meso, num, pct, won } from "../format";

type Cand = {
  slot: string;
  item: string;
  kind: "starforce" | "potential" | "additional" | "flame" | "buy" | "base";
  label: string;
  gain: number;
  damage_pct: number;
  cost: number;
  per_eok: number;
  detail: Record<string, any>;
  notes: string[];
};
type Result = {
  name: string;
  candidates: Cand[];
  plan: { chosen: Cand[]; gain: number; cost: number };
  budget: number;
  assumptions: Assumptions;
  spec: Record<string, number>;
  basis: Record<string, number>;
  table: HwansanRow[];
  excluded: string[];
  notes: string[];
  presets: PresetInfo;
  warnings: string[];
};

const KINDS: { id: Cand["kind"]; label: string }[] = [
  { id: "starforce", label: "스타포스" },
  { id: "potential", label: "잠재" },
  { id: "additional", label: "에디" },
  { id: "flame", label: "추옵" },
  { id: "buy", label: "매물 구매" },
  { id: "base", label: "노작+직작" },
];
const kindLabel = (k: string) => KINDS.find((x) => x.id === k)?.label ?? k;

export function HwansanTable({ rows }: { rows: HwansanRow[] }) {
  return (
    <table className="dense">
      <thead><tr><th>1단위</th><th>환산 주스탯</th><th>보스 딜 증가</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}><td>{r.label}</td><td>{num(r.hwansan, 1)}</td><td>{pct(r.damage_pct / 100, 3)}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

export function Recommend({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [name, setName] = useState(settings.characters[0] ?? "");
  const [budget, setBudget] = useState(settings.budget_eok);
  const [res, setRes] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [kinds, setKinds] = useState<Set<string>>(new Set(KINDS.map((k) => k.id)));
  const [bestOnly, setBestOnly] = useState(true);
  const [limit, setLimit] = useState(30);

  const run = async (target = name) => {
    if (!target) return;
    setLoading(true);
    setError("");
    try {
      setRes(await api<Result>("/recommend", { body: { name: target, budget_eok: budget } }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const saveExcluded = async (list: string[]) => {
    onSettings(await api<Settings>("/settings", { method: "PUT", body: { ...settings, excluded_items: list } }));
    run();
  };

  const rows = useMemo(() => {
    if (!res) return [];
    let r = res.candidates.filter((c) => kinds.has(c.kind));
    if (bestOnly) {
      const seen = new Set<string>();
      r = r.filter((c) => {
        const k = `${c.slot}|${c.kind}`;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
    }
    return r;
  }, [res, kinds, bestOnly]);

  const toggle = (k: string) => setKinds((s) => {
    const n = new Set(s);
    n.has(k) ? n.delete(k) : n.add(k);
    return n;
  });

  const w = settings.won_per_eok;
  const eventSaving = (c: Cand) => (c.detail.event_cost != null ? c.cost - c.detail.event_cost : null);

  return (
    <div className="recommend">
      <section className="panel toolbar-panel">
        <form className="char-search" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <select value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 200 }}>
            {settings.characters.length === 0 && <option value="">내 캐릭터 탭에서 먼저 불러오세요</option>}
            {settings.characters.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <span className="num-input" style={{ maxWidth: 200 }}>
            <em>예산</em><input type="number" min={0} step={1} value={budget} onChange={(e) => setBudget(Number(e.target.value))} /><em>억</em>
          </span>
          <button className="btn primary" type="submit" disabled={loading || !name}>{loading ? "계산 중…" : "추천 계산"}</button>
        </form>
        {error && <p className="error">{error}</p>}
        <More>
          이득은 <b>환산 주스탯</b>(현재 스펙에서 최종 주스탯 1포인트와 같은 딜 증가 = 1)입니다.
          보스 방어율 {settings.hwansan.boss_armor}%{settings.hwansan.crit_rate_100 ? ", 크확 100%" : ""} 가정 · 설정 탭에서 변경.
          비용은 현재 설정(MVP·PC방·이벤트) 기준 기대값이며, 매물은 시세 기록 탭의 데이터를 씁니다.
          보스용 프리셋 기준이며 프리셋 변경은 내 캐릭터 탭에서 합니다.
        </More>
      </section>

      {res && (
        <>
          {res.warnings.map((w) => <p key={w} className="error small">{w}</p>)}
          <TicketHint settings={settings} />
          <div className="stats-row">
            <Stat label="총 환산 증가" value={`+${num(res.plan.gain, 0)}`} tone="good" sub={`억당 ${num(res.plan.cost ? res.plan.gain / (res.plan.cost / 1e8) : 0, 1)}`} icon="sparkles" />
            <Stat label="총 기대 비용" value={meso(res.plan.cost)} sub={won(res.plan.cost, w) || `예산 ${meso(res.budget)}`} />
            <Stat label="선택 항목" value={`${res.plan.chosen.length}개`} />
            <Stat label="기준 프리셋" value="보스용" sub={`${presetText(res.presets.target)} · ${res.presets.custom ? "직접 지정" : "자동 추정"}`} />
          </div>
          <section className="panel">
            <h3>예산 {meso(res.budget)} 최적 조합</h3>
            <div className="plan-list">
              {res.plan.chosen.map((c, i) => (
                <div key={i} className="plan-item">
                  <ItemIcon name={c.item} size={40} />
                  <div className="grow">
                    <small className="muted">{c.slot} · <span className={`kind ${c.kind}`}>{kindLabel(c.kind)}</span></small>
                    <b>{c.label}</b>
                    <small className="muted">{c.item}</small>
                  </div>
                  <div className="right">
                    <b className="ok">+{num(c.gain, 0)}</b>
                    <small className="muted">{meso(c.cost)} · 억당 {c.cost <= 0 ? "∞" : num(c.per_eok, 1)}</small>
                  </div>
                </div>
              ))}
              {!res.plan.chosen.length && <p className="muted center">예산 안에서 고를 항목이 없습니다</p>}
            </div>
            <More label="표로 보기 · 비고"><CandTable rows={res.plan.chosen} w={w} eventSaving={eventSaving} /></More>
          </section>

          <section className="panel">
            <div className="toolbar">
              <h2>억당 환산 랭킹 <small className="muted">{rows.length}개</small></h2>
              <div className="chips">
                {KINDS.map((k) => (
                  <button key={k.id} type="button" className={`chip ${kinds.has(k.id) ? "on" : ""}`} onClick={() => toggle(k.id)}>{k.label}</button>
                ))}
                <label className="check small" style={{ margin: 0 }}>
                  <input type="checkbox" checked={bestOnly} onChange={(e) => setBestOnly(e.target.checked)} />장비·종류별 최고만
                </label>
              </div>
            </div>
            <CandTable rows={rows.slice(0, limit)} w={w} eventSaving={eventSaving} rank
              onExclude={(item) => saveExcluded([...settings.excluded_items, item])} />
            {rows.length > limit && <button className="chip" onClick={() => setLimit(limit + 30)}>더 보기</button>}
            {res.excluded.length > 0 && (
              <p className="small muted">제외한 장비:{" "}
                {res.excluded.map((x) => (
                  <span key={x} className="chip">{x}
                    <button type="button" className="chip-x" title="다시 포함" onClick={() => saveExcluded(settings.excluded_items.filter((e) => e !== x))}>×</button>
                  </span>
                ))}
              </p>
            )}
          </section>

          <section className="panel">
           <More label="환산표 · 스펙 분해 · 계산 가정">
           <div className="two-col">
            <div>
              <h3>현재 스펙 환산표</h3>
              <HwansanTable rows={res.table} />
            </div>
            <div>
              <h3>스펙 분해 <small className="muted">주스탯 = 순수 × (1 + %) + 미적용</small></h3>
              <div className="kv">
                <span>최종 주스탯</span><b>{num(res.spec.main, 0)}</b>
                <span>순수 주스탯 (추정)</span><b>{num(res.basis.main_pure, 0)}</b>
                <span>주스탯 % (장비 합)</span><b>{num(res.basis.item_main_pct, 0)}% {res.assumptions.extra_main_pct ? `+ ${res.assumptions.extra_main_pct}%` : ""}</b>
                <span>미적용 (심볼 + 하이퍼)</span><b>{num(res.basis.symbol_main, 0)} + {num(res.basis.hyper_main, 0)}{res.assumptions.extra_main_static ? ` + ${res.assumptions.extra_main_static}` : ""}</b>
                <span>공격력 (순수 / %)</span><b>{num(res.spec.att, 0)} ({num(res.basis.att_pure, 0)} / {num(res.spec.att_pct, 0)}%)</b>
                <span>데미지+보공 / 최종뎀</span><b>{num(res.spec.dmg + res.spec.boss, 1)}% / {num(res.spec.final_dmg, 2)}%</b>
                <span>방무 / 크뎀</span><b>{num(res.spec.ied, 2)}% / {num(res.spec.crit_dmg, 2)}%</b>
              </div>
              <ul className="small muted">
                {res.notes.map((n) => <li key={n}>{n}</li>)}
                <li>헥사 스탯 등 장비 외 미적용 주스탯·주스탯%는 API로 분해하지 않아 설정의 보정값으로 넣을 수 있습니다.</li>
              </ul>
            </div>
           </div>
           </More>
          </section>
        </>
      )}
    </div>
  );
}

function CandTable({ rows, w, eventSaving, rank, onExclude }: {
  rows: Cand[];
  w: number | null;
  eventSaving: (c: Cand) => number | null;
  rank?: boolean;
  onExclude?: (item: string) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="dense rec">
        <thead>
          <tr>
            {rank && <th>#</th>}<th>부위</th><th>장비</th><th>종류</th><th>내용</th><th>환산 +</th><th>딜 +</th>
            <th>기대 비용</th><th>억당 환산</th><th>샤타 대기 시</th><th>비고</th>{onExclude && <th />}
          </tr>
        </thead>
        <tbody>
          {rows.map((c, i) => {
            const save = eventSaving(c);
            return (
              <tr key={`${c.slot}${c.kind}${c.label}${i}`}>
                {rank && <td>{i + 1}</td>}
                <td>{c.slot}</td>
                <td className="item-col"><span className="with-icon"><ItemIcon name={c.item} size={24} />{c.item}</span></td>
                <td><span className={`kind ${c.kind}`}>{kindLabel(c.kind)}</span></td>
                <td className="item-col">{c.label}{c.detail.prob != null && <small className="muted"> · 1회 {pct(c.detail.prob)}</small>}</td>
                <td>{num(c.gain, 0)}</td>
                <td>{pct(c.damage_pct / 100, 2)}</td>
                <td title={won(c.cost, w)}>{meso(c.cost)}</td>
                <td><b>{c.cost <= 0 ? "∞ (차익)" : num(c.per_eok, 1)}</b></td>
                <td>{save != null && save > 0 ? <span className="ok" title={`이벤트 시 ${meso(c.detail.event_cost)}`}>-{meso(save)}</span> : "-"}</td>
                <td className="opts small muted">{c.notes.join(" · ")}</td>
                {onExclude && <td><button className="link" title="이 장비를 추천에서 제외" onClick={() => onExclude(c.item)}>제외</button></td>}
              </tr>
            );
          })}
          {!rows.length && <tr><td colSpan={12} className="muted center">후보가 없습니다</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
