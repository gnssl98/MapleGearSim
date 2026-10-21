import { useState } from "react";
import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Settings } from "../api";
import { ItemIcon, More, Stat } from "../components/ui";
import { meso, num, pct, won } from "../format";

type LuckStat = { attempts: number; actual: number; expected: number; below: number | null };
type Item = {
  kind: "starforce" | "potential" | "cube";
  character: string;
  item: string;
  attempts: number;
  meso: number;
  successes: number;
  destroys: number;
  grade_ups: number;
  first: string;
  last: string;
  start_star: number | null;
  end_star: number | null;
  cube_types: Record<string, number>;
  no_cost: number;
};
type Session = {
  character: string; item: string; level: number | null; start: number; end: number; attempts: number;
  destroys: number; first: string; last: string; actual: number | null; expected: number | null;
};
type Result = {
  start: string;
  end: string;
  totals: { starforce: number; potential: number; cube: number; all: number; attempts: Record<string, number> };
  daily: { date: string; starforce: number; potential: number; cube: number; attempts: number }[];
  items: Item[];
  characters: string[];
  luck: {
    starforce_success: LuckStat;
    starforce_destroy: LuckStat;
    grade_up: LuckStat;
    starforce_cost: { sessions: number; actual: number; expected: number };
  };
  sessions: Session[];
  cube_counts: Record<string, number>;
  unknown_levels: Record<string, number>;
  levels: Record<string, number>;
  superior: number;
  assumptions: string[];
};

const KIND_LABEL = { starforce: "스타포스", potential: "메소 재설정", cube: "큐브" };
const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const daysAgo = (n: number) => iso(new Date(Date.now() - n * 86400000));
const MAN = 1e4;

function luckText(s: LuckStat, good: "more" | "less") {
  if (!s.attempts || s.below == null) return "기록 없음";
  // u = 이번 결과보다 운이 나빴을 확률 (mid-p)
  const u = good === "more" ? s.below : 1 - s.below;
  return u >= 0.5 ? `상위 ${pct(1 - u, 1)} (운 좋음)` : `하위 ${pct(u, 1)} (운 나쁨)`;
}

function luckTone(s: LuckStat, good: "more" | "less"): "good" | "bad" | undefined {
  if (!s.attempts || s.below == null) return undefined;
  const u = good === "more" ? s.below : 1 - s.below;
  return u >= 0.5 ? "good" : "bad";
}

