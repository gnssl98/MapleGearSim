import { useEffect, useState } from "react";
import { api, type Settings } from "../api";
import { Icon } from "./ui";

/** 1억 메소당 원 시세: 사용자가 정한다 (설정에 저장, 모든 탭 공통) */
export function WonRate({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [v, setV] = useState<number | "">(settings.won_per_eok ?? "");
  const [saved, setSaved] = useState(false);
  useEffect(() => setV(settings.won_per_eok ?? ""), [settings.won_per_eok]);
  const save = async () => {
    const s = await api<Settings>("/settings", { method: "PUT", body: { ...settings, won_per_eok: v === "" ? null : v } });
    onSettings(s);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };
  const dirty = (settings.won_per_eok ?? "") !== v;
  return (
    <div className={`won-rate ${settings.won_per_eok ? "" : "missing"}`}>
      <span className="field-label">1억 메소 =</span>
      <span className="num-input compact">
        <input type="number" min={0} step={50} placeholder="예: 2000" value={v}
          onChange={(e) => setV(e.target.value === "" ? "" : Number(e.target.value))}
          onKeyDown={(e) => e.key === "Enter" && save()} />
        <em>원</em>
      </span>
      {(dirty || saved) && <button type="button" className={`icon-btn ${saved ? "done" : ""}`} title="저장 (모든 탭 공통)" onClick={save}><Icon name="check" size={15} /></button>}
      {!settings.won_per_eok && <span className="muted small">현금 환산에 쓰는 기준이에요. 메소마켓 시세 등 원하는 값으로 정하세요</span>}
    </div>
  );
}
