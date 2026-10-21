import { useEffect, useMemo, useState } from "react";
import { api, type Histogram as H, type Meta, type Percentiles, type Preset, type Settings } from "../api";
import { Histogram } from "../components/Histogram";
import { Grade, ItemIcon, More, Stat } from "../components/ui";
import { eokToMeso, meso, num, pct, won } from "../format";
import { stepIcon, type CharacterData, type Item, type NextStep } from "./Character";

const TEMPLATES = [
  { label: "직접 입력", part: "", level: 0, boss: true },
  { label: "에테르넬 모자 (250)", part: "hat", level: 250, boss: true },
  { label: "에테르넬 상의 (250)", part: "top", level: 250, boss: true },
  { label: "에테르넬 하의 (250)", part: "bottom", level: 250, boss: true },
  { label: "에테르넬 어깨 (250)", part: "shoulder", level: 250, boss: true },
  { label: "아케인셰이드 신발 (200)", part: "shoes", level: 200, boss: true },
  { label: "아케인셰이드 장갑 (200)", part: "gloves", level: 200, boss: true },
  { label: "아케인셰이드 망토 (200)", part: "cape", level: 200, boss: true },
  { label: "칠흑 몽환의 벨트 (200)", part: "belt", level: 200, boss: true },
  { label: "칠흑 거대한 공포 (200)", part: "ring", level: 200, boss: true },
  { label: "칠흑 커맨더 포스 이어링 (200)", part: "earring", level: 200, boss: true },
  { label: "칠흑 고통의 근원 (160)", part: "pendant", level: 160, boss: true },
  { label: "칠흑 루즈 컨트롤 머신 마크 (160)", part: "face", level: 160, boss: true },
  { label: "칠흑 마력이 깃든 안대 (160)", part: "eye", level: 160, boss: true },
];

const MVP_NAMES: Record<string, string> = {
  none: "없음", bronze: "브론즈", silver: "실버", gold: "골드", diamond: "다이아", red: "레드", black: "블랙",
};

const NO_FLAME = new Set(["ring", "shoulder", "emblem", "secondary", "shield", "force_shield"]);

export type Prefill = {
  nonce: number;
  label: string;
  itemName: string;
  part: string;
  level: number;
  boss: boolean;
  star: number;
  potentialGrade: string | null;
  additionalGrade: string | null;
  // 다음 단계 장비: 새 노작을 사서 직작하고, 지금 장비(sell)는 판다
  next?: boolean;
  sell?: { name: string; star: number; grade: string | null } | null;
  icon?: string | null;
};

/** 장착 장비(또는 그 다음 단계 장비)로 직작 계산기 입력 만들기 */
export function prefillFromItem(it: Item, step?: NextStep | null): Prefill {
  if (!step) {
    return {
      nonce: Date.now(), label: it.name, itemName: it.name, part: it.part!, level: it.level, boss: it.boss_flame,
      star: it.starforce, potentialGrade: it.potential_grade, additionalGrade: it.additional_grade, icon: it.icon,
    };
  }
  return {
    nonce: Date.now(), label: `${step.label} (${step.level}제)`, itemName: step.name ?? "", part: step.part,
    level: step.level, boss: true, star: 0, potentialGrade: "rare", additionalGrade: "rare", next: true,
    sell: { name: it.name, star: it.starforce, grade: it.potential_grade }, icon: stepIcon(step),
  };
}

type StageResult = { percentiles: Percentiles; warnings?: string[] } & Record<string, any>;
type PlanResult = {
  compare: {
    base_price: number;
    craft_expected: number;
    breakeven_price: number;
    cumulative_breakeven: { name: string; expected: number; cumulative: number }[];
    market_price: number | null;
    resale_net: number;
    market_net: number | null;
    expected_profit: number | null;
    loss_probability: number | null;
    percentiles: Percentiles;
    histogram: H;
  };
  details: Record<string, StageResult>;
};

function NumInput({ value, onChange, step = 1, min, max, suffix, width }: {
  value: number | ""; onChange: (v: number | "") => void; step?: number; min?: number; max?: number;
  suffix?: string; width?: number;
}) {
  return (
    <span className="num-input" style={width ? { width } : undefined}>
      <input type="number" value={value} step={step} min={min} max={max}
             onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
      {suffix && <em>{suffix}</em>}
    </span>
  );
}

