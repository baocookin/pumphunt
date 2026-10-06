"use client";

import { useEffect, useState } from "react";

// Same origin by default (FastAPI serves this export); override for `next dev`.
const API = `${process.env.NEXT_PUBLIC_API_URL ?? ""}/api`;

type ChainFeed = { connected?: boolean; connects?: number; stale_reconnects?: number; subscribed?: number; notifications?: number; events?: number; last_error?: string | null; mentions?: string[] };
type PortalFeed = { connected?: boolean; connects?: number; stale_reconnects?: number; messages?: number; last_msg_ts?: number; last_error?: string | null };
type NoEvent = { signature?: string; found?: boolean; log_truncated?: boolean; pump_ixs?: { name?: string | null; disc: string; inner: boolean }[]; events?: { kind: string; via: string }[] };
type Rpc = {
  confirmed?: number; failed?: number; no_event?: number; last_rpc_ts?: number; via?: Record<string, number>; triggered?: Record<string, number>; last_no_event?: NoEvent | null;
  withdraw_authority?: string | null; authority_static?: boolean | null; migrate_ix?: string | null;
  migrate_users?: Record<string, number>; migrate_user_static?: boolean | null; portal_mislabeled?: number;
  noop?: number; retry_pending?: number; failed_final?: number; last_failed?: { signature?: string; error?: string } | null;
  transport?: { calls?: number; rate_limited?: number; errors?: number } | null;
  poller?: { polls?: number; listed?: number; skipped_failed?: number; cursor?: string | null; last_poll_ts?: number; last_error?: string | null; backfill_from?: number | null };
};
type Stats = {
  build_sha?: string;
  status: {
    now?: number; last_chain_ts?: number; last_portal_ts?: number; counts?: Record<string, number>;
    chain_feed?: ChainFeed | null; portal_feed?: PortalFeed | null; portal_pools?: Record<string, number>; rpc?: Rpc | null; mentions?: string[];
    harvest?: Harvest | null; gecko?: Gecko | null; snapshots?: Snapshots | null;
  };
  chain_scope: "migrations" | "full";
  creates_24h: number;
  creates_24h_chain: number;
  creates_24h_portal: number;
  portal_coverage: number | null;
  migrations_24h: number;
  migrations_24h_portal: number;
  migrations_total: number;
  hourly: { hour: string; creates_chain: number; creates_portal: number; migrations: number; migrations_portal: number }[];
};
type Migration = { mint: string; pool: string | null; ts: number; slot: number | null; sol_amount?: number; quote_mint?: string | null; harvested: boolean; source?: string };
const SOL_QUOTES = new Set(["So11111111111111111111111111111111111111112", "11111111111111111111111111111111"]);
type Cell = { n: number; median?: number; win_rate?: number; top2pct_share?: number; p10?: number; p90?: number };
type Snapshots = { taken?: number; late?: number; errors?: number; queued?: number; last_ts?: number; last_error?: string | null };
type Harvest = { runs?: number; last_run_ts?: number; last_error?: string | null; rows_last_run?: number; with_data?: number; no_pool?: number; no_candles?: number; due?: number; pending?: number; fills_rows?: number; swaps_fetched?: number; credits_today?: number; fills_paused?: boolean; gtfa?: boolean | null; gtfa_error?: string | null; replay_windows?: number; window_incomplete?: number; windows_with_breaks?: number; flow_rows?: number; states_unresolved?: number; token_filter?: boolean | null; token_filter_note?: string | null; token_filter_checks?: Record<string, number>; features_rows?: number; funding_rows?: number; funding_lookups?: number; features_error?: string | null };
type ModelStat = { n?: number; median?: number; win_rate?: number; p10?: number; p90?: number };
type Stratum = { bucket: string; n?: number; median?: number; win_rate?: number; p90?: number };
type Gecko = { calls?: number; rate_limited?: number; not_found?: number; errors?: number };
type DataFile = { name: string; bytes: number; mtime: number };
type Summary = {
  harvested: number; with_data: number; with_fills?: number; alive_24h_rate: number; no_data?: Record<string, number>;
  cells: Record<string, Cell>; verdict: { status: string; why: string };
  fills?: Record<string, Record<string, Cell>>; fill_primary_size?: string | null; verdict_fill?: { status: string; why: string };
  fill_models?: { net_ghost?: ModelStat; net_replay?: ModelStat; net_persist?: ModelStat; exit_capped_share?: number; replayed_share?: number };
  fill_strata?: { real_in_sol?: Stratum[]; idle_at_entry?: Stratum[] };
  prereg?: Prereg;
};
type Hypothesis = { name: string; desc: string; since: number | null; eligible: number; members: number; n: number; median?: number | null; mean?: number | null; rug_share?: number | null; win_rate?: number | null; p10?: number | null; p90?: number | null; top2pct_share?: number | null; median_ci95?: [number, number] | null; verdict: { status: string; why: string } };
type Prereg = { prereg_ts: number; explore_until: number; cell: string; size: string; c2: { min_real_sol: number; max_idle_s: number }; hypotheses: Hypothesis[] };
type Config = { entry_delays_min: number[]; horizons_min: number[]; cost_bps_round_trip: number; fill_sizes_sol?: number[]; fills_daily_credits?: number; sniper_daily_credits?: number; sniper_sample_per_10k?: number };
type SnipeCell = { n: number; mean?: number; mean_ci95?: [number, number] | null; median?: number; win_rate?: number; p_2x?: number; p_10x?: number; unresolved?: number };
type SniperRecorderStats = { polls?: number; creates_seen?: number; sampled?: number; census_gaps?: number; harvested?: number; not_sol?: number; errors?: number; credits_today?: number; paused?: boolean; queued?: number; last_poll_ts?: number; last_error?: string | null };
type Sniper = {
  launches: number; classic: number; mayhem: number; graduated: number; with_chain_breaks: number; truncated: number;
  grid: { latencies: number[]; exits: Record<string, [number | null, number | null, number | null]>; size: number };
  cells: Record<string, Record<string, SnipeCell>>;
  prereg: SnipeCell & { since: number; explore_until: number; cell: string; min_n: number; robust: Record<string, number | null>; verdict: string; top1pct_share?: number | null };
  lottery?: { tickets: number; graduated_waiting: number; p_touch_10x: number | null; p_touch_100x: number | null; n_touch_10x: number; n_touch_100x: number };
  creates_24h_census?: number; creates_24h_portal?: number; recorder?: SniperRecorderStats | null;
};

