import { useEffect, useState } from "react";
import { api, PRESET_KINDS, presetText, type HwansanRow, type Meta, type PresetChoice, type PresetInfo, type Settings } from "../api";
import { Grade, Icon, ItemIcon, More, Seg, Stat } from "../components/ui";
import { koUnit, num } from "../format";
import { HwansanTable } from "./Recommend";

type Line = { text: string; key: string; value: number };
export type Item = {
  slot: string;
  part: string | null;
  name: string;
  icon: string | null;
  level: number;
  starforce: number;
  starforce_scroll: boolean;
  potential_grade: string | null;
  potential: Line[];
  additional_grade: string | null;
  additional: Line[];
  boss_flame: boolean;
  craftable: boolean;
  flame_score: number | null;
  weapon_flame_rank: number | null;
  cuttable_count: number | null;
  hwansan?: number;
  hwansan_set?: number;
  next_steps: NextStep[];
};
export type NextStep = { tier: string; name: string | null; label: string; level: number; part: string; id: number | null };
export type CharacterData = {
  name: string;
  world: string;
  class: string;
  level: number;
  image: string | null;
  job_id: string | null;
  supported: boolean;
  stats: Record<string, string>;
  constant_check: { calculated: number; actual: number; error_pct: number | null } | null;
  items: Item[];
  set_effects: { name: string; count: number }[];
  hwansan: { table: HwansanRow[]; spec: Record<string, number>; warnings: string[] } | null;
  presets: PresetInfo;
};

type View = PresetInfo["view"];
const VIEW_LABEL: Record<View, string> = { boss: "보스용", farming: "재획용", current: "현재 착용" };
const NO_FLAME = new Set(["ring", "shoulder", "emblem", "secondary", "shield", "force_shield"]);

export const stepIcon = (st: NextStep) => (st.id ? `/api/icon/${st.id}` : null);

function eok(v: string | undefined) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "-";
  return n >= 1e8 ? `${(n / 1e8).toFixed(2)}억` : `${Math.round(n / 1e4).toLocaleString("ko-KR")}만`;
}

function flameText(it: Item) {
  if (it.part === "weapon") return it.weapon_flame_rank ? `공 ${it.weapon_flame_rank}추` : null;
  return it.part && !NO_FLAME.has(it.part) && it.flame_score ? `${num(it.flame_score, 0)}급` : null;
}