export function Craft({ meta, settings, prefill }: { meta: Meta; settings: Settings; prefill?: Prefill | null }) {
  const [tpl, setTpl] = useState(1);
  const [part, setPart] = useState("hat");
  const [level, setLevel] = useState(250);
  const [boss, setBoss] = useState(true);
  const [basePrice, setBasePrice] = useState<number | "">(0);
  const [baseOther, setBaseOther] = useState(false);
  const [marketPrice, setMarketPrice] = useState<number | "">("");
  const [marketOther, setMarketOther] = useState(false);
  const [itemName, setItemName] = useState("");
  const [resale, setResale] = useState<number | "">(0);
  const [marketMsg, setMarketMsg] = useState("");

  const [useSf, setUseSf] = useState(true);
  const [sfStart, setSfStart] = useState(0);
  const [sfTarget, setSfTarget] = useState(22);
  const [spare, setSpare] = useState<number | "">(0);
  const [recovery, setRecovery] = useState<"basic" | "restore" | "optimize">("optimize");
  const [safeguard, setSafeguard] = useState<number[]>([]);

  const [usePot, setUsePot] = useState(true);
  const [potGrade, setPotGrade] = useState("rare");
  const [potPreset, setPotPreset] = useState("");
  const [potPresets, setPotPresets] = useState<Preset[]>([]);
  const [potPity, setPotPity] = useState<number | "">(0);

  const [useAdd, setUseAdd] = useState(false);
  const [addGrade, setAddGrade] = useState("rare");
  const [addPreset, setAddPreset] = useState("");
  const [addPresets, setAddPresets] = useState<Preset[]>([]);
  const [addPity, setAddPity] = useState<number | "">(0);

  const [useFlame, setUseFlame] = useState(true);
  const [flameMethod, setFlameMethod] = useState("meso_reset");
  const [flameItemPrice, setFlameItemPrice] = useState<number | "">("");
  const [flameThreshold, setFlameThreshold] = useState<number | "">(150);
  const [flameAttTier, setFlameAttTier] = useState(6);

  // 이벤트 아이템 (설정의 보유 개수가 있으면 기본 사용)
  const tix = settings.tickets;
  const [useStar17, setUseStar17] = useState(tix.star17 > 0);
  const [useUniqueScroll, setUseUniqueScroll] = useState(tix.unique_potential > 0);
  const [useEpicScroll, setUseEpicScroll] = useState(tix.epic_additional > 0);
  useEffect(() => {
    setUseStar17(tix.star17 > 0);
    setUseUniqueScroll(tix.unique_potential > 0);
    setUseEpicScroll(tix.epic_additional > 0);
  }, [tix.star17, tix.unique_potential, tix.epic_additional]);
  const RANK = ["rare", "epic", "unique", "legendary"];
  const star17Ok = sfStart < 17 && sfTarget >= 17 && level <= tix.star17_max_level;
  const effStart = useStar17 && star17Ok ? 17 : sfStart;
  const effPotGrade = useUniqueScroll && RANK.indexOf(potGrade) < 2 ? "unique" : potGrade;
  const effAddGrade = useEpicScroll && RANK.indexOf(addGrade) < 1 ? "epic" : addGrade;

  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const maxStar = useMemo(() => {
    let m = 0;
    for (const r of meta.starforce.max_star_by_level) if (level >= r.min_level) m = r.max_star;
    return m;
  }, [level, meta]);
  const isWeapon = part === "weapon";
  const flameAllowed = !NO_FLAME.has(part);
  const wpe = settings.won_per_eok;

  useEffect(() => {
    if (sfTarget > maxStar) setSfTarget(maxStar);
  }, [maxStar, sfTarget]);

  useEffect(() => {
    const load = async (kind: string, set: (p: Preset[]) => void, setSel: (s: string) => void) => {
      const ps = await api<Preset[]>(`/potential/presets?job=${settings.job}&part=${part}&kind=${kind}&level=${level}`);
      set(ps);
      setSel(ps[0]?.id ?? "");
    };
    load("potential", setPotPresets, setPotPreset).catch(() => setPotPresets([]));
    load("additional", setAddPresets, setAddPreset).catch(() => setAddPresets([]));
  }, [part, level, settings.job]);

  const [fromItem, setFromItem] = useState("");
  const [fromIcon, setFromIcon] = useState<string | null>(null);
  const [sell, setSell] = useState<Prefill["sell"]>(null);
  const applyPrefill = (p: Prefill) => {
    setTpl(0);
    setPart(p.part);
    setLevel(p.level);
    setBoss(p.boss);
    setSfStart(p.star);
    // 이미 22성 이상이면 스타포스 단계는 기본 제외 (필요하면 목표를 올려 다시 켠다)
    setUseSf(p.star < 22);
    setSfTarget(Math.max(22, p.star));
    setPotGrade(p.potentialGrade ?? "rare");
    setAddGrade(p.additionalGrade ?? "rare");
    setUseAdd(true);
    setFromItem(p.label);
    setFromIcon(p.icon ?? null);
    setItemName(p.itemName);
    setSell(p.sell ?? null);
    setBasePrice(p.next ? "" : 0);  // 내 장비 직작 = 베이스 구매 없음, 다음 단계 = 노작 구매가 입력
    setResale(0);
    setMarketPrice("");
    setMarketMsg(p.next ? `노작을 사서 직작하고 지금 장비(${p.sell?.name})는 판다고 계산합니다. 노작 구매가와 되팔기 금액을 넣거나 시세 기록에서 채우세요.` : "");
    setResult(null);
  };
  useEffect(() => {
    if (prefill) applyPrefill(prefill);
  }, [prefill?.nonce]);

  // 직작 계산기 안에서 바로 내 캐릭터 장비 / 다음 단계 불러오기
  const [charName, setCharName] = useState(settings.characters[0] ?? "");
  const [charData, setCharData] = useState<CharacterData | null>(null);
  const [pick, setPick] = useState<number | null>(null);
  const [charMsg, setCharMsg] = useState("");
  useEffect(() => {
    if (!charName) return;
    setCharMsg("불러오는 중…");
    api<CharacterData>(`/character/${encodeURIComponent(charName)}?view=boss`)
      .then((d) => { setCharData(d); setPick(null); setCharMsg(""); })
      .catch((e) => { setCharData(null); setCharMsg((e as Error).message); });
  }, [charName]);
  const pickable = (charData?.items ?? []).filter((it) => it.part && it.craftable);
  const picked = pick == null ? null : pickable[pick] ?? null;

  const applyTemplate = (i: number) => {
    setTpl(i);
    const t = TEMPLATES[i];
    if (t.part) {
      setPart(t.part);
      setLevel(t.level);
      setBoss(t.boss);
    }
  };

  const toggleSg = (s: number) =>
    setSafeguard((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const run = async () => {
    setLoading(true);
    setError("");
    const ev = settings.events;
    const body: Record<string, unknown> = {
      base_price: eokToMeso(Number(basePrice) || 0),
      base_other_world: baseOther,
      market_price: marketPrice === "" ? null : eokToMeso(Number(marketPrice)),
      market_other_world: marketOther,
      resale_price: eokToMeso(Number(resale) || 0),
    };
    if (useSf && sfTarget > effStart) {
      body.starforce = {
        level, start: effStart, target: sfTarget, mvp: settings.mvp, pc_room: settings.pc_room,
        mvp_max_star: settings.mvp_max_star,
        events: {
          discount30: ev.discount30, destroy_reduction: ev.destroy_reduction,
          guaranteed_5_10_15: ev.guaranteed_5_10_15, plus_one: ev.plus_one, recovery_discount: ev.recovery_discount,
        },
        safeguard: recovery === "optimize" ? [] : safeguard,
        recovery: recovery === "restore"
          ? Object.fromEntries(Array.from({ length: 30 }, (_, s) => [s, "restore"]))
          : {},
        spare_price: eokToMeso(Number(spare) || 0),
        optimize: recovery === "optimize",
      };
    }
    const potBody = (grade: string, preset: string, pity: number | "") => ({
      part, level, current: grade, job: settings.job, preset_id: preset || null, miracle: ev.miracle,
      pity_used: grade === "unique" ? { unique: Number(pity) || 0 } : {},
    });
    if (usePot && potPreset) body.potential = potBody(effPotGrade, potPreset, potPity);
    if (useAdd && addPreset) body.additional = potBody(effAddGrade, addPreset, addPity);
    if (useFlame && flameAllowed) {
      body.flame = {
        item_type: isWeapon ? "weapon" : "armor", level, boss, method: flameMethod, job: settings.job,
        item_price: flameItemPrice === "" ? null : eokToMeso(Number(flameItemPrice)),
        coef: settings.flame_coef,
        threshold: isWeapon ? null : Number(flameThreshold) || 0,
        requirements: isWeapon ? { ATT: flameAttTier } : {},
      };
    }
    try {
      setResult(await api<PlanResult>("/craft/plan", { body }));
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  type Est = { price: number; n: number; low: number; high: number; recent_only: boolean } | null;
  const fetchMarket = async () => {
    if (!itemName.trim()) { setMarketMsg("아이템명을 입력하세요"); return; }
    const q = (o: Record<string, string | number | boolean>) => new URLSearchParams(Object.entries(o).map(([k, v]) => [k, String(v)])).toString();
    const name = itemName.trim();
    const target = useSf ? sfTarget : sfStart;
    // 팔 장비: 다음 단계면 지금 장착 장비, 내 장비 직작이면 그 장비 자체
    const own = fromItem && !sell;
    const sellQ = sell ? { item_name: sell.name, star: sell.star, grade: sell.grade ?? "", sell: true }
      : { item_name: name, star: sfStart, grade: potGrade, sell: true };
    const [fin, base, mine] = await Promise.all([
      api<Est>(`/market/estimate?${q({ item_name: name, star: target, grade: usePot ? "legendary" : potGrade })}`),
      api<Est>(`/market/estimate?${q({ item_name: name, base: true })}`),
      fromItem ? api<Est>(`/market/estimate?${q(sellQ)}`) : Promise.resolve(null),
    ]);
    const msgs: string[] = [];
    const eok = (v: number) => Math.round((v / 1e8) * 100) / 100;
    if (fin) { setMarketPrice(eok(fin.price)); setMarketOther(false); msgs.push(`완제품 ${fin.n}건 중앙값 ${meso(fin.price)}`); }
    else msgs.push("완제품: 비슷한 매물 기록 없음");
    if (!own) {
      if (base) { setBasePrice(eok(base.price)); setBaseOther(false); msgs.push(`노작 ${base.n}건 중앙값 ${meso(base.price)}`); }
      else msgs.push("노작: 기록 없음");
    }
    if (fromItem) {
      // 지금 장비를 직작하는 경우: 완제품을 사면 지금 장비를 팔 수 있음 (등록가 기준, 실구매가에서 타서버 10% 제외)
      if (mine) { setResale(eok(mine.price)); msgs.push(`기존 장비${sell ? `(${sell.name})` : ""} ${mine.n}건 중앙값 ${meso(mine.price)} (되팔기)`); }
      else msgs.push(`기존 장비${sell ? `(${sell.name})` : ""}: 기록 없음`);
    }
    setMarketMsg(msgs.join(" · ") + " — 시세 기록 탭 데이터 (최근 30일 우선)");
  };

  const c = result?.compare;
  const warnings = result ? Object.values(result.details).flatMap((d) => d.warnings ?? []) : [];

  return (
    <div className="craft">
      <section className="panel form">
        <div className="detail-head">
          <ItemIcon src={fromIcon} name={itemName || null} size={48} />
          <div>
            <small className="muted">계산할 아이템</small>
            <h2>{fromItem || "직접 입력"}</h2>
          </div>
        </div>
        {settings.characters.length > 0 && (
          <fieldset className="loader">
            <legend className="small">내 캐릭터 장비에서 불러오기</legend>
            <select value={charName} onChange={(e) => setCharName(e.target.value)}>
              {settings.characters.map((c) => <option key={c} value={c}>{c} (보스용 프리셋)</option>)}
            </select>
            <div className="mini-grid">
              {pickable.map((it, i) => (
                <button key={it.slot} type="button" className={`mini ${pick === i ? "on" : ""}`} title={`${it.slot} · ${it.name}${it.starforce ? ` ${it.starforce}성` : ""}`}
                  onClick={() => { setPick(i); applyPrefill(prefillFromItem(it)); }}>
                  <ItemIcon src={it.icon} name={it.name} star={it.starforce} grade={it.potential_grade} size={36} />
                  {it.next_steps.length > 0 && <span className="dot" />}
                </button>
              ))}
            </div>
            {picked && (
              <div className="picked">
                <small className="muted">{picked.slot} · {picked.name} <Grade g={picked.potential_grade} /></small>
                {picked.next_steps.length > 0 && (
                  <div className="next-list">
                    {picked.next_steps.map((st) => (
                      <button key={st.label} type="button" className={`next-card ${fromItem.startsWith(st.label) ? "on" : ""}`}
                        onClick={() => applyPrefill(prefillFromItem(picked, st))}>
                        <ItemIcon src={stepIcon(st)} name={st.name ?? st.label} size={30} />
                        <span><small className="muted">다음 단계 · {st.level}제</small><b>{st.label}</b></span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {charMsg && <p className="muted small">{charMsg}</p>}
          </fieldset>
        )}
        <label className="row">
          <span>템플릿</span>
          <select value={tpl} onChange={(e) => applyTemplate(Number(e.target.value))}>
            {TEMPLATES.map((t, i) => <option key={t.label} value={i}>{t.label}</option>)}
          </select>
        </label>
        <div className="grid2">
          <label className="row">
            <span>부위</span>
            <select value={part} onChange={(e) => { setPart(e.target.value); setTpl(0); }}>
              {meta.parts.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="row">
            <span>착용 레벨</span>
            <NumInput value={level} onChange={(v) => { setLevel(Number(v) || 0); setTpl(0); }} min={0} max={300} />
          </label>
        </div>
        <label className="check">
          <input type="checkbox" checked={boss} onChange={(e) => setBoss(e.target.checked)} />
          보스 장비 판정 (추옵 4줄·단계 +2)
        </label>
        <div className="grid2">
          <label className="row">
            <span>베이스 구매가</span>
            <NumInput value={basePrice} onChange={setBasePrice} step={0.1} min={0} suffix="억" />
          </label>
          <label className="check small">
            <input type="checkbox" checked={baseOther} onChange={(e) => setBaseOther(e.target.checked)} />
            타서버 매물 (+10%)
          </label>
          <label className="row">
            <span>완제품 시세</span>
            <NumInput value={marketPrice} onChange={setMarketPrice} step={1} min={0} suffix="억" />
          </label>
          <label className="check small">
            <input type="checkbox" checked={marketOther} onChange={(e) => setMarketOther(e.target.checked)} />
            타서버 매물 (+10%)
          </label>
          <label className="row">
            <span>구매 시 기존 장비 되팔기</span>
            <NumInput value={resale} onChange={setResale} step={0.1} min={0} suffix="억 (등록가)" />
          </label>
        </div>
        <More>지금 내 장비를 직작하는 경우(또는 다음 단계로 바꾸는 경우), 완제품을 사면 지금 장비를 팔 수 있어 구매 비용에서 차감합니다
          (수수료 {settings.mvp !== "none" && settings.mvp !== "bronze" || settings.pc_room ? "3" : "5"}%). 다음 단계는 노작을 사서 직작하고 지금 장비는 판다고 계산합니다.</More>
        <div className="grid2">
          <label className="row">
            <span>아이템명 (시세 조회용)</span>
            <input value={itemName} onChange={(e) => setItemName(e.target.value)} placeholder="에테르넬 나이트헬름" />
          </label>
          <button type="button" className="chip" style={{ alignSelf: "end", marginBottom: 10 }} onClick={() => fetchMarket().catch((e) => setMarketMsg(e.message))}>시세 기록에서 가격 채우기</button>
        </div>
        {marketMsg && <p className="muted small">{marketMsg}</p>}

        <fieldset className={useSf ? "" : "off"}>
          <legend>
            <label className="check"><input type="checkbox" checked={useSf} onChange={(e) => setUseSf(e.target.checked)} />스타포스</label>
          </legend>
          <div className="grid2">
            <label className="row"><span>현재 성</span>
              <NumInput value={sfStart} onChange={(v) => setSfStart(Math.min(Number(v) || 0, maxStar - 1))} min={0} max={maxStar - 1} suffix="성" />
            </label>
            <label className="row"><span>목표 성</span>
              <NumInput value={sfTarget} onChange={(v) => setSfTarget(Math.min(Number(v) || 0, maxStar))} min={1} max={maxStar} suffix={`성 / 최대 ${maxStar}`} />
            </label>
          </div>
          <label className={`check small ticket ${star17Ok ? "" : "dim"}`}>
            <input type="checkbox" checked={useStar17} onChange={(e) => setUseStar17(e.target.checked)} />
            17성 강화권 사용 {useStar17 && star17Ok ? `→ ${sfStart}성 대신 17성부터` : star17Ok ? "" : `(17성 미만·목표 17성 이상·${tix.star17_max_level}제 이하일 때)`}
            {tix.star17 > 0 && <span className="pill">보유 {tix.star17}</span>}
          </label>
          <label className="row"><span>스페어(노작) 시세</span>
            <NumInput value={spare} onChange={setSpare} step={0.1} min={0} suffix="억" />
          </label>
          <label className="row"><span>파괴 대응</span>
            <select value={recovery} onChange={(e) => setRecovery(e.target.value as typeof recovery)}>
              <option value="optimize">자동 최적화 (파방·복구 방식)</option>
              <option value="basic">기본 복구 (스페어 1개 → 12성)</option>
              <option value="restore">확정 복구 (직전 성급, 스페어 N개 + 메소)</option>
            </select>
          </label>
          {recovery !== "optimize" && (
            <div className="row"><span>파괴방지</span>
              <div className="chips">
                {meta.starforce.safeguard_stars.map((s) => (
                  <button key={s} type="button" className={safeguard.includes(s) ? "chip on" : "chip"} onClick={() => toggleSg(s)}>
                    {s}→{s + 1}
                  </button>
                ))}
              </div>
            </div>
          )}
        </fieldset>

        {(["pot", "add"] as const).map((k) => {
          const isPot = k === "pot";
          const on = isPot ? usePot : useAdd;
          const presets = isPot ? potPresets : addPresets;
          return (
            <fieldset key={k} className={on ? "" : "off"}>
              <legend>
                <label className="check">
                  <input type="checkbox" checked={on} onChange={(e) => (isPot ? setUsePot : setUseAdd)(e.target.checked)} />
                  {isPot ? "잠재능력 (메소 재설정)" : "에디셔널 (메소 재설정)"}
                </label>
              </legend>
              <div className="grid2">
                <label className="row"><span>현재 등급</span>
                  <select value={isPot ? potGrade : addGrade} onChange={(e) => (isPot ? setPotGrade : setAddGrade)(e.target.value)}>
                    {meta.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                </label>
                <label className="row"><span>목표 옵션</span>
                  <select value={isPot ? potPreset : addPreset} onChange={(e) => (isPot ? setPotPreset : setAddPreset)(e.target.value)}>
                    {presets.length === 0 && <option value="">(이 부위 프리셋 없음)</option>}
                    {presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                  </select>
                </label>
              </div>
              {(() => {
                const use = isPot ? useUniqueScroll : useEpicScroll;
                const cur = isPot ? potGrade : addGrade;
                const to = isPot ? "unique" : "epic";
                const ok = RANK.indexOf(cur) < RANK.indexOf(to);
                const own = isPot ? tix.unique_potential : tix.epic_additional;
                return (
                  <label className={`check small ticket ${ok ? "" : "dim"}`}>
                    <input type="checkbox" checked={use} onChange={(e) => (isPot ? setUseUniqueScroll : setUseEpicScroll)(e.target.checked)} />
                    {isPot ? "유니크 잠재 주문서 사용" : "에픽 에디 주문서 사용"} {use && ok ? `→ ${isPot ? "유니크" : "에픽"}부터` : ok ? "" : "(이미 그 등급 이상)"}
                    {own > 0 && <span className="pill">보유 {own}</span>}
                  </label>
                );
              })()}
              {(isPot ? effPotGrade : effAddGrade) === "unique" && (
                <label className="row"><span>유→레 천장 진행</span>
                  <NumInput value={isPot ? potPity : addPity} onChange={isPot ? setPotPity : setAddPity} min={0} suffix="회 사용" />
                </label>
              )}
            </fieldset>
          );
        })}

        <fieldset className={useFlame && flameAllowed ? "" : "off"}>
          <legend>
            <label className="check">
              <input type="checkbox" checked={useFlame && flameAllowed} disabled={!flameAllowed}
                     onChange={(e) => setUseFlame(e.target.checked)} />
              추가옵션 {flameAllowed ? "" : "(이 부위는 추옵 없음)"}
            </label>
          </legend>
          <label className="row"><span>수단</span>
            <select value={flameMethod} onChange={(e) => setFlameMethod(e.target.value)}>
              {meta.flame_methods.map((m) => <option key={m.id} value={m.id}>{m.label}{m.meso ? " (300만)" : ""}</option>)}
            </select>
          </label>
          {!meta.flame_methods.find((m) => m.id === flameMethod)?.meso && (
            <label className="row"><span>불꽃 1개 가치</span>
              <NumInput value={flameItemPrice} onChange={setFlameItemPrice} step={0.01} min={0} suffix="억" />
            </label>
          )}
          {isWeapon ? (
            <label className="row"><span>목표</span>
              <select value={flameAttTier} onChange={(e) => setFlameAttTier(Number(e.target.value))}>
                <option value={7}>공격력 1추 (7단계)</option>
                <option value={6}>공격력 2추 이상 (6단계+)</option>
                <option value={5}>공격력 3추 이상 (5단계+)</option>
              </select>
            </label>
          ) : (
            <label className="row"><span>목표 급수</span>
              <NumInput value={flameThreshold} onChange={setFlameThreshold} step={10} min={0} suffix="급 이상" />
            </label>
          )}
        </fieldset>

        <button className="btn primary block" onClick={run} disabled={loading}>{loading ? "계산 중…" : "계산"}</button>
        {error && <p className="error">{error}</p>}
      </section>

      <section className="results">
        {!c && !error && (
          <div className="panel empty">
            <p>왼쪽에서 아이템과 직작 단계를 고른 뒤 <b>계산</b>을 누르세요.</p>
            <p className="muted">현재 설정: {meta.jobs.find((j) => j.id === settings.job)?.name} · MVP {MVP_NAMES[settings.mvp] ?? settings.mvp} ·
              {Object.entries(settings.events).filter(([, v]) => v).length ? " 이벤트 적용 중" : " 이벤트 없음"}</p>
          </div>
        )}
        {c && (
          <>
            <div className="stats-row">
              <Stat label="직작 기대 비용" value={meso(c.base_price + c.craft_expected)} icon="hammer"
                sub={`베이스 ${meso(c.base_price)} + 강화 ${meso(c.craft_expected)} ${won(c.base_price + c.craft_expected, wpe)}`} />
              <Stat label="손익분기 시세" value={meso(c.breakeven_price)} sub="완제품이 이보다 비싸면 직작 이득" tone="accent" />
              {c.market_price != null && (
                <>
                  <Stat label={`기대 ${c.expected_profit! >= 0 ? "이득" : "손해"} (직작 기준)`} value={meso(Math.abs(c.expected_profit!))}
                    tone={c.expected_profit! >= 0 ? "good" : "bad"}
                    sub={`완제품 ${meso(c.market_price)}${c.resale_net > 0 ? ` − 되팔기 ${meso(c.resale_net)} = ${meso(c.market_net)}` : ""} ${won(Math.abs(c.expected_profit!), wpe)}`} />
                  <Stat label="직작이 손해일 확률" value={pct(c.loss_probability, 1)} tone={c.loss_probability! <= 0.5 ? "good" : "bad"}
                    sub={`직작 총비용 > 구매 실비용${c.resale_net > 0 ? " (되팔기 차감 후)" : ""}`} />
                </>
              )}
            </div>

            <div className="panel">
              <h3>직작 총비용 분포 <small className="muted">(베이스 포함, 상위 1% 절단)</small></h3>
              <Histogram data={c.histogram} markers={[
                { value: c.breakeven_price, label: "기대값", color: "var(--accent-2)" },
                ...(c.market_net != null ? [{ value: c.market_net, label: c.resale_net > 0 ? "구매(되팔기 후)" : "완제품", color: "var(--bad)" }] : []),
              ]} />
              <table className="pct">
                <thead><tr><th>운</th>{["p50", "p75", "p90", "p95", "p99"].map((p) => <th key={p}>상위 {100 - Number(p.slice(1))}%</th>)}</tr></thead>
                <tbody><tr><td>총비용</td>{["p50", "p75", "p90", "p95", "p99"].map((p) => <td key={p}>{meso(c.percentiles[p])}</td>)}</tr></tbody>
              </table>
              <More>예: "상위 10%" 칸은 100번 중 90번은 이 금액 이하로 끝난다는 뜻입니다.</More>
            </div>

            <div className="panel">
              <h3>단계별 손익분기 (누적)</h3>
              <table>
                <thead><tr><th>단계</th><th>기대 비용</th><th>누적 (베이스 포함)</th><th>중앙값</th><th>상위 10%</th></tr></thead>
                <tbody>
                  <tr><td>베이스</td><td>{meso(c.base_price)}</td><td>{meso(c.base_price)}</td><td /><td /></tr>
                  {c.cumulative_breakeven.map((s) => {
                    const key = { 스타포스: "starforce", 잠재능력: "potential", 에디셔널: "additional", 추가옵션: "flame" }[s.name]!;
                    const d = result!.details[key];
                    const p = d.distribution?.percentiles ?? d.percentiles;
                    return (
                      <tr key={s.name}>
                        <td>{s.name}</td><td>{meso(s.expected)}</td><td>{meso(s.cumulative)}</td>
                        <td>{meso(p?.p50)}</td><td>{meso(p?.p90)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {result!.details.starforce && <StarforceDetail d={result!.details.starforce} />}
            {result!.details.potential && <PotentialDetail title="잠재능력" d={result!.details.potential} />}
            {result!.details.additional && <PotentialDetail title="에디셔널" d={result!.details.additional} />}
            {result!.details.flame && <FlameDetail d={result!.details.flame} />}

            {warnings.length > 0 && (
              <div className="panel warn">
                <h3>⚠ 계산 가정</h3>
                <ul>{[...new Set(warnings)].map((w) => <li key={w}>{w}</li>)}</ul>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function StarforceDetail({ d }: { d: StageResult }) {
  const e = d.expected;
  return (
    <div className="panel">
      <h3>스타포스 <small className="muted">{d.table_version}</small></h3>
      <div className="kv">
        <span>기대 메소</span><b>{meso(e.meso)}</b>
        <span>기대 파괴</span><b>{num(e.destroys, 2)}회 (스페어 {num(e.spares, 2)}개)</b>
        <span>기대 시도</span><b>{num(e.attempts, 0)}회</b>
        <span>무파괴 성공 확률</span><b>{pct(d.distribution.no_destroy_prob, 1)}</b>
        {d.policy && (
          <>
            <span>최적 정책</span>
            <b>
              파방 {d.policy.safeguard.length ? d.policy.safeguard.map((s: number) => `${s}성`).join("·") : "없음"} /
              확정복구 {Object.keys(d.policy.recovery).length ? Object.keys(d.policy.recovery).map((s) => `${s}성`).join("·") : "없음"}
            </b>
          </>
        )}
      </div>
      <details>
        <summary>성급별 상세</summary>
        <table className="dense">
          <thead><tr><th>성급</th><th>성공</th><th>유지</th><th>파괴</th><th>1회 비용</th><th>여기서 목표까지 기대</th><th>파괴 시</th></tr></thead>
          <tbody>
            {d.steps.map((s: any) => (
              <tr key={s.star}>
                <td>{s.star}→{s.star + 1}{s.safeguard ? " 🛡" : ""}{s.unverified_cost ? " ⚠" : ""}</td>
                <td>{pct(s.success, 2)}</td><td>{pct(s.fail, 2)}</td><td>{pct(s.destroy, 2)}</td>
                <td>{meso(s.cost)}</td><td>{meso(s.expected_total_from_here)}</td>
                <td>{s.destroy > 0 ? `${s.recovery_star}성 (스페어 ${s.recovery_spares}${s.recovery_meso ? ` + ${meso(s.recovery_meso)}` : ""})` : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function PotentialDetail({ title, d }: { title: string; d: StageResult }) {
  return (
    <div className="panel">
      <h3>{title} {d.target_label && <small className="muted">목표: {d.target_label}</small>}</h3>
      <div className="kv">
        {d.stages.map((s: any) => (
          <span key={s.grade} style={{ display: "contents" }}>
            <span>{s.grade_name} → 다음 등급</span>
            <b>{pct(s.p, 3)} · 천장 {s.pity}회 · 기대 {num(s.expected_attempts, 1)}회 ({meso(s.expected_attempts * s.cost)})</b>
          </span>
        ))}
        {d.option_prob != null && (
          <>
            <span>목표 옵션 1회 확률</span><b>{pct(d.option_prob, 3)} (1/{num(1 / d.option_prob, 0)})</b>
            <span>기대 시도 / 메소</span><b>{num(d.option_expected_attempts, 0)}회 × {meso(d.cost_per_attempt)} = {meso(d.option_expected_meso)}</b>
            <span>50% / 90% 확률 도달</span><b>{d.attempts_for_confidence.p50}회 / {d.attempts_for_confidence.p90}회</b>
          </>
        )}
        <span>합계 기대</span><b>{meso(d.expected_total_meso)}</b>
      </div>
    </div>
  );
}

function FlameDetail({ d }: { d: StageResult }) {
  return (
    <div className="panel">
      <h3>추가옵션</h3>
      <div className="kv">
        <span>1회 성공 확률</span><b>{pct(d.prob, 3)} (1/{num(1 / d.prob, 0)})</b>
        <span>기대 시도 / 메소</span><b>{num(d.expected_attempts, 0)}회 × {meso(d.cost_per_attempt)} = {meso(d.expected_meso)}</b>
        <span>50% / 90% 확률 도달</span><b>{d.attempts_for_confidence.p50}회 / {d.attempts_for_confidence.p90}회</b>
      </div>
    </div>
  );
}
