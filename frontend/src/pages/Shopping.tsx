import { useMemo, useState } from "react";
import { api, presetText, ticketLabels, type PresetInfo, type Settings } from "../api";
import { CopyButton, Empty, Icon, ItemIcon, More, Seg, Stat } from "../components/ui";
import { meso, num, pct, won } from "../format";

type Target = {
  slot: string;
  item: string;
  part: string;
  star: number;
  potential: string;
  gain: number;
  damage_pct: number;
  craft_cost: number | null;
  value_cap: number | null;
  resale: number;
  cap: number;
  cap_before_resale: number;
  binding: "craft" | "value";
  search: string;
  detail: { from_star: number; starforce: number; potential: number; destroys: number };
  notes: string[];
  kind: "upgrade" | "next";
  level: number;
  base_price: number | null;
  icon: string | null;
};
type Result = {
  name: string;
  budget: number;
  threshold: number | null;
  threshold_auto: number | null;
  targets: Target[];
  presets: PresetInfo;
  excluded: string[];
  warnings: string[];
};
type Mode = "auto" | "manual" | "off";
type Kind = Target["kind"];

const EOK = 1e8;
const opt = (v: number | "" | undefined) => (v === "" || v == null ? null : v * EOK);

export function Shopping({ settings }: { settings: Settings }) {
  const [name, setName] = useState(settings.characters[0] ?? "");
  const [budget, setBudget] = useState(settings.budget_eok);
  const [mode, setMode] = useState<Mode>("auto");
  const [manual, setManual] = useState(20);
  const [kind, setKind] = useState<Kind>("upgrade");
  const [res, setRes] = useState<Result | null>(null);
  const [auto, setAuto] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [override, setOverride] = useState<Record<string, number | "">>({});  // 판매가(upgrade) / 노작가(next)
  const [seen, setSeen] = useState<Record<string, number | "">>({});
  const [open, setOpen] = useState<string | null>(null);

  const run = async () => {
    if (!name) return;
    setLoading(true);
    setError("");
    try {
      const threshold = mode === "auto" ? null : mode === "off" ? 0 : manual;
      const r = await api<Result>("/shopping", { body: { name, budget_eok: budget, threshold } });
      setRes(r);
      if (r.threshold_auto != null) setAuto(r.threshold_auto);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const groupKey = (t: Target) => `${t.kind}|${t.slot}|${t.item}`;
  const groups = useMemo(() => {
    const m = new Map<string, Target[]>();
    for (const t of res?.targets ?? []) if (t.kind === kind) m.set(groupKey(t), [...(m.get(groupKey(t)) ?? []), t]);
    return [...m.entries()];
  }, [res, kind]);
  const counts = useMemo(() => {
    const c = { upgrade: new Set<string>(), next: new Set<string>() };
    for (const t of res?.targets ?? []) c[t.kind].add(groupKey(t));
    return { upgrade: c.upgrade.size, next: c.next.size };
  }, [res]);

  /** upgrade: 상한가 = min(직작, 효율) + 되팔기 / next: 노작가 + 직작 비용 */
  const capOf = (t: Target, g: string) => {
    const o = opt(override[g]);
    if (t.kind === "next") return (t.craft_cost ?? 0) + (o ?? t.base_price ?? 0);
    return t.cap_before_resale + (o ?? t.resale);
  };

  const w = settings.won_per_eok;

  return (
    <div className="shopping">
      <section className="panel toolbar-panel">
        <form className="char-search" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <select value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 200 }}>
            {settings.characters.length === 0 && <option value="">내 캐릭터 탭에서 먼저 불러오세요</option>}
            {settings.characters.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <span className="num-input" style={{ maxWidth: 170 }}>
            <em>예산</em><input type="number" min={0} step={1} value={budget} onChange={(e) => setBudget(Number(e.target.value))} /><em>억</em>
          </span>
          <button className="btn primary" type="submit" disabled={loading || !name}>{loading ? "계산 중…" : "상한가 계산"}</button>
        </form>
        <div className="toolbar wrap">
          <span className="field-label">효율 기준</span>
          <Seg value={mode} onChange={setMode} options={[["auto", "자동"], ["manual", "직접 입력"], ["off", "끄기"]] as const} />
          {mode === "manual" && (
            <span className="num-input" style={{ maxWidth: 170 }}>
              <em>억당 환산</em><input type="number" min={0} step={1} value={manual} onChange={(e) => setManual(Number(e.target.value))} />
            </span>
          )}
          {auto != null && mode === "auto" && <span className="muted small">억당 환산 {num(auto, 1)}</span>}
        </div>
        {error && <p className="error">{error}</p>}
        <More>
          <p>경매장(메이플 핸즈·웹)에서 볼 매물의 <b>최대 구매가</b>를 계산합니다. 검색 조건을 복사해서 찾고, 본 가격을 넣으면 바로 판단해 줍니다.</p>
          <ul>
            <li><b>지금 장비 강화</b>: 상한가 = min(직작 비용, 효율 기준가) + 내 장비 되팔기.
              직작 비용은 내 장비를 같은 스펙까지 직접 올리는 기대 비용, 효율 기준가는 환산 이득 ÷ 기준 억당 환산입니다.</li>
            <li><b>자동 효율 기준</b>: 예산으로 할 수 있는 최적 조합의 마지막 선택 효율. 이보다 비싸게 사면 다른 업그레이드에 쓰는 게 낫다는 뜻입니다.
              <b> 끄기</b>는 직작 비용만 봅니다.</li>
            <li><b>상위 템</b>: 상한가 = 노작 구매가 + 노작 0성 → 목표 성 + 레어 → 목표 잠재 기대 비용. 지금 장비는 사든 만들든 팔게 되므로 되팔기는 더하지 않습니다.
              상위 템의 환산 이득은 기본 스탯·세트 데이터가 없어 계산하지 않습니다.</li>
            <li>매물은 같은 아이템, 목표 성 이상, 잠재 조건 이상을 가정합니다. 지금 장비 강화는 에디·추옵도 현재 이상, 상위 템은 노작 수준 기준입니다.</li>
            <li>판매가·노작가를 비우면 시세 기록 탭의 비슷한 매물로 추정하고, 기록이 없으면 0으로 계산합니다.</li>
            <li>쿨감 모자처럼 환산에 안 잡히는 옵션을 띄운 장비는 같은 종류 목표만 보여 줍니다.</li>
          </ul>
        </More>
      </section>

      {res && (
        <>
          <div className="stats-row">
            <Stat label="기준 억당 환산" value={res.threshold ? num(res.threshold, 1) : "없음"} sub={res.threshold ? "이보다 효율 나쁘면 비쌈" : "직작 비용만 비교"} tone="accent" />
            <Stat label="지금 장비 강화" value={`${counts.upgrade}개 부위`} />
            <Stat label="상위 템" value={`${counts.next}종`} sub="노작 → 직작 기준" icon="up" />
            <Stat label="기준 프리셋" value="보스용" sub={presetText(res.presets.target)} />
          </div>
          <TicketHint settings={settings} />
          {res.warnings.map((x) => <p key={x} className="error small">{x}</p>)}
          {res.excluded.length > 0 && <p className="muted small">제외 장비 {res.excluded.length}개는 계산하지 않았어요 (업그레이드 추천 탭에서 관리)</p>}

          <Seg value={kind} onChange={setKind} options={[["upgrade", `지금 장비 강화 ${counts.upgrade}`], ["next", `상위 템 ${counts.next}`]] as const} />

          <div className="shop-groups">
            {groups.map(([g, rows]) => {
              const t0 = rows[0];
              const isNext = t0.kind === "next";
              const estimate = isNext ? t0.base_price : t0.resale;
              return (
                <section key={g} className="panel shop-group">
                  <div className="group-head">
                    <ItemIcon src={t0.icon} name={t0.item} size={44} star={isNext ? null : t0.detail.from_star} />
                    <div className="grow">
                      <small className="muted">{t0.slot} · {t0.level}제{isNext ? " · 상위 템" : ""}</small>
                      <h3>{t0.item}</h3>
                    </div>
                    <label className="num-input compact" title={isNext ? "노작(0성·레어 이하) 구매가" : "지금 장비를 팔 때 손에 쥐는 금액 (수수료 뺀 금액)"}>
                      <em>{isNext ? "노작가" : "내 장비 판매가"}</em>
                      <input type="number" min={0} step={0.5} placeholder={estimate ? num(estimate / EOK, 2) : "0"} value={override[g] ?? ""}
                        onChange={(e) => setOverride({ ...override, [g]: e.target.value === "" ? "" : Number(e.target.value) })} />
                      <em>억</em>
                    </label>
                  </div>
                  {isNext && estimate == null && opt(override[g]) == null && (
                    <p className="hint"><Icon name="info" size={14} /> 노작 시세 기록이 없어 강화비만으로 계산했어요. 노작가를 넣으면 상한가에 더해집니다.</p>
                  )}
                  <div className="offers">
                    {rows.map((t, i) => {
                      const key = `${g}|${i}`;
                      const cap = capOf(t, g);
                      const p = seen[key];
                      const verdict = p === "" || p == null ? null : p * EOK <= cap;
                      return (
                        <div key={key} className={`offer ${verdict == null ? "" : verdict ? "ok" : "no"}`}>
                          <div className="offer-spec">
                            {t.star > 0 && <span className="pill star">★ {t.star}{isNext || t.star > t.detail.from_star ? "+" : ""}</span>}
                            <span className="pill">{t.potential.replace(/ \(.*\)$/, "")}</span>
                            {!isNext && <span className="muted small">환산 +{num(t.gain, 0)} · 딜 +{pct(t.damage_pct / 100, 2)}</span>}
                          </div>
                          <div className="offer-cap" title={won(cap, w)}>
                            <small className="muted">상한가</small>
                            <b>{meso(cap)}</b>
                          </div>
                          <label className="num-input compact seen">
                            <input type="number" min={0} step={0.5} placeholder="본 가격" value={p ?? ""}
                              onChange={(e) => setSeen({ ...seen, [key]: e.target.value === "" ? "" : Number(e.target.value) })} />
                            <em>억</em>
                          </label>
                          <span className="verdict">{verdict == null ? "" : verdict ? <><Icon name="check" size={14} /> 구매</> : "비쌈"}</span>
                          <CopyButton text={t.search} />
                          <button type="button" className="icon-btn" title="계산 내역" onClick={() => setOpen(open === key ? null : key)}>
                            <Icon name="info" size={15} />
                          </button>
                          {open === key && (
                            <div className="offer-detail">
                              <div className="kv">
                                {isNext ? (
                                  <>
                                    <span>노작가</span><b>{meso(opt(override[g]) ?? t.base_price ?? 0)}{opt(override[g]) == null && (t.base_price != null ? " (시세 기록)" : " (미입력)")}</b>
                                    <span>스타포스 0→{t.star}</span><b>{meso(t.detail.starforce)}</b>
                                  </>
                                ) : (
                                  <>
                                    <span className={t.binding === "craft" ? "bind" : ""}>직작 비용 {t.binding === "craft" && "← 기준"}</span>
                                    <b>{meso(t.craft_cost)} <small className="muted">(스타포스 {meso(t.detail.starforce)})</small></b>
                                    <span className={t.binding === "value" ? "bind" : ""}>효율 기준가 {t.binding === "value" && "← 기준"}</span><b>{meso(t.value_cap)}</b>
                                    <span>+ 내 장비 되팔기</span><b>{meso(opt(override[g]) ?? t.resale)}</b>
                                  </>
                                )}
                                <span>잠재</span><b>{meso(t.detail.potential)}</b>
                                <span>검색 조건</span><b className="wrap-text">{t.search}</b>
                              </div>
                              {t.notes.length > 0 && <ul className="small muted">{t.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
          {!groups.length && <Empty>{kind === "next" ? "상위 단계가 있는 장비가 없습니다" : "계산할 목표가 없습니다"}</Empty>}
        </>
      )}
    </div>
  );
}

export function TicketHint({ settings }: { settings: Settings }) {
  const t = ticketLabels(settings.tickets);
  return (
    <p className="hint">
      <Icon name="star" size={14} />
      {t.length ? <>이벤트 아이템 반영: {t.join(" · ")}</> : "보유 이벤트 아이템 없음 (17성 강화권·유니크 잠재·에픽 에디 주문서는 설정 탭에서 입력)"}
    </p>
  );
}