export function Character({ meta, settings, onSettings, onCraft }: {
  meta: Meta;
  settings: Settings;
  onSettings: (s: Settings) => void;
  onCraft: (item: Item, step?: NextStep | null) => void;
}) {
  const [name, setName] = useState(settings.characters[0] ?? "");
  const [data, setData] = useState<CharacterData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [view, setView] = useState<View>("boss");
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    api<{ has_key: boolean }>("/character/status").then((r) => setHasKey(r.has_key)).catch(() => setHasKey(false));
    // 첫 즐겨찾기 캐릭터를 캐시에서 바로 표시 (API 호출은 캐시가 없을 때만)
    if (settings.characters[0]) load(settings.characters[0]);
  }, []);

  const load = async (target: string, refresh = false, v: View = view) => {
    if (!target.trim()) return;
    setLoading(true);
    setError("");
    try {
      const d = await api<CharacterData>(`/character/${encodeURIComponent(target.trim())}?view=${v}${refresh ? "&refresh=true" : ""}`);
      setData(d);
      setName(d.name);
      setSel((s) => (s && d.items.some((it) => it.slot === s) ? s : null));
      if (!settings.characters.includes(d.name)) {
        onSettings(await api<Settings>("/settings", { method: "PUT", body: { ...settings, characters: [...settings.characters, d.name] } }));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const changeView = (v: View) => {
    setView(v);
    if (data) load(data.name, false, v);
  };

  const savePreset = async (kind: "boss" | "farming", c: PresetChoice | null) => {
    if (!data) return;
    const all = { ...settings.presets };
    const mine = { ...(all[data.name] ?? {}) };
    if (c) mine[kind] = c; else delete mine[kind];
    all[data.name] = mine;
    onSettings(await api<Settings>("/settings", { method: "PUT", body: { ...settings, presets: all } }));
    load(data.name);
  };

  const removeFav = async (n: string) =>
    onSettings(await api<Settings>("/settings", { method: "PUT", body: { ...settings, characters: settings.characters.filter((c) => c !== n) } }));

  const useJob = async () => {
    if (!data?.job_id) return;
    onSettings(await api<Settings>("/settings", { method: "PUT", body: { ...settings, job: data.job_id } }));
  };

  const s = data?.stats ?? {};
  const cc = data?.constant_check;
  const jobName = (id: string | null) => meta.jobs.find((j) => j.id === id)?.name ?? id;
  const selected = data?.items.find((it) => it.slot === sel) ?? null;
  const ccOk = cc && Math.abs(cc.error_pct ?? 99) < 0.1;

  return (
    <div className="character">
      <section className="panel toolbar-panel">
        <form className="char-search" onSubmit={(e) => { e.preventDefault(); load(name); }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="캐릭터 이름" />
          <button className="btn primary" type="submit" disabled={loading}>{loading ? "불러오는 중…" : "불러오기"}</button>
          {data && (
            <button type="button" className="icon-btn" title="최신으로 새로고침 (넥슨 API 다시 조회)" onClick={() => load(data.name, true)} disabled={loading}>
              <Icon name="refresh" size={16} />
            </button>
          )}
        </form>
        {settings.characters.length > 0 && (
          <div className="chips">
            {settings.characters.map((c) => (
              <span key={c} className={`chip ${data?.name === c ? "on" : ""}`}>
                <button type="button" className="chip-btn" onClick={() => load(c)}>{c}</button>
                <button type="button" className="chip-x" title="즐겨찾기에서 제거" onClick={() => removeFav(c)}>×</button>
              </span>
            ))}
          </div>
        )}
        {hasKey === false && <p className="error">넥슨 오픈 API 키가 없습니다. 프로젝트 폴더의 <code>.env</code> 에 <code>NEXON_API_KEY=...</code> 를 넣고 다시 실행하세요.</p>}
        {error && <p className="error">{error}</p>}
        <More>조회 결과는 이 PC에만 캐시되며(최대 30일), 새로고침을 누를 때만 다시 조회합니다. 게임 내 변경은 평균 15분 뒤 반영됩니다.</More>
      </section>

      {data && (
        <>
          <section className="panel hero">
            <div className="hero-avatar">{data.image ? <img src={data.image} alt="" /> : <Icon name="user" size={40} />}</div>
            <div className="hero-main">
              <h2>{data.name}</h2>
              <div className="chips">
                <span className="pill">Lv.{data.level}</span>
                <span className="pill">{data.class}</span>
                <span className="pill">{data.world}</span>
                {cc && <span className={`pill ${ccOk ? "good" : "bad"}`} title={`직업 상수 검증 오차 ${num(cc.error_pct, 4)}%`}>{ccOk ? "✓ 환산 검증" : "⚠ 환산 불일치"}</span>}
              </div>
              {!data.supported && <p className="error">아직 지원하지 않는 직업입니다 (지원: 아델·렌·나이트로드).</p>}
              {data.supported && data.job_id !== settings.job && (
                <button className="chip" onClick={useJob}>계산 기준 직업을 {jobName(data.job_id)}(으)로 변경</button>
              )}
            </div>
            <div className="hero-stats">
              <Stat label="전투력" value={koUnit(Number(s["전투력"] ?? 0))} sub={Number(s["전투력"] ?? 0).toLocaleString("ko-KR")} tone="accent" />
              <Stat label="최대 스탯공격력" value={eok(s["최대 스탯공격력"])} />
              <Stat label="보공 · 방무 · 크뎀" value={<>{num(Number(s["보스 몬스터 데미지"]), 0)} · {num(Number(s["방어율 무시"]), 1)} · {num(Number(s["크리티컬 데미지"]), 1)}</>} sub="%" />
            </div>
          </section>

          <section className="panel">
            <div className="toolbar">
              <Seg value={view} onChange={changeView} options={(["boss", "farming", "current"] as View[]).map((v) => [v, VIEW_LABEL[v]] as const)} />
              <div className="chips">{data.set_effects.map((st) => <span key={st.name} className="pill">{st.name} <b>{st.count}</b></span>)}</div>
            </div>
            {data.hwansan?.warnings.map((w) => <p key={w} className="error small">{w}</p>)}
            <More label={`프리셋 · ${presetText(view === "current" ? data.presets.current : data.presets.chosen[view as "boss" | "farming"])}`}>
              <p>지금 게임에서 착용 중: {presetText(data.presets.current)}.
                {data.presets.custom ? " 보스/재획 프리셋은 직접 지정한 값입니다." : " 보스/재획 프리셋은 잠재·어빌·하이퍼 옵션으로 자동 추정했습니다."}
                {" "}착용 중이 아닌 프리셋의 스탯은 현재 스탯에서 장비·세트·어빌·하이퍼 차이를 빼고 더해 추정합니다 (링크·유니온 프리셋 차이 미반영).
                위 전투력 등은 지금 착용 중인 프리셋 기준입니다.</p>
              {view !== "current" && data.hwansan && (
                <p><b>{VIEW_LABEL[view]} 추정:</b> 주스탯 {Math.round(data.hwansan.spec.main).toLocaleString("ko-KR")} · 공격력 {Math.round(data.hwansan.spec.att).toLocaleString("ko-KR")} ·
                  보공 {num(data.hwansan.spec.boss, 0)}% · 방무 {num(data.hwansan.spec.ied, 2)}% · 크뎀 {num(data.hwansan.spec.crit_dmg, 2)}%</p>
              )}
              <div className="preset-edit">
                {(["boss", "farming"] as const).map((kind) => (
                  <div key={kind} className="preset-row">
                    <b>{VIEW_LABEL[kind]}</b>
                    {PRESET_KINDS.map(([k, label]) => (
                      <label key={k} className="small">{label}{" "}
                        <select value={data.presets.chosen[kind][k]}
                          onChange={(e) => savePreset(kind, { ...data.presets.chosen[kind], [k]: Number(e.target.value) })}>
                          {[1, 2, 3].map((n) => <option key={n} value={n}>{n}{n === data.presets.current[k] ? " (착용 중)" : ""}</option>)}
                        </select>
                      </label>
                    ))}
                    {settings.presets[data.name]?.[kind] && <button type="button" className="link" onClick={() => savePreset(kind, null)}>자동 추정으로</button>}
                  </div>
                ))}
              </div>
            </More>
          </section>

          <div className="equip-layout">
            <section className="panel">
              <h3>{VIEW_LABEL[view]} 장비 <small className="muted">{data.items.length}개 · 눌러서 자세히</small></h3>
              <div className="equip-grid">
                {data.items.map((it) => (
                  <button key={it.slot} type="button" className={`tile ${sel === it.slot ? "on" : ""}`} onClick={() => setSel(it.slot)}>
                    <ItemIcon src={it.icon} name={it.name} grade={it.potential_grade} star={it.starforce} size={44} />
                    <span className="tile-body">
                      <small className="muted">{it.slot}</small>
                      <b>{it.name}</b>
                      <span className="tile-tags">
                        <Grade g={it.potential_grade} />
                        {it.additional_grade && <Grade g={it.additional_grade} />}
                        {it.next_steps.length > 0 && <span className="up" title="다음 단계 장비 있음"><Icon name="up" size={12} /></span>}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <aside className="panel detail">
              {selected ? <ItemDetail it={selected} onCraft={onCraft} flameNote={`추옵 급수 = 주스탯 + 부스탯×${settings.flame_coef.sub} + 공×${settings.flame_coef.att} + 올%×${settings.flame_coef.all_pct}`} />
                : <div className="muted center detail-empty"><Icon name="box" size={28} /><p>장비를 누르면 옵션과<br />다음 단계 장비가 보여요</p></div>}
            </aside>
          </div>

          {data.hwansan && (
            <section className="panel">
              <More label="현재 스펙 환산표 (1단위 → 환산 주스탯)"><HwansanTable rows={data.hwansan.table} /></More>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function ItemDetail({ it, onCraft, flameNote }: { it: Item; onCraft: (item: Item, step?: NextStep | null) => void; flameNote: string }) {
  const flame = flameText(it);
  return (
    <div className="item-detail">
      <div className="detail-head">
        <ItemIcon src={it.icon} name={it.name} grade={it.potential_grade} size={56} />
        <div>
          <small className="muted">{it.slot} · {it.level}제{it.boss_flame ? " · 보스추옵" : ""}</small>
          <h3>{it.name}</h3>
          <div className="chips">
            {it.starforce > 0 && <span className="pill star">★ {it.starforce}{it.starforce_scroll ? " 놀장" : ""}</span>}
            {flame && <span className="pill" title={flameNote}>추옵 {flame}</span>}
            {it.cuttable_count != null && it.cuttable_count !== 255 && <span className="pill">가위 {it.cuttable_count}</span>}
          </div>
        </div>
      </div>
      <div className="lines">
        <div><span className="muted small">잠재</span> <Grade g={it.potential_grade} />
          {it.potential.length ? <ul>{it.potential.map((l, i) => <li key={i}>{l.text}</li>)}</ul> : <p className="muted small">없음</p>}</div>
        <div><span className="muted small">에디</span> <Grade g={it.additional_grade} />
          {it.additional.length ? <ul>{it.additional.map((l, i) => <li key={i}>{l.text}</li>)}</ul> : <p className="muted small">없음</p>}</div>
      </div>
      {it.hwansan != null && (
        <Stat label="환산 기여" value={num(it.hwansan, 0)} sub={it.hwansan_set ? `세트 효과 ${num(it.hwansan_set, 0)} 포함 · 이 장비를 뺐을 때 잃는 환산` : "이 장비를 뺐을 때 잃는 환산 주스탯"} />
      )}
      {it.part && (it.craftable ? (
        <>
          <button className="btn primary block" onClick={() => onCraft(it)}><Icon name="hammer" size={16} /> 이 장비 직작 계산</button>
          {it.next_steps.length > 0 && (
            <>
              <h4>다음 단계 <small className="muted">노작부터 직작, 지금 장비는 판매</small></h4>
              <div className="next-list">
                {it.next_steps.map((st) => (
                  <button key={st.label} type="button" className="next-card" onClick={() => onCraft(it, st)}>
                    <ItemIcon src={stepIcon(st)} name={st.name ?? st.label} size={36} />
                    <span><small className="muted">{st.tier} · {st.level}제</small><b>{st.label}</b></span>
                    <Icon name="arrow" size={16} />
                  </button>
                ))}
              </div>
            </>
          )}
        </>
      ) : <p className="muted small">강화할 수 없는 장비입니다</p>)}
    </div>
  );
}
