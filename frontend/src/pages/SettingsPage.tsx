import { useState } from "react";
import { api, type Meta, type Settings } from "../api";
import { More } from "../components/ui";

const EVENTS: { key: keyof Settings["events"]; label: string }[] = [
  { key: "discount30", label: "스타포스 강화 비용 30% 할인" },
  { key: "destroy_reduction", label: "파괴 확률 30% 감소 (21성 이하)" },
  { key: "guaranteed_5_10_15", label: "5·10·15성 100% 성공" },
  { key: "plus_one", label: "10성 이하 1+1" },
  { key: "recovery_discount", label: "흔적 복구 메소 20% 할인" },
  { key: "miracle", label: "미라클 타임 (잠재 등급 상승 2배)" },
];

export function SettingsPage({ meta, settings, onSaved }: { meta: Meta; settings: Settings; onSaved: (s: Settings) => void }) {
  const [s, setS] = useState<Settings>(settings);
  const [msg, setMsg] = useState("");

  const save = async () => {
    const saved = await api<Settings>("/settings", { method: "PUT", body: s });
    onSaved(saved);
    setMsg("저장했습니다");
    setTimeout(() => setMsg(""), 2000);
  };
  const ev = (k: keyof Settings["events"], v: boolean) => setS({ ...s, events: { ...s.events, [k]: v } });
  const hw = <K extends keyof Settings["hwansan"]>(k: K, v: Settings["hwansan"][K]) => setS({ ...s, hwansan: { ...s.hwansan, [k]: v } });
  const shining = () => setS({ ...s, events: { ...s.events, discount30: true, destroy_reduction: true } });

  return (
    <div className="settings">
      <section className="panel form">
        <h2>프로필</h2>
        <label className="row"><span>직업</span>
          <select value={s.job} onChange={(e) => setS({ ...s, job: e.target.value })}>
            {meta.jobs.map((j) => <option key={j.id} value={j.id}>{j.name} ({j.main_stat}/{j.sub_stat})</option>)}
          </select>
        </label>
        <label className="row"><span>MVP 등급</span>
          <select value={s.mvp} onChange={(e) => setS({ ...s, mvp: e.target.value })}>
            {[["none", "없음"], ["bronze", "브론즈"], ["silver", "실버 (3%)"], ["gold", "골드 (5%)"], ["diamond", "다이아 (10%)"], ["red", "레드 (10%)"], ["black", "블랙 (10% ⚠)"]]
              .map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="check"><input type="checkbox" checked={s.pc_room} onChange={(e) => setS({ ...s, pc_room: e.target.checked })} />프리미엄 PC방 (스타포스 5%, 판매 수수료 3%)</label>
        <label className="row"><span>MVP/PC방 할인 적용 상한</span>
          <span className="num-input"><input type="number" value={s.mvp_max_star} min={0} max={29}
            onChange={(e) => setS({ ...s, mvp_max_star: Number(e.target.value) })} /><em>성까지 (현재 성급 기준) ⚠</em></span>
        </label>
        <label className="row"><span>1억 메소당 현금 (직접 정하기)</span>
          <span className="num-input"><input type="number" value={s.won_per_eok ?? ""} placeholder="예: 2200"
            onChange={(e) => setS({ ...s, won_per_eok: e.target.value === "" ? null : Number(e.target.value) })} /><em>원 / 1억 메소</em></span>
        </label>
      </section>

      <section className="panel form">
        <div className="toolbar">
          <h2>진행 중인 이벤트</h2>
          <button type="button" className="chip" onClick={shining}>샤이닝 스타포스 프리셋</button>
        </div>
        {EVENTS.map((e) => (
          <label key={e.key} className="check"><input type="checkbox" checked={s.events[e.key]} onChange={(x) => ev(e.key, x.target.checked)} />{e.label}</label>
        ))}
      </section>

      <section className="panel form">
        <h2>보유 이벤트 아이템</h2>
        <div className="grid2">
          {([["star17", "스타포스 17성 강화권"], ["unique_potential", "유니크 잠재능력 부여 주문서"], ["epic_additional", "에픽 에디셔널 잠재능력 부여 주문서"]] as const).map(([k, l]) => (
            <label key={k} className="row"><span>{l}</span>
              <span className="num-input"><input type="number" min={0} value={s.tickets[k]}
                onChange={(e) => setS({ ...s, tickets: { ...s.tickets, [k]: Number(e.target.value) || 0 } })} /><em>개</em></span>
            </label>
          ))}
          <label className="row"><span>17성 강화권 사용 가능 레벨</span>
            <span className="num-input"><input type="number" min={0} max={300} value={s.tickets.star17_max_level}
              onChange={(e) => setS({ ...s, tickets: { ...s.tickets, star17_max_level: Number(e.target.value) || 0 } })} /><em>제 이하 ⚠</em></span>
          </label>
        </div>
        <More>
          1개 이상 보유하면 구매 상한가·업그레이드 추천·직작 계산기·시세 기록의 직작 비교에서 이 아이템을 쓴다고 보고 기대 비용을 다시 계산합니다.
          <ul>
            <li>17성 강화권: 17성 미만 장비를 17성으로 (목표가 17성 이상이고 장비 레벨이 위 상한 이하일 때). 17성 이후 파괴되면 다시 올리는 비용은 포함됩니다.</li>
            <li>유니크 잠재 주문서: 잠재가 유니크 미만이면 유니크부터 시작 (레어→유니크 등급업 비용 0).</li>
            <li>에픽 에디 주문서: 에디가 에픽 미만이면 에픽부터 시작.</li>
            <li>아이템은 이벤트로 받은 교환 불가 아이템으로 보고 비용 0으로 계산합니다. 보유 개수보다 많은 부위에 동시에 쓰는 경우는 따로 막지 않습니다.</li>
            <li>⚠ 강화권의 사용 가능 레벨은 이벤트마다 달라 직접 맞춰 주세요 (아이템 설명 참고).</li>
          </ul>
        </More>
      </section>

      <section className="panel form">
        <h2>추옵 급수 계수</h2>
        <More>급수 = 주스탯×a + 부스탯×b + 공/마×c + 올스탯%×d</More>
        <div className="grid4">
          {([["main", "주스탯"], ["sub", "부스탯"], ["att", "공/마"], ["all_pct", "올스탯%"]] as const).map(([k, l]) => (
            <label key={k} className="row"><span>{l}</span>
              <input type="number" step="0.1" value={s.flame_coef[k]}
                onChange={(e) => setS({ ...s, flame_coef: { ...s.flame_coef, [k]: Number(e.target.value) } })} />
            </label>
          ))}
        </div>
      </section>

      <section className="panel form">
        <h2>환산·추천</h2>
        <More>환산 주스탯 = 현재 스펙에서 "최종 주스탯 1"과 같은 보스 딜 증가를 1로 둔 값 (데미지 공식 차분)</More>
        <div className="grid2">
          <label className="row"><span>보스 방어율</span>
            <span className="num-input"><input type="number" value={s.hwansan.boss_armor} onChange={(e) => hw("boss_armor", Number(e.target.value))} /><em>%</em></span>
          </label>
          <label className="row"><span>추천 기본 예산</span>
            <span className="num-input"><input type="number" value={s.budget_eok} onChange={(e) => setS({ ...s, budget_eok: Number(e.target.value) })} /><em>억</em></span>
          </label>
          <label className="row"><span>장비 외 주스탯% 보정</span>
            <span className="num-input"><input type="number" value={s.hwansan.extra_main_pct} onChange={(e) => hw("extra_main_pct", Number(e.target.value))} /><em>%</em></span>
          </label>
          <label className="row"><span>장비 외 공격력% 보정</span>
            <span className="num-input"><input type="number" value={s.hwansan.extra_att_pct} onChange={(e) => hw("extra_att_pct", Number(e.target.value))} /><em>%</em></span>
          </label>
          <label className="row"><span>추가 미적용 주스탯 (헥사 스탯 등)</span>
            <input type="number" value={s.hwansan.extra_main_static} onChange={(e) => hw("extra_main_static", Number(e.target.value))} />
          </label>
          <label className="row"><span>추옵 재설정 수단 (추천용)</span>
            <select value={s.flame_method} onChange={(e) => setS({ ...s, flame_method: e.target.value })}>
              {meta.flame_methods.filter((m) => m.meso).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>
        </div>
        <label className="check"><input type="checkbox" checked={s.hwansan.crit_rate_100} onChange={(e) => hw("crit_rate_100", e.target.checked)} />크리티컬 확률 100% 가정 (버프 포함)</label>
      </section>

      <div className="save-bar">
        <button className="btn primary" onClick={save}>저장</button>
        {msg && <span className="muted">{msg}</span>}
      </div>

      <section className="panel muted small">
        <p>스타포스 테이블: {meta.starforce.version} · 잠재 옵션 확률표 수집일: {meta.potential_tables_fetched_at ?? "없음"}</p>
      </section>
    </div>
  );
}
