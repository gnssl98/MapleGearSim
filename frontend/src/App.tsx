import { useEffect, useState } from "react";
import { api, type Meta, type Settings } from "./api";
import { Icon, More, type IconName } from "./components/ui";
import { Character, type Item, type NextStep } from "./pages/Character";
import { Bm } from "./pages/Bm";
import { Craft, prefillFromItem, type Prefill } from "./pages/Craft";
import { Ledger } from "./pages/Ledger";
import { Mvp } from "./pages/Mvp";
import { Prices } from "./pages/Prices";
import { Recommend } from "./pages/Recommend";
import { SettingsPage } from "./pages/SettingsPage";
import { Shopping } from "./pages/Shopping";

const TABS: { id: string; label: string; icon: IconName; desc: string }[] = [
  { id: "character", label: "내 캐릭터", icon: "user", desc: "장착 장비와 다음 단계 장비" },
  { id: "recommend", label: "업그레이드 추천", icon: "sparkles", desc: "예산 안에서 환산이 가장 많이 오르는 조합" },
  { id: "shopping", label: "구매 상한가", icon: "tag", desc: "경매장에서 이 가격까지는 사도 되는 매물" },
  { id: "craft", label: "직작 계산기", icon: "hammer", desc: "노작부터 직접 만들 때 비용과 운" },
  { id: "prices", label: "시세 기록", icon: "chart", desc: "경매장에서 본 매물 가격 기록" },
  { id: "ledger", label: "강화 가계부", icon: "wallet", desc: "실제로 쓴 메소와 강화 운" },
  { id: "bm", label: "확률형 BM", icon: "box", desc: "현질 금액으로 기대 회수와 손익분기 당첨 개수" },
  { id: "mvp", label: "MVP 작", icon: "star", desc: "MVP 등급을 채우는 가장 싼 방법" },
  { id: "settings", label: "설정", icon: "gear", desc: "MVP·이벤트·환산 가정" },
];
type Tab = string;

export function App() {
  const [tab, setTab] = useState<Tab>("character");
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api<Meta>("/meta"), api<Settings>("/settings")])
      .then(([m, s]) => { setMeta(m); setSettings(s); })
      .catch((e) => setError(`서버에 연결할 수 없습니다: ${e.message}`));
  }, []);

  const toCraft = (it: Item, step?: NextStep | null) => {
    setPrefill(prefillFromItem(it, step));
    setTab("craft");
    window.scrollTo(0, 0);
  };

  const activeEvents = settings ? Object.values(settings.events).filter(Boolean).length : 0;
  const cur = TABS.find((t) => t.id === tab)!;

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand"><span className="logo"><Icon name="star" size={16} /></span><b>MapleGearSim</b></div>
        <nav>
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "nav-item on" : "nav-item"} onClick={() => { setTab(t.id); window.scrollTo(0, 0); }}>
              <Icon name={t.icon} size={18} />
              <span>{t.label}</span>
              {t.id === "settings" && activeEvents > 0 && <span className="badge" title="진행 중인 이벤트">{activeEvents}</span>}
            </button>
          ))}
        </nav>
        <More label="정보" className="side-foot">
          개인용 계산기 · 확률/비용은 공식 공지·확률 공개 페이지와 커뮤니티 자료 기준이며 ⚠ 표시는 미검증 수치입니다.
          장비 이미지: 넥슨 오픈 API · maplestory.io. <br />Data based on NEXON Open API
        </More>
      </aside>
      <main className="content">
        <div className="page-head">
          <h1>{cur.label}</h1>
          <p className="muted">{cur.desc}</p>
        </div>
        {error && <p className="error">{error}</p>}
        {meta && settings && (
          <>
            <div hidden={tab !== "character"}>
              <Character meta={meta} settings={settings} onSettings={setSettings} onCraft={toCraft} />
            </div>
            <div hidden={tab !== "recommend"}><Recommend settings={settings} onSettings={setSettings} /></div>
            <div hidden={tab !== "shopping"}><Shopping settings={settings} /></div>
            <div hidden={tab !== "craft"}><Craft meta={meta} settings={settings} prefill={prefill} /></div>
            <div hidden={tab !== "prices"}><Prices meta={meta} settings={settings} /></div>
            <div hidden={tab !== "ledger"}><Ledger settings={settings} onSettings={setSettings} /></div>
            <div hidden={tab !== "bm"}><Bm settings={settings} onSettings={setSettings} /></div>
            <div hidden={tab !== "mvp"}><Mvp settings={settings} onSettings={setSettings} /></div>
            {tab === "settings" && <SettingsPage meta={meta} settings={settings} onSaved={setSettings} />}
          </>
        )}
      </main>
    </div>
  );
}