type Bucket = { range: [number | null, number | null]; n: number; median?: number; mean?: number; win?: number; rug?: number; mean_early?: number | null; mean_late?: number | null };
type ExploreSample = { all: { n: number; median?: number; mean?: number; win?: number; rug?: number }; features: Record<string, { n: number; buckets: Bucket[] | null }> };
type ExploreC = { population: string; cell: string; window: [number, number]; samples: Record<string, ExploreSample> };
type ExploreS = { window: [number, number]; cells: string[]; samples: Record<string, Record<string, ExploreSample>> };
type GCell = { n: number; mean?: number; mean_ci95?: [number, number] | null; median?: number; win_rate?: number; rug_share?: number };
type GLevel = { reached: number; grad: number; fail: number; jump: number; unresolved: number; exit_waiting: number; p_grad_given_ticket: number | null; cells: Record<string, GCell> };
type Graduation = { levels: Record<string, GLevel>; prereg: GCell & { since: number; level: number; exit: string; min_n: number; robust_means: (number | null)[]; verdict: string } };

const num = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toPrecision(2));
const rangeLabel = ([lo, hi]: [number | null, number | null]) =>
  lo !== null && lo === hi ? `= ${num(lo)}` : lo === null ? `< ${num(hi ?? 0)}` : hi === null ? `≥ ${num(lo)}` : `${num(lo)} … ${num(hi)}`;

