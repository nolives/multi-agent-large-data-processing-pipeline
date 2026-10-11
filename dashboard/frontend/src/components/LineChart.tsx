import { useEffect, useRef, useState } from 'react';

export interface Point { label: string; value: number; detail: string }

/**
 * A single-series line over time with a soft area wash. The pointer snaps a crosshair to the nearest
 * point and shows its value; the same values are available in the table below the chart.
 */
export function LineChart({ points, format, height = 220, partial = [] }: {
  points: Point[]; format: (v: number) => string; height?: number; partial?: number[];
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  useEffect(() => {
    if (!box.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);
  if (points.length < 2) return <p className="muted">Not enough months to draw a trend.</p>;

  const pad = { left: 44, right: 16, top: 12, bottom: 26 };
  const innerW = width - pad.left - pad.right, innerH = height - pad.top - pad.bottom;
  const rawMax = Math.max(...points.map((p) => p.value));
  const step = niceStep(rawMax / 4);
  const max = Math.max(step, Math.ceil(rawMax / step) * step);
  const x = (i: number) => pad.left + (innerW * i) / (points.length - 1);
  const y = (v: number) => pad.top + innerH - (innerH * v) / max;
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  const every = Math.ceil(points.length / Math.max(2, Math.floor(innerW / 80)));
  const nearest = (clientX: number, target: SVGElement) => {
    const rect = target.getBoundingClientRect();
    const i = Math.round(((clientX - rect.left - pad.left) / innerW) * (points.length - 1));
    setHover(Math.min(points.length - 1, Math.max(0, i)));
  };

  return (
    <div ref={box} className="relative" style={{ width: '100%', overflow: 'hidden' }}>
      <svg width={width} height={height} role="img" aria-label="Trend by month. Values are also in the table below."
           onPointerMove={(e) => nearest(e.clientX, e.currentTarget)} onPointerLeave={() => setHover(null)} style={{ display: 'block', touchAction: 'none' }}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? 'var(--axis)' : 'var(--grid)'} strokeWidth={1} />
            <text x={pad.left - 8} y={y(t) + 4} textAnchor="end" fontSize={11.5} fill="var(--muted)" style={{ fontVariantNumeric: 'tabular-nums' }}>{format(t)}</text>
          </g>
        ))}
        {points.map((p, i) => (i % every === 0 ? (
          <text key={p.label} x={x(i)} y={height - 8} textAnchor={i === 0 ? 'start' : 'middle'} fontSize={11.5} fill="var(--muted)">{p.label}</text>
        ) : null))}
        <path d={`${path} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill="var(--series-wash)" />
        <path d={path} fill="none" stroke="var(--series)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {partial.map((i) => <circle key={i} cx={x(i)} cy={y(points[i].value)} r={4} fill="var(--surface)" stroke="var(--series)" strokeWidth={2} />)}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={y(0)} stroke="var(--axis)" strokeWidth={1} />
            <circle cx={x(hover)} cy={y(points[hover].value)} r={5} fill="var(--series)" stroke="var(--surface)" strokeWidth={2} />
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tooltip" style={{ left: Math.min(Math.max(x(hover) - 80, 0), width - 180), top: Math.max(y(points[hover].value) - 62, 0) }}>
          <div className="font-semibold">{format(points[hover].value)}</div>
          <div className="ink-2">{points[hover].label}</div>
          <div className="muted">{points[hover].detail}</div>
        </div>
      )}
      <button className="muted text-[12.5px] underline mt-1" onClick={() => setTable(!table)} aria-expanded={table}>{table ? 'Hide table' : 'Show as table'}</button>
      {table && (
        <div className="scroll-x mt-2"><table className="data"><thead><tr><th>Month</th><th className="r">Value</th><th>Detail</th></tr></thead>
          <tbody>{points.map((p) => <tr key={p.label}><td>{p.label}</td><td className="r">{format(p.value)}</td><td className="ink-2">{p.detail}</td></tr>)}</tbody></table></div>
      )}
    </div>
  );
}

function niceStep(rough: number) {
  const power = 10 ** Math.floor(Math.log10(Math.max(rough, 1e-9)));
  const unit = rough / power;
  return (unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10) * power;
}
