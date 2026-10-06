"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type Stats = {
  status: { now?: number; last_chain_ts?: number; last_portal_ts?: number; counts?: Record<string, number> };
  creates_24h_chain: number;
  creates_24h_portal: number;
  portal_coverage: number | null;
  migrations_24h: number;
  migrations_total: number;
  hourly: { hour: string; creates_chain: number; creates_portal: number; migrations: number }[];
};
type Migration = { mint: string; pool: string; ts: number; slot: number; sol_amount: number; harvested: boolean };
type Cell = { n: number; median?: number; win_rate?: number; top2pct_share?: number; p10?: number; p90?: number };
type Summary = {
  harvested: number; with_data: number; alive_24h_rate: number;
  cells: Record<string, Cell>; verdict: { status: string; why: string };
};
type Config = { entry_delays_min: number[]; horizons_min: number[]; cost_bps_round_trip: number };

const pct = (v?: number, d = 1) => (v === undefined || v === null || !Number.isFinite(v) ? "–" : `${(v * 100).toFixed(d)}%`);
const signed = (v?: number) => (v === undefined || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`);
const time = (ts: number) => new Date(ts * 1000).toLocaleString();
const short = (m: string) => `${m.slice(0, 4)}…${m.slice(-4)}`;
const cls = (v?: number) => (v === undefined ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

export default function Page() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [migs, setMigs] = useState<Migration[]>([]);
  const [sum, setSum] = useState<Summary | null>(null);
  const [cfg, setCfg] = useState<Config | null>(null);
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
      } catch (e) {
        if (alive) setErr(`Không kết nối được API tại ${API}: ${String(e)}`);
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const now = Date.now() / 1000;
  const chainOk = (stats?.status.last_chain_ts ?? 0) > now - 60;
  const portalOk = (stats?.status.last_portal_ts ?? 0) > now - 120;
  const verdict = sum?.verdict.status ?? "…";

  return (
    <main>
      <h1>
        pumphunt <span className="badge">recorder</span>
        <span className={`badge ${chainOk ? "ok" : "bad"}`}>chain feed {chainOk ? "ok" : "no data"}</span>
        <span className={`badge ${portalOk ? "ok" : "bad"}`}>pumpportal {portalOk ? "ok" : "no data"}</span>
      </h1>
      {err && <p className="err">{err}</p>}

      <div className="tiles">
        <div className="tile"><div className="k">Token tạo mới / 24h (on‑chain)</div><div className="v">{stats?.creates_24h_chain ?? "–"}</div></div>
        <div className="tile"><div className="k">PumpPortal coverage</div><div className="v">{pct(stats?.portal_coverage ?? undefined, 0)}</div></div>
        <div className="tile"><div className="k">Graduation / 24h</div><div className="v">{stats?.migrations_24h ?? "–"} <span className="k">/ {stats?.migrations_total ?? 0} tổng</span></div></div>
        <div className="tile"><div className="k">Đã harvest nến</div><div className="v">{sum?.harvested ?? 0} <span className="k">alive 24h {pct(sum?.alive_24h_rate, 0)}</span></div></div>
        <div className={`tile verdict ${verdict.toLowerCase()}`}><div className="k">Giả thuyết C (T+30m → 1h)</div><div className="v">{verdict}</div><div className="k">{sum?.verdict.why}</div></div>
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
        <thead><tr><th>Lúc</th><th>Mint</th><th>Pool</th><th>Slot</th><th>SOL vào pool</th><th>Harvest</th></tr></thead>
        <tbody>
          {migs.length === 0 && <tr><td colSpan={6} className="empty">Chưa ghi được migration nào</td></tr>}
          {migs.map((m) => (
            <tr key={m.mint}>
              <td>{time(m.ts)}</td>
              <td className="mono"><a href={`https://solscan.io/token/${m.mint}`} target="_blank" rel="noreferrer">{short(m.mint)}</a></td>
              <td className="mono">{short(m.pool)}</td>
              <td>{m.slot}</td>
              <td>{m.sol_amount?.toFixed(2)}</td>
              <td>{m.harvested ? "✓" : "chờ 25h"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Theo giờ (24h)</h2>
      <table>
        <thead><tr><th>Giờ (UTC)</th><th>Create on‑chain</th><th>Create PumpPortal</th><th>Graduation</th></tr></thead>
        <tbody>
          {stats?.hourly.slice().reverse().map((h) => (
            <tr key={h.hour}><td>{h.hour}</td><td>{h.creates_chain}</td><td>{h.creates_portal}</td><td>{h.migrations}</td></tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
