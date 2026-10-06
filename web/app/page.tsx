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
    harvest?: Harvest | null; gecko?: Gecko | null;
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
const WSOL = "So11111111111111111111111111111111111111112";
type Cell = { n: number; median?: number; win_rate?: number; top2pct_share?: number; p10?: number; p90?: number };
type Harvest = { runs?: number; last_run_ts?: number; last_error?: string | null; rows_last_run?: number; with_data?: number; no_pool?: number; no_candles?: number; due?: number; pending?: number };
type Gecko = { calls?: number; rate_limited?: number; not_found?: number; errors?: number };
type DataFile = { name: string; bytes: number; mtime: number };
type Summary = {
  harvested: number; with_data: number; alive_24h_rate: number; no_data?: Record<string, number>;
  cells: Record<string, Cell>; verdict: { status: string; why: string };
};
type Config = { entry_delays_min: number[]; horizons_min: number[]; cost_bps_round_trip: number };

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
        <div className={`tile verdict ${verdict.toLowerCase()}`}><div className="k">Giả thuyết C (T+30m → 1h)</div><div className="v">{verdict}</div><div className="k">{sum?.verdict.why}</div></div>
      </div>

      <h2>Harvester &amp; dữ liệu</h2>
      <div className="tiles">
        <div className="tile">
          <div className="k">Harvester (GeckoTerminal, sau 25h)</div>
          <div className="v">{hv?.pending ?? 0} <span className="k">chờ · {hv?.due ?? 0} tới hạn · {hv?.runs ?? 0} chu kỳ</span></div>
          <div className="k">{`có nến ${hv?.with_data ?? 0} · không giao dịch ${hv?.no_candles ?? 0} · không pool ${hv?.no_pool ?? 0}`}{hv?.last_run_ts ? ` · chạy cuối ${Math.max(0, Math.round((now - hv.last_run_ts) / 60))} phút trước` : ""}</div>
          <div className="k">{`Gecko ${gk?.calls ?? 0} call · ${gk?.rate_limited ?? 0} lần 429 · ${gk?.not_found ?? 0} không có`}</div>
          <div className="k mono">{hv?.last_error ?? ""}</div>
        </div>
        <div className="tile">
          <div className="k">Dữ liệu trên volume</div>
          <div className="v">{files.length} <span className="k">file · {mb(files.reduce((a, f) => a + f.bytes, 0))}</span></div>
          <div className="k mono">{files.slice().sort((a, b) => b.mtime - a.mtime).slice(0, 4).map((f) => `${f.name} ${mb(f.bytes)}`).join(" · ")}</div>
        </div>
        <div className="tile">
          <div className="k">Xuất dữ liệu</div>
          <div className="k"><a href={`${API}/export/survivor.csv`}>survivor.csv</a> · <a href={`${API}/export/survivor.jsonl`}>survivor.jsonl</a> · <a href={`${API}/export/migrations.jsonl`}>migrations.jsonl</a></div>
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
              <td>{m.sol_amount !== undefined && m.sol_amount !== null ? `${m.sol_amount.toFixed(2)}${m.quote_mint && m.quote_mint !== WSOL ? ` ${short(m.quote_mint)}` : ""}` : "–"}</td>
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
