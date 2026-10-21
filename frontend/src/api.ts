export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: init?.method ?? (init?.body !== undefined ? "POST" : "GET"),
    headers: init?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export type Settings = {
  job: string;
  characters: string[];
  mvp: string;
  pc_room: boolean;
  mvp_max_star: number;
  won_per_eok: number | null;
  events: {
    discount30: boolean;
    destroy_reduction: boolean;
    guaranteed_5_10_15: boolean;
    plus_one: boolean;
    recovery_discount: boolean;
    miracle: boolean;
  };
  flame_coef: { main: number; sub: number; att: number; all_pct: number };
  hwansan: Assumptions;
  budget_eok: number;
  excluded_items: string[];
  flame_method: string;
  presets: Record<string, Partial<Record<"boss" | "farming", PresetChoice>>>;
  ledger: { cube_prices: Record<string, number>; item_levels: Record<string, number> };
  tickets: Tickets;
  bm: { unit_prices: Record<string, number>; values: Record<string, number>; jackpots: Record<string, string[]>; options: Record<string, number> };
  mvp_plan: MvpPlan;
};

export type BmEvalReq = {
  product: string; table: number; unit_price_won: number; spend_won: number;
  bundle?: { count: number; price: number } | null;
  values_eok: Record<string, number>; jackpots: string[];
};
export type MvpPlan = {
  current_cash: number; target: string; sf_meso_eok: number; sell_meso_eok: number; other_won: number;
  mesomarket_recovery: number; bm: BmEvalReq[];
};

/** 보유 이벤트 아이템 개수 (backend engine/tickets.py) */
export type Tickets = { unique_potential: number; epic_additional: number; star17: number; star17_max_level: number };
export const ticketLabels = (t: Tickets) => [
  t.star17 > 0 && `17성 강화권 ${t.star17}개 (${t.star17_max_level}제 이하)`,
  t.unique_potential > 0 && `유니크 잠재 주문서 ${t.unique_potential}개`,
  t.epic_additional > 0 && `에픽 에디 주문서 ${t.epic_additional}개`,
].filter(Boolean) as string[];

export type PresetChoice = { equipment: number; ability: number; hyper: number };
export type PresetInfo = {
  current: PresetChoice;
  chosen: { boss: PresetChoice; farming: PresetChoice };
  guessed: { boss: PresetChoice; farming: PresetChoice };
  custom: boolean;
  view: "current" | "boss" | "farming";
  target: PresetChoice;
};
export const PRESET_KINDS = [["equipment", "장비"], ["ability", "어빌리티"], ["hyper", "하이퍼스탯"]] as const;
export const presetText = (c: PresetChoice) => `장비 ${c.equipment} · 어빌 ${c.ability} · 하이퍼 ${c.hyper}`;

export type Assumptions = {
  boss_armor: number;
  crit_rate_100: boolean;
  extra_main_pct: number;
  extra_att_pct: number;
  extra_main_static: number;
};

export type HwansanRow = { label: string; hwansan: number; damage_pct: number };

export type Meta = {
  jobs: { id: string; name: string; main_stat: string; sub_stat: string }[];
  parts: { id: string; name: string }[];
  grades: { id: string; name: string }[];
  flame_methods: { id: string; label: string; meso: boolean }[];
  starforce: { version: string; max_star_by_level: { min_level: number; max_star: number }[]; safeguard_stars: number[] };
  potential_tables_fetched_at: string | null;
};

export type Histogram = { lo: number; hi: number; count: number }[];
export type Percentiles = Record<string, number>;

export type Preset = { id: string; label: string };