function FeatureTable({ sample }: { sample?: ExploreSample }) {
  if (!sample || !sample.all.n) return <p className="k">Chưa có dòng nào trong mẫu này.</p>;
  const rows = Object.entries(sample.features).filter(([, f]) => f.buckets && f.buckets.length > 0);
  const a = sample.all;
  return (
    <>
      <p className="k">{`Toàn mẫu: n=${a.n} · trung vị ${signed(a.median)} · trung bình ${signed(a.mean)} · thắng ${pct(a.win, 0)} · mất gần hết ${pct(a.rug, 0)}`}</p>
      <table>
        <thead><tr><th>Đặc trưng</th><th>n</th><th>nhóm 1</th><th>nhóm 2</th><th>nhóm 3</th></tr></thead>
        <tbody>
          {rows.map(([name, f]) => (
            <tr key={name}>
              <td className="mono">{name}</td><td>{f.n}</td>
              {(f.buckets ?? []).map((b, i) => (
                <td key={i}>
                  <span className="k">{rangeLabel(b.range)} · n={b.n}</span><br />
                  med <span className={cls(b.median)}>{signed(b.median)}</span> · TB <span className={cls(b.mean)}>{signed(b.mean)}</span> · rug {pct(b.rug, 0)}<br />
                  <span className="k">TB nửa đầu/nửa sau: {signed(b.mean_early ?? undefined)} / {signed(b.mean_late ?? undefined)}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

const pct = (v?: number | null, d = 1) => (v === undefined || v === null || !Number.isFinite(v) ? "–" : `${(v * 100).toFixed(d)}%`);
const signed = (v?: number) => (v === undefined || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`);
const time = (ts: number) => new Date(ts * 1000).toLocaleString();
const short = (m: string) => `${m.slice(0, 4)}…${m.slice(-4)}`;
const cls = (v?: number) => (v === undefined ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

export default function Page() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [migs, setMigs] = useState<Migration[]>([]);
  const [sum, setSum] = useState<Summary | null>(null);
  const [cfg, setCfg] = useState<Config | null>(null);
  const [files, setFiles] = useState<DataFile[]>([]);
  const [sn, setSn] = useState<Sniper | null>(null);
  const [exC, setExC] = useState<ExploreC | null>(null);
  const [exS, setExS] = useState<ExploreS | null>(null);
  const [exSample, setExSample] = useState<"window" | "before">("window");
  const [grad, setGrad] = useState<Graduation | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const [s, m, su, c] = await Promise.all([
          fetch(`${API}/stats`).then((r) => r.json()),
          fetch(`${API}/migrations?limit=30`).then((r) => r.json()),
          fetch(`${API}/survivor/summary`).then((r) => r.json()),
          fetch(`${API}/config`).then((r) => r.json()),
        ]);
        if (!alive) return;
        setStats(s); setMigs(m); setSum(su); setCfg(c); setErr(null);
        fetch(`${API}/files`).then((r) => r.json()).then((f) => { if (alive) setFiles(f.files ?? []); }).catch(() => {});
        fetch(`${API}/sniper/summary`).then((r) => r.json()).then((x) => { if (alive) setSn(x); }).catch(() => {});
        fetch(`${API}/survivor/explore`).then((r) => r.json()).then((x) => { if (alive) setExC(x); }).catch(() => {});
        fetch(`${API}/sniper/explore`).then((r) => r.json()).then((x) => { if (alive) setExS(x); }).catch(() => {});
        fetch(`${API}/graduation/summary`).then((r) => r.json()).then((x) => { if (alive) setGrad(x); }).catch(() => {});
      } catch (e) {
        if (alive) setErr(`Không kết nối được API tại ${API}: ${String(e)}`);
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const now = Date.now() / 1000;
  // On-chain data arrives via the websocket feed or via RPC confirmation of PumpPortal
  // migrations; either one being fresh means we are getting slots + pools from chain.
  const lastOnChain = Math.max(stats?.status.last_chain_ts ?? 0, stats?.status.rpc?.last_rpc_ts ?? 0);
  const chainOk = lastOnChain > now - 15 * 60; // migrations are ~1/min, be patient
  const portalOk = (stats?.status.last_portal_ts ?? 0) > now - 120;
  const verdict = sum?.verdict.status ?? "…";
  const verdictFill = sum?.verdict_fill?.status ?? "…";
  const primarySize = sum?.fill_primary_size ?? "1";
  const fillGrid = sum?.fills?.[primarySize];
  const full = stats?.chain_scope === "full";
  const feed = stats?.status.chain_feed;
  const portal = stats?.status.portal_feed;
  const rpc = stats?.status.rpc;
  const mentions = stats?.status.mentions ?? [];
  const signer = Object.entries(rpc?.migrate_users ?? {}).sort((a, b) => b[1] - a[1])[0];
  const signerTotal = Object.values(rpc?.migrate_users ?? {}).reduce((a, b) => a + b, 0);
  const pools = Object.entries(stats?.status.portal_pools ?? {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(" · ");
  const hv = stats?.status.harvest;
  const gk = stats?.status.gecko;
  const mb = (b: number) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${(b / 1024).toFixed(0)} KB`);

  return (
    <main>
      <h1>
        pumphunt <span className="badge">recorder · {stats?.chain_scope ?? "…"}</span>
        <span className="badge mono" title={stats?.build_sha}>build {stats?.build_sha ? stats.build_sha.slice(0, 7) : "…"}</span>
        <span className={`badge ${chainOk ? "ok" : "bad"}`}>on‑chain {chainOk ? "ok" : "no data"}</span>
        <span className={`badge ${portalOk ? "ok" : "bad"}`}>pumpportal {portalOk ? "ok" : "no data"}</span>
      </h1>
      {err && <p className="err">{err}</p>}

      <div className="tiles">
        <div className="tile"><div className="k">Token tạo mới / 24h {full ? "(on‑chain)" : "(PumpPortal)"}</div><div className="v">{stats?.creates_24h ?? "–"}</div></div>
        <div className="tile"><div className="k">Graduation / 24h (xác nhận on‑chain)</div><div className="v">{stats?.migrations_24h ?? "–"} <span className="k">/ {stats?.migrations_total ?? 0} tổng</span></div></div>
        <div className="tile"><div className="k">Graduation / 24h (PumpPortal)</div><div className="v">{stats?.migrations_24h_portal ?? "–"}</div></div>
        <div className="tile"><div className="k">Đã harvest nến</div><div className="v">{sum?.harvested ?? 0} <span className="k">alive 24h {pct(sum?.alive_24h_rate, 0)}</span></div></div>
        <div className={`tile verdict ${verdictFill.toLowerCase()}`}><div className="k">Giả thuyết C, khớp lệnh thật {primarySize} SOL (T+30m → 1h)</div><div className="v">{verdictFill}</div><div className="k">{sum?.verdict_fill?.why}</div></div>
        <div className={`tile verdict ${verdict.toLowerCase()}`}><div className="k">Giả thuyết C, theo nến −3.5% (T+30m → 1h)</div><div className="v">{verdict}</div><div className="k">{sum?.verdict.why}</div></div>
      </div>

      <h2>Khớp lệnh thật trên reserve on‑chain (net sau trượt giá + phí pool + phí tx, {primarySize} SOL)</h2>
      <table>
        <thead>
          <tr><th>Vào tại</th>{cfg?.horizons_min.map((h) => <th key={h}>giữ {h >= 60 ? `${h / 60}h` : `${h}m`}</th>)}</tr>
        </thead>
        <tbody>
          {cfg?.entry_delays_min.map((d) => (
            <tr key={d}>
              <td>T+{d}m</td>
              {cfg.horizons_min.map((h) => {
                const c = fillGrid?.[`d${d}_h${h}`];
                return (
                  <td key={h}>
                    {c && c.n > 0 ? (
                      <>n={c.n} · med <span className={cls(c.median)}>{signed(c.median)}</span> · wr {pct(c.win_rate, 0)} · top2% {pct(c.top2pct_share, 0)}</>
                    ) : <span className="k">n=0</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <table>
        <thead><tr><th>Cỡ lệnh (T+30m → 1h)</th><th>n</th><th>median net</th><th>thắng</th><th>p10</th><th>p90</th></tr></thead>
        <tbody>
          {Object.entries(sum?.fills ?? {}).map(([size, grid]) => {
            const c = grid["d30_h60"];
            return (
              <tr key={size}><td>{size} SOL</td><td>{c?.n ?? 0}</td><td className={cls(c?.median)}>{signed(c?.median)}</td><td>{pct(c?.win_rate, 0)}</td><td>{signed(c?.p10)}</td><td>{signed(c?.p90)}</td></tr>
            );
          })}
        </tbody>
      </table>

      <h2>Giả thuyết đăng ký trước (chỉ dữ liệu sau thời điểm đăng ký mới được dùng để kiểm định)</h2>
      <table>
        <thead><tr><th>Giả thuyết</th><th>Tập con</th><th>từ</th><th>n</th><th>median net</th><th>KTC 95% median</th><th>trung bình</th><th>mất gần hết</th><th>thắng</th><th>top 2%</th><th>Kết luận</th></tr></thead>
        <tbody>
          {(sum?.prereg?.hypotheses ?? []).map((h) => (
            <tr key={h.name}>
              <td className="mono">{h.name}</td><td>{h.desc}</td>
              <td>{h.since ? new Date(h.since * 1000).toISOString().slice(0, 16).replace("T", " ") : "đầu"}</td>
              <td>{h.n ?? 0}{h.since ? ` / ${h.eligible}` : ""}</td>
              <td className={cls(h.median ?? undefined)}>{signed(h.median ?? undefined)}</td>
              <td>{h.median_ci95 ? `${signed(h.median_ci95[0])} … ${signed(h.median_ci95[1])}` : "–"}</td>
              <td className={cls(h.mean ?? undefined)}>{signed(h.mean ?? undefined)}</td><td>{pct(h.rug_share, 0)}</td>
              <td>{pct(h.win_rate, 0)}</td><td>{pct(h.top2pct_share, 0)}</td>
              <td className="mono">{h.verdict?.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="k">{sum?.prereg ? `Ô ${sum.prereg.cell}, ${sum.prereg.size} SOL, net khớp lệnh thật. C2: ≥ ${sum.prereg.c2.min_real_sol} SOL thật trong pool và có swap trong ${sum.prereg.c2.max_idle_s} giây trước lúc quyết định (đo đúng T+30, chưa tính độ trễ). Luật dựa trên đặc trưng chỉ được chọn trên dữ liệu tới ${new Date(sum.prereg.explore_until * 1000).toISOString().slice(0, 10)}, rồi kiểm định trên dữ liệu sau khi đăng ký luật. Chi tiết: docs/PREREG.md.` : ""}</p>

      <h2>Ba cách tính thực thi cho ô quyết định ({primarySize} SOL, T+30m → 1h)</h2>
      <table>
        <thead><tr><th>Mô hình</th><th>Giả định</th><th>n</th><th>median net</th><th>thắng</th><th>p10</th><th>p90</th></tr></thead>
        <tbody>
          {([
            ["net_ghost", "Bi quan: thị trường quên lệnh mua của mình, bán vào trạng thái thật"],
            ["net_replay", "Chính: chèn lệnh vào chuỗi swap thật, chạy lại từng swap sau đó"],
            ["net_persist", "Lạc quan: tác động giá của mình giữ nguyên tới lúc bán"],
          ] as const).map(([k, label]) => {
            const m = sum?.fill_models?.[k];
            return (
              <tr key={k}><td className="mono">{k.replace("net_", "")}</td><td>{label}</td><td>{m?.n ?? 0}</td><td className={cls(m?.median)}>{signed(m?.median)}</td><td>{pct(m?.win_rate, 0)}</td><td>{signed(m?.p10)}</td><td>{signed(m?.p90)}</td></tr>
            );
          })}
        </tbody>
      </table>
      <p className="k">{`Lệnh bán bị chặn ở lượng SOL thật trong pool: ${pct(sum?.fill_models?.exit_capped_share, 0)} số lệnh · phát lại được: ${pct(sum?.fill_models?.replayed_share, 0)} · các dòng tính bằng mô hình cũ không được đưa vào bảng.`}</p>

      <h2>Chia theo điều kiện lúc vào (thăm dò, chọn sau khi đã xem dữ liệu, không phải kiểm định)</h2>
      <div className="tiles">
        {([["real_in_sol", "SOL thật trong pool lúc vào"], ["idle_at_entry", "Pool đã đứng yên bao lâu lúc vào"]] as const).map(([k, label]) => (
          <div className="tile" key={k} style={{ flex: "1 1 360px" }}>
            <div className="k">{label}</div>
            <table>
              <thead><tr><th>Nhóm</th><th>n</th><th>median</th><th>thắng</th><th>p90</th></tr></thead>
              <tbody>
                {(sum?.fill_strata?.[k] ?? []).map((r) => (
                  <tr key={r.bucket}><td>{r.bucket}</td><td>{r.n ?? 0}</td><td className={cls(r.median)}>{signed(r.median)}</td><td>{pct(r.win_rate, 0)}</td><td>{signed(r.p90)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      <h2>Sniper: mua vài slot sau khi token ra đời (giả thuyết S, docs/SNIPER.md)</h2>
      <div className="tiles">
        <div className={`tile verdict ${(sn?.prereg.verdict ?? "").toLowerCase()}`}>
          <div className="k">{`S: vào cuối slot tạo+2, ${sn?.grid.size ?? 0.5} SOL, chốt x2 / cắt 50% / bán sau 60 giây, token classic từ ${sn ? new Date(sn.prereg.since * 1000).toISOString().slice(0, 16).replace("T", " ") : "…"}`}</div>
          <div className="v">{sn?.prereg.verdict ?? "…"}</div>
          <div className="k">{`n=${sn?.prereg.n ?? 0} / ${sn?.prereg.min_n ?? 2000} · EV ${signed(sn?.prereg.mean)}${sn?.prereg.mean_ci95 ? ` (KTC 95% ${signed(sn.prereg.mean_ci95[0])} … ${signed(sn.prereg.mean_ci95[1])})` : ""} · thắng ${pct(sn?.prereg.win_rate, 0)}`}</div>
        </div>
        <div className="tile">
          <div className="k">Census on‑chain (mint authority) / 24h</div>
          <div className="v">{sn?.creates_24h_census ?? "–"} <span className="k">PumpPortal {sn?.creates_24h_portal ?? "–"}</span></div>
          <div className="k">{`lấy mẫu ${cfg?.sniper_sample_per_10k ? cfg.sniper_sample_per_10k / 100 : "–"}% · đã đọc ${sn?.recorder?.harvested ?? 0} (không phải SOL ${sn?.recorder?.not_sol ?? 0}) · chờ ${sn?.recorder?.queued ?? 0} · credit hôm nay ${sn?.recorder?.credits_today ?? 0}${cfg?.sniper_daily_credits ? ` / ${cfg.sniper_daily_credits}` : ""}${sn?.recorder?.paused ? " · TẠM DỪNG" : ""}`}</div>
          <div className="k">{`launch có đường giá: ${sn?.classic ?? 0} classic · ${sn?.mayhem ?? 0} mayhem · ${sn?.graduated ?? 0} tốt nghiệp · đứt chuỗi ${sn?.with_chain_breaks ?? 0} · bị cắt ${sn?.truncated ?? 0}`}</div>
          <div className="k mono">{sn?.recorder?.last_error ?? ""}</div>
        </div>
        <div className="tile">
          <div className="k">Vé xổ số (giữ từ slot +2, thăm dò)</div>
          <div className="v">{sn?.lottery ? `${sn.lottery.n_touch_100x} chạm x100` : "–"}</div>
          <div className="k">{sn?.lottery ? `trên ${sn.lottery.tickets} vé · chạm x10: ${pct(sn.lottery.p_touch_10x, 2)} · x100: ${pct(sn.lottery.p_touch_100x, 3)} · ${sn.lottery.graduated_waiting} token tốt nghiệp chờ nến pool` : ""}</div>
          <div className="k">Chạm = đỉnh nến 5 phút, không phải giá bán được.</div>
        </div>
      </div>
      <table>
        <thead><tr><th>Thoát (classic, mọi mẫu, thăm dò)</th>{(sn?.grid.latencies ?? []).map((k) => <th key={k}>slot +{k}</th>)}</tr></thead>
        <tbody>
          {Object.keys(sn?.grid.exits ?? {}).map((e) => (
            <tr key={e}>
              <td className="mono">{e}</td>
              {(sn?.grid.latencies ?? []).map((k) => {
                const c = sn?.cells.classic?.[`k${k}_${e}`];
                return <td key={k}>{c && c.n > 0 ? <>EV <span className={cls(c.mean)}>{signed(c.mean)}</span> · wr {pct(c.win_rate, 0)} · n={c.n}</> : <span className="k">n=0</span>}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="k">EV là lãi/lỗ trung bình mỗi vé sau phí 1.25% mỗi chiều và 0.002 SOL phí ưu tiên/tip; slot ≈ 0.27 giây. p = chốt x2 / cắt 50% / bán sau 60 giây; tpN = chốt xN, nếu không thì giữ tới tốt nghiệp hoặc hết cửa sổ 2 giờ; tN = bán sau N giây; hold = giữ.</p>

      <h2>Graduation run: mua khi curve đã ở ≥ X SOL, bán 3 giây sau migration (giả thuyết G, docs/SNIPER.md mục 8)</h2>
      <div className="tiles">
        <div className={`tile verdict ${(grad?.prereg.verdict ?? "").toLowerCase()}`}>
          <div className="k">{`G: vào khi curve chạm ${grad?.prereg.level ?? 60} SOL, 0,5 SOL, bán 3 giây sau migration · launch classic từ ${grad ? new Date(grad.prereg.since * 1000).toISOString().slice(0, 16).replace("T", " ") : "…"}`}</div>
          <div className="v">{grad?.prereg.verdict ?? "…"}</div>
          <div className="k">{`n=${grad?.prereg.n ?? 0} / ${grad?.prereg.min_n ?? 300} · EV ${signed(grad?.prereg.mean)}${grad?.prereg.mean_ci95 ? ` (KTC 95% ${signed(grad.prereg.mean_ci95[0])} … ${signed(grad.prereg.mean_ci95[1])})` : ""} · thắng ${pct(grad?.prereg.win_rate, 0)} · mất gần hết ${pct(grad?.prereg.rug_share, 0)}`}</div>
        </div>
      </div>
      <table>
        <thead><tr><th>Mức kích hoạt</th><th>chạm</th><th>có vé (tốt nghiệp / thất bại)</th><th>nhảy qua, không vào kịp</th><th>P(tốt nghiệp | có vé)</th><th>bán 3 giây sau migration</th><th>bán 5 phút sau</th></tr></thead>
        <tbody>
          {Object.entries(grad?.levels ?? {}).map(([lv, g]) => (
            <tr key={lv}>
              <td>{lv} SOL</td><td>{g.reached}</td><td>{g.grad} / {g.fail}{g.exit_waiting ? ` (${g.exit_waiting} chờ pool)` : ""}</td>
              <td>{g.jump}</td><td>{pct(g.p_grad_given_ticket, 0)}</td>
              {(["t3s", "t5m"] as const).map((w) => {
                const c = g.cells[w];
                return <td key={w}>{c && c.n > 0 ? <>EV <span className={cls(c.mean)}>{signed(c.mean)}</span> · med {signed(c.median)} · wr {pct(c.win_rate, 0)} · n={c.n}</> : <span className="k">n=0</span>}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Thăm dò luật đặc trưng (nơi tìm luật, KHÔNG phải kiểm định)</h2>
      <p className="k">
        Mẫu:{" "}
        <button onClick={() => setExSample("window")} disabled={exSample === "window"}>cửa sổ thăm dò đã đăng ký</button>{" "}
        <button onClick={() => setExSample("before")} disabled={exSample === "before"}>trước thời điểm đăng ký</button>
        {" · "}Luật chỉ được đăng ký khi trung bình (không chỉ trung vị) dương ở cả hai nửa: trung vị giấu đuôi rug (docs/RESEARCH.md).
      </p>
      <h3>{`C2: vào T+30 → giữ 1h, 1 SOL, khớp lệnh thật${exC ? ` (cửa sổ ${new Date(exC.window[0] * 1000).toISOString().slice(0, 10)} → ${new Date(exC.window[1] * 1000).toISOString().slice(0, 10)})` : ""}`}</h3>
      <FeatureTable sample={exC?.samples[exSample]} />
      <h3>{`Sniper: vé classic ở slot tạo+2, luật p (chốt x2 / cắt 50% / bán sau 60s)${exS ? ` (cửa sổ ${new Date(exS.window[0] * 1000).toISOString().slice(0, 10)} → ${new Date(exS.window[1] * 1000).toISOString().slice(0, 10)})` : ""}`}</h3>
      <FeatureTable sample={exS?.samples[exSample]?.[exS.cells[0]]} />

      <h2>Harvester &amp; dữ liệu</h2>
      <div className="tiles">
        <div className="tile">
          <div className="k">Harvester (GeckoTerminal, sau 25h)</div>
          <div className="v">{hv?.pending ?? 0} <span className="k">chờ · {hv?.due ?? 0} tới hạn · {hv?.runs ?? 0} chu kỳ</span></div>
          <div className="k">{`có nến ${hv?.with_data ?? 0} · không giao dịch ${hv?.no_candles ?? 0} · không pool ${hv?.no_pool ?? 0}`}{hv?.last_run_ts ? ` · chạy cuối ${Math.max(0, Math.round((now - hv.last_run_ts) / 60))} phút trước` : ""}</div>
          <div className="k">{`Gecko ${gk?.calls ?? 0} call · ${gk?.rate_limited ?? 0} lần 429 · ${gk?.not_found ?? 0} không có`}</div>
          <div className="k">{`Fills: ${hv?.fills_rows ?? 0} token có swap · ${hv?.swaps_fetched ?? 0} swap · credit RPC hôm nay ${hv?.credits_today ?? 0}${cfg?.fills_daily_credits ? ` / ${cfg.fills_daily_credits}` : ""}${hv?.fills_paused ? " · TẠM DỪNG (hết ngân sách)" : ""}`}</div>
          <div className="k">{`getTransactionsForAddress: ${hv?.gtfa === true ? "đang dùng" : hv?.gtfa === false ? "không có, dùng đường dự phòng" : "chưa thử"} · cửa sổ phát lại ${hv?.replay_windows ?? 0} · bị cắt ${hv?.window_incomplete ?? 0}`}</div>
          {hv?.gtfa_error && <div className="k mono">{hv.gtfa_error}</div>}
          <div className="k">{`Cửa sổ đủ nhưng đứt chuỗi (thiếu swap) ${hv?.windows_with_breaks ?? 0} · token có order flow ${hv?.flow_rows ?? 0} · thời điểm chưa tìm được swap ${hv?.states_unresolved ?? 0}`}</div>
          <div className="k">{`Snapshot holder đúng giờ (T+30/T+60): ${stats?.status.snapshots?.taken ?? 0} đã chụp · ${stats?.status.snapshots?.late ?? 0} trễ, bỏ · ${stats?.status.snapshots?.errors ?? 0} lỗi · ${stats?.status.snapshots?.queued ?? 0} đang chờ`}</div>
          <div className="k">{`Đặc trưng: ${hv?.features_rows ?? 0} token có lịch sử bonding curve · ${hv?.funding_rows ?? 0} token tra nguồn tiền (${hv?.funding_lookups ?? 0} ví tra qua RPC)`}</div>
          {(stats?.status.snapshots?.last_error || hv?.features_error) && <div className="k mono">{[stats?.status.snapshots?.last_error, hv?.features_error].filter(Boolean).join(" · ")}</div>}
          <div className="k">{`Bộ lọc tokenTransfer (bỏ giao dịch bot không swap): ${hv?.token_filter === true ? "đã kiểm chứng, đang dùng" : hv?.token_filter === false ? "tắt" : "đang kiểm chứng"}${hv?.token_filter_note ? ` · ${hv.token_filter_note}` : ""}${hv?.token_filter_checks?.repaired ? ` · đã đọc lại ${hv.token_filter_checks.repaired} swap bộ lọc bỏ sót` : ""}`}</div>
          <div className="k mono">{hv?.last_error ?? ""}</div>
        </div>
        <div className="tile">
          <div className="k">Dữ liệu trên volume</div>
          <div className="v">{files.length} <span className="k">file · {mb(files.reduce((a, f) => a + f.bytes, 0))}</span></div>
          <div className="k mono">{files.slice().sort((a, b) => b.mtime - a.mtime).slice(0, 4).map((f) => `${f.name} ${mb(f.bytes)}`).join(" · ")}</div>
        </div>
        <div className="tile">
          <div className="k">Xuất dữ liệu</div>
          <div className="k"><a href={`${API}/export/survivor.csv`}>survivor.csv</a> · <a href={`${API}/export/survivor.jsonl`}>survivor.jsonl</a> · <a href={`${API}/export/migrations.jsonl`}>migrations.jsonl</a> · <a href={`${API}/sniper/rows?limit=5000`}>sniper rows</a></div>
          <div className="k">{sum?.no_data ? `không dữ liệu: ${Object.entries(sum.no_data).map(([k, v]) => `${k} ${v}`).join(" · ") || "0"}` : ""}</div>
        </div>
      </div>

      <h2>Feed on‑chain</h2>
      <div className="tiles">
        <div className="tile"><div className="k">WebSocket Solana</div><div className="v">{feed ? (feed.connected ? "connected" : "down") : "–"} <span className="k">· {feed?.connects ?? 0} lần nối · {feed?.stale_reconnects ?? 0} vì im lặng · {feed?.subscribed ?? 0} sub</span></div><div className="k mono">{feed?.last_error ?? ""}</div></div>
        <div className="tile"><div className="k">WebSocket PumpPortal</div><div className="v">{portal ? (portal.connected ? "connected" : "down") : "–"} <span className="k">· {portal?.connects ?? 0} lần nối · {portal?.stale_reconnects ?? 0} vì im lặng</span></div><div className="k">{pools ? `migration theo nền tảng: ${pools}` : ""}</div><div className="k mono">{portal?.last_error ?? ""}</div></div>
        <div className="tile"><div className="k">Notification / event decode</div><div className="v">{feed?.notifications ?? 0} <span className="k">/ {feed?.events ?? 0}</span></div></div>
        <div className="tile">
          <div className="k">Poller getSignaturesForAddress (nguồn chính)</div>
          <div className="v">{rpc?.poller?.polls ?? 0} <span className="k">lần · {rpc?.poller?.listed ?? 0} tx liệt kê · {rpc?.poller?.skipped_failed ?? 0} tx lỗi bỏ qua</span></div>
          <div className="k">{rpc?.poller?.last_poll_ts ? `lần cuối ${Math.max(0, Math.round(now - rpc.poller.last_poll_ts))}s trước` : "chưa chạy"}{rpc?.poller?.cursor ? ` · cursor ${short(rpc.poller.cursor)}` : ""}{rpc?.portal_mislabeled ? ` · PumpPortal gán sai mint ${rpc.portal_mislabeled}` : ""}</div>
          <div className="k mono">{rpc?.poller?.last_error ?? ""}</div>
        </div>
        <div className="tile">
          <div className="k">RPC confirm (getTransaction)</div>
          <div className="v">{rpc?.confirmed ?? 0} <span className="k">ok · {rpc?.failed ?? 0} fail · {rpc?.no_event ?? 0} no‑event · {rpc?.noop ?? 0} no‑op (bot thua cuộc)</span></div>
          <div className="k">{`đang chờ thử lại ${rpc?.retry_pending ?? 0} · bỏ cuộc ${rpc?.failed_final ?? 0} · RPC ${rpc?.transport?.calls ?? 0} call, ${rpc?.transport?.rate_limited ?? 0} lần 429`}{rpc?.last_failed?.signature ? ` · lỗi gần nhất ${short(rpc.last_failed.signature)}: ${rpc.last_failed.error}` : ""}</div>
          <div className="k">{rpc?.triggered ? `kích hoạt bởi poller ${rpc.triggered.poller ?? 0} · websocket ${rpc.triggered.chain ?? 0} · pumpportal ${rpc.triggered.portal ?? 0}` : ""}</div>
          <div className="k">{rpc?.via ? `nhận qua log ${rpc.via.log ?? 0} · cpi ${rpc.via.cpi ?? 0} · accounts ${rpc.via.accounts ?? 0}` : ""}</div>
          {rpc?.last_no_event?.signature && (
            <div className="k mono">
              no‑event gần nhất: <a href={`https://solscan.io/tx/${rpc.last_no_event.signature}`} target="_blank" rel="noreferrer">{short(rpc.last_no_event.signature)}</a>
              {" · "}log {rpc.last_no_event.log_truncated ? "bị cắt" : "đủ"}
              {" · "}ix pump: {(rpc.last_no_event.pump_ixs ?? []).map((i) => i.name ?? i.disc.slice(0, 8)).join(", ") || "không có"}
            </div>
          )}
        </div>
        <div className="tile">
          <div className="k">withdraw_authority ({rpc?.migrate_ix ?? "?"})</div>
          <div className="v mono" style={{ fontSize: 13, wordBreak: "break-all" }}>{rpc?.withdraw_authority ?? "chưa học"}</div>
          <div className="k">{rpc?.authority_static === false ? "lần gần nhất nạp qua lookup table, websocket không thấy tx đó" : ""}</div>
          <div className="k">{signer ? `ký migrate nhiều nhất: ${short(signer[0])} (${signer[1]}/${signerTotal})${mentions.includes(signer[0]) ? ", đã subscribe" : ""}` : ""}</div>
          <div className="k">đang subscribe: {mentions.map(short).join(", ")}</div>
        </div>
      </div>

      <h2>Return net (chi phí {cfg ? (cfg.cost_bps_round_trip / 100).toFixed(2) : "–"}% round‑trip) theo thời điểm vào × thời gian giữ</h2>
      <table>
        <thead>
          <tr><th>Vào tại</th>{cfg?.horizons_min.map((h) => <th key={h}>giữ {h >= 60 ? `${h / 60}h` : `${h}m`}</th>)}</tr>
        </thead>
        <tbody>
          {cfg?.entry_delays_min.map((d) => (
            <tr key={d}>
              <td>T+{d}m</td>
              {cfg.horizons_min.map((h) => {
                const c = sum?.cells[`d${d}_h${h}`];
                return (
                  <td key={h}>
                    {c && c.n > 0 ? (
                      <>n={c.n} · med <span className={cls(c.median)}>{signed(c.median)}</span> · wr {pct(c.win_rate, 0)} · top2% {pct(c.top2pct_share, 0)}</>
                    ) : <span className="k">n=0</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Graduation gần đây</h2>
      <table>
        <thead><tr><th>Lúc</th><th>Mint</th><th>Pool</th><th>Slot</th><th>Vốn vào pool (SOL, hoặc quote khác)</th><th>Nguồn</th><th>Harvest</th></tr></thead>
        <tbody>
          {migs.length === 0 && <tr><td colSpan={7} className="empty">Chưa ghi được migration nào</td></tr>}
          {migs.map((m) => (
            <tr key={m.mint}>
              <td>{time(m.ts)}</td>
              <td className="mono"><a href={`https://solscan.io/token/${m.mint}`} target="_blank" rel="noreferrer">{short(m.mint)}</a></td>
              <td className="mono">{m.pool ? short(m.pool) : <span className="k">chưa rõ</span>}</td>
              <td>{m.slot ?? "–"}</td>
              <td>{m.sol_amount !== undefined && m.sol_amount !== null ? `${m.sol_amount.toFixed(2)}${m.quote_mint && !SOL_QUOTES.has(m.quote_mint) ? ` ${short(m.quote_mint)}` : ""}` : "–"}</td>
              <td>{m.source ?? "–"}</td>
              <td>{m.harvested ? "✓" : "chờ 25h"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Theo giờ (24h)</h2>
      <table>
        <thead><tr><th>Giờ (UTC)</th><th>Create on‑chain</th><th>Create PumpPortal</th><th>Graduation on‑chain</th><th>Graduation PumpPortal</th></tr></thead>
        <tbody>
          {stats?.hourly.slice().reverse().map((h) => (
            <tr key={h.hour}><td>{h.hour}</td><td>{full ? h.creates_chain : "–"}</td><td>{h.creates_portal}</td><td>{h.migrations}</td><td>{h.migrations_portal}</td></tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