export function Ledger({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [start, setStart] = useState(daysAgo(29));
  const [end, setEnd] = useState(daysAgo(0));
  const [character, setCharacter] = useState("");
  const [res, setRes] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [levels, setLevels] = useState<Record<string, number>>({});
  const [prices, setPrices] = useState<Record<string, number>>({});

  const run = async () => {
    setLoading(true);
    setError("");
    try {
      const q = new URLSearchParams({ start, end, ...(character ? { character } : {}) });
      setRes(await api<Result>(`/ledger?${q}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const saveLedger = async (patch: Partial<Settings["ledger"]>) => {
    const ledger = { ...settings.ledger, ...patch };
    onSettings(await api<Settings>("/settings", { method: "PUT", body: { ...settings, ledger } }));
  };

  const range = (n: number) => { setStart(daysAgo(n - 1)); setEnd(daysAgo(0)); };
  const w = settings.won_per_eok;
  const cubePrice = (t: string) => prices[t] ?? (settings.ledger.cube_prices[t] ?? 0) / MAN;

  return (
    <div className="ledger">
      <section className="panel toolbar-panel">
        <form className="char-search" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} style={{ maxWidth: 160 }} />
          <span className="muted">~</span>
          <input type="date" value={end} min={start} max={daysAgo(0)} onChange={(e) => setEnd(e.target.value)} style={{ maxWidth: 160 }} />
          <div className="chips">
            {[7, 30, 60].map((n) => <button key={n} type="button" className="chip" onClick={() => range(n)}>최근 {n}일</button>)}
          </div>
          <select value={character} onChange={(e) => setCharacter(e.target.value)} style={{ maxWidth: 180 }}>
            <option value="">전체 캐릭터</option>
            {(res?.characters ?? settings.characters).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button className="btn primary" type="submit" disabled={loading}>{loading ? "기록 불러오는 중…" : "조회"}</button>
        </form>
        {error && <p className="error">{error}</p>}
        <More>
          넥슨 오픈 API의 스타포스·잠재능력 재설정·큐브 사용 기록(API 키 주인 계정의 모든 캐릭터)으로 쓴 메소와 운을 계산합니다.
          처음 조회할 때는 하루당 3번씩 호출해서 30일이면 30초쯤 걸리고, 지난 날짜는 캐시를 씁니다. 한 번에 최대 62일까지 볼 수 있습니다.
        </More>
      </section>

      {res && (
        <>
          <h3 className="section-title">{res.start} ~ {res.end} {character && <small className="muted">· {character}</small>}</h3>
          <div className="stats-row">
            <Stat label="총 사용 메소" value={meso(res.totals.all)} sub={won(res.totals.all, w)} tone="accent" icon="wallet" />
            <Stat label="스타포스" value={meso(res.totals.starforce)} sub={`${num(res.totals.attempts.starforce, 0)}회`} icon="star" />
            <Stat label="메소 재설정" value={meso(res.totals.potential)} sub={`잠재·에디 ${num(res.totals.attempts.potential, 0)}회`} />
            <Stat label="큐브" value={`${num(res.totals.attempts.cube, 0)}개`} sub={res.totals.cube ? `가치 ${meso(res.totals.cube)}` : "개당 가치 미지정"} />
          </div>
          <h3 className="section-title">운</h3>
          <LuckCards res={res} />

          {res.daily.some((d) => d.starforce + d.potential + d.cube > 0) && (
            <section className="panel">
              <h3>날짜별 사용 메소</h3>
              <div className="chart">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={res.daily} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--border)" />
                    <YAxis tickFormatter={(v) => meso(v)} width={56} tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--border)" />
                    <Tooltip cursor={{ fill: "var(--hover)" }} formatter={(v: number, n: string) => [meso(v), n]}
                      contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="starforce" name="스타포스" stackId="a" fill="#d4a017" isAnimationActive={false} />
                    <Bar dataKey="potential" name="메소 재설정" stackId="a" fill="#3fa04a" isAnimationActive={false} />
                    <Bar dataKey="cube" name="큐브" stackId="a" fill="var(--accent)" isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          {Object.keys(res.unknown_levels).length > 0 && (
            <section className="panel warn">
              <h3>레벨을 모르는 장비 <small className="muted">스타포스 기록에는 장비 레벨이 없어 비용을 계산하지 못했습니다</small></h3>
              {Object.entries(res.unknown_levels).map(([n, c]) => (
                <div key={n} className="preset-row small">
                  <b style={{ width: "auto" }}>{n}</b><span className="muted">{c}회</span>
                  <span className="num-input" style={{ maxWidth: 160 }}>
                    <input type="number" min={0} max={300} placeholder="레벨" value={levels[n] ?? ""}
                      onChange={(e) => setLevels({ ...levels, [n]: Number(e.target.value) })} /><em>제</em>
                  </span>
                </div>
              ))}
              <button className="chip" type="button" onClick={async () => {
                await saveLedger({ item_levels: { ...settings.ledger.item_levels, ...levels } });
                run();
              }}>저장하고 다시 계산</button>
            </section>
          )}

          <section className="panel">
            <h3>장비별 <small className="muted">{res.items.length}개</small></h3>
            <div className="table-wrap">
              <table className="dense rec">
                <thead>
                  <tr><th>종류</th><th>캐릭터</th><th>장비</th><th>시도</th><th>결과</th><th>사용 메소</th><th>기간</th></tr>
                </thead>
                <tbody>
                  {res.items.map((it) => (
                    <tr key={`${it.kind}${it.character}${it.item}`}>
                      <td><span className={`kind ${it.kind === "cube" ? "buy" : it.kind}`}>{KIND_LABEL[it.kind]}</span></td>
                      <td>{it.character}</td>
                      <td className="item-col"><span className="with-icon"><ItemIcon name={it.item} size={24} />{it.item}</span></td>
                      <td>{num(it.attempts, 0)}</td>
                      <td className="item-col small">
                        {it.kind === "starforce"
                          ? <>{it.start_star}→{it.end_star}성 · 성공 {it.successes}{it.destroys > 0 && <span className="bad-text"> · 파괴 {it.destroys}</span>}</>
                          : <>등급 상승 {it.grade_ups}회{it.kind === "cube" && <span className="muted"> · {Object.entries(it.cube_types).map(([k, v]) => `${k} ${v}`).join(", ")}</span>}</>}
                      </td>
                      <td title={won(it.meso, w)}>{meso(it.meso)}{it.no_cost > 0 && <small className="muted"> (비용 제외 {it.no_cost}회)</small>}</td>
                      <td className="small muted">{it.first.slice(5, 10)}{it.last.slice(5, 10) !== it.first.slice(5, 10) && ` ~ ${it.last.slice(5, 10)}`}</td>
                    </tr>
                  ))}
                  {!res.items.length && <tr><td colSpan={7} className="muted center">기간 내 기록이 없습니다</td></tr>}
                </tbody>
              </table>
            </div>

            {res.sessions.length > 0 && (
              <More label={`스타포스 구간별 기대 비용 비교 (${res.sessions.length}개)`}>
                <div className="table-wrap">
                  <table className="dense rec">
                    <thead><tr><th>캐릭터</th><th>장비</th><th>구간</th><th>시도</th><th>파괴</th><th>실제</th><th>기대</th><th>차이</th></tr></thead>
                    <tbody>
                      {res.sessions.map((s, i) => {
                        const diff = s.actual != null && s.expected != null ? s.actual - s.expected : null;
                        return (
                          <tr key={i}>
                            <td>{s.character}</td><td className="item-col">{s.item}{s.level ? ` (${s.level}제)` : ""}</td>
                            <td>{s.start}→{s.end}성</td><td>{s.attempts}</td><td>{s.destroys}</td>
                            <td>{meso(s.actual)}</td><td>{meso(s.expected)}</td>
                            <td className={diff == null ? "" : diff <= 0 ? "ok" : "bad-text"}>{diff == null ? (s.end <= s.start ? "진행 없음" : "-") : `${diff > 0 ? "+" : ""}${meso(diff)}`}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </More>
            )}
          </section>

          {Object.keys(res.cube_counts).length > 0 && (
            <section className="panel">
              <h3>큐브 개당 가치 <small className="muted">이벤트·보상으로 얻은 큐브는 0으로 두고, 직접 산 큐브만 넣으세요</small></h3>
              <div className="grid2" style={{ maxWidth: 640 }}>
                {Object.entries(res.cube_counts).map(([t, c]) => (
                  <label key={t} className="num-input small">
                    <em style={{ minWidth: 200 }}>{t} ({c}개)</em>
                    <input type="number" min={0} step={10} value={cubePrice(t)} onChange={(e) => setPrices({ ...prices, [t]: Number(e.target.value) })} />
                    <em>만</em>
                  </label>
                ))}
              </div>
              <button className="chip" type="button" style={{ marginTop: 8 }} onClick={async () => {
                const cube_prices = { ...settings.ledger.cube_prices };
                for (const [k, v] of Object.entries(prices)) cube_prices[k] = v * MAN;
                await saveLedger({ cube_prices });
                run();
              }}>저장하고 다시 계산</button>
            </section>
          )}

          <section className="panel">
            <More label="계산 가정">
              <ul className="small muted">
                {res.assumptions.map((a) => <li key={a}>{a}</li>)}
                {res.superior > 0 && <li>슈페리얼 장비 강화 {res.superior}회는 비용·운 계산에서 제외했습니다.</li>}
              </ul>
            </More>
          </section>
        </>
      )}
    </div>
  );
}

function LuckCards({ res }: { res: Result }) {
  const { starforce_success: s, starforce_destroy: d, grade_up: g, starforce_cost: c } = res.luck;
  const diff = c.actual - c.expected;
  return (
    <div className="stats-row">
      <Stat label="스타포스 성공" value={<>{s.actual} <small>/ 기대 {num(s.expected, 1)}</small></>} sub={luckText(s, "more")} tone={luckTone(s, "more")} />
      <Stat label="스타포스 파괴" value={<>{d.actual} <small>/ 기대 {num(d.expected, 2)}</small></>} sub={d.expected > 0 ? luckText(d, "less") : "파괴 구간 시도 없음"} tone={d.expected > 0 ? luckTone(d, "less") : undefined} />
      <Stat label="잠재 등급 상승" value={<>{g.actual} <small>/ 기대 {num(g.expected, 1)}</small></>} sub={`${luckText(g, "more")} · ${num(g.attempts, 0)}회`} tone={luckTone(g, "more")} />
      <Stat label="스타포스 기대 비용 대비" value={c.sessions ? `${diff > 0 ? "+" : ""}${meso(diff)}` : "-"}
        sub={c.sessions ? `실제 ${meso(c.actual)} · 기대 ${meso(c.expected)} · ${c.sessions}구간` : "목표까지 올린 구간 없음"}
        tone={c.sessions ? (diff <= 0 ? "good" : "bad") : undefined} />
    </div>
  );
}
