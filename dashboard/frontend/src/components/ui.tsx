import { useEffect, useState, type ReactNode } from 'react';
import { api } from '../api';

export const fmt = (value: number) => value.toLocaleString('en-US');
export const pct = (part: number, whole: number, digits = 1) => (whole ? `${((100 * part) / whole).toFixed(digits)}%` : 'n/a');
export const share = (fraction: number | null | undefined) => (fraction == null ? 'n/a' : `${Math.round(fraction * 100)}%`);
export const monthLabel = (month: string) =>
  new Date(`${month}-15T00:00:00Z`).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
export const TOPIC_LABEL: Record<string, string> = {
  access: 'Access', usability: 'Usability', playback: 'Playback', downloads: 'Downloads', catalog: 'Catalog', billing: 'Billing',
  support: 'Support', other: 'Other', billing_support: 'Billing and support',
};

/** Loads one API path. While a new path loads, the previous data stays on screen (no skeleton flash). */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true });
  useEffect(() => {
    if (!path) return;
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api<T>(path)
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((e: Error) => live && setState({ data: null, error: e.message, loading: false }));
    return () => { live = false; };
  }, [path]);
  return state;
}

export function Async<T>({ state, children }: { state: { data: T | null; error: string | null; loading: boolean }; children: (data: T) => ReactNode }) {
  if (state.error) return <div className="card" role="alert"><strong>Could not load this section.</strong> <span className="ink-2">{state.error}</span></div>;
  if (!state.data) return <div className="card muted" aria-busy="true">Loading from the database…</div>;
  return <div style={{ opacity: state.loading ? 0.55 : 1, transition: 'opacity 120ms' }}>{children(state.data)}</div>;
}

export function Card({ title, note, children, className = '' }: { title?: string; note?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {title && <h2 className="text-[15px] font-semibold">{title}</h2>}
      {note && <p className="muted text-[13px] mt-0.5 mb-3">{note}</p>}
      {!note && title && <div className="mb-3" />}
      {children}
    </section>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: string; sub?: ReactNode }) {
  return (
    <div className="card">
      <div className="ink-2 text-[13px]">{label}</div>
      <div className="text-[28px] font-semibold leading-tight mt-1">{value}</div>
      {sub && <div className="muted text-[12.5px] mt-1">{sub}</div>}
    </div>
  );
}

export interface BarDatum { key: string; label: ReactNode; value: number; display?: string; detail?: string; emphasis?: boolean; href?: string }

/**
 * Horizontal bars for comparing magnitudes. One series, so one color; `emphasis` on some rows grays the rest.
 * Every value is printed at the bar's end, so nothing depends on hover.
 */
export function BarList({ data, unit, max, wideLabels = false }: { data: BarDatum[]; unit: string; max?: number; wideLabels?: boolean }) {
  const top = max ?? Math.max(1, ...data.map((d) => d.value));
  const anyEmphasis = data.some((d) => d.emphasis);
  return (
    <div role="list" aria-label={unit}>
      {data.map((d) => (
        <div className="bar-row" role="listitem" key={d.key} title={d.detail ?? `${d.display ?? fmt(d.value)} ${unit}`}
             style={wideLabels ? { gridTemplateColumns: 'minmax(150px, 52%) 1fr auto' } : undefined}>
          <div className={`text-[13.5px] ${wideLabels ? 'leading-snug' : 'truncate'}`}>{d.href ? <a href={d.href}>{d.label}</a> : d.label}</div>
          <div className="bar-track"><div className={`bar-fill ${anyEmphasis && !d.emphasis ? 'deemph' : ''}`} style={{ width: `${(100 * d.value) / top}%`, minWidth: d.value ? undefined : 0 }} /></div>
          <div className="num text-[13.5px] font-medium text-right" style={{ minWidth: 56 }}>{d.display ?? fmt(d.value)}</div>
        </div>
      ))}
    </div>
  );
}

export const SeverityDots = ({ level }: { level: number }) => (
  <span className="whitespace-nowrap" aria-label={`Severity ${level} of 5`} title={`Severity ${level} of 5`}>
    <span className="num font-medium">{level}</span><span className="muted"> / 5</span>
  </span>
);

export const Status = ({ ok, children }: { ok: boolean; children: ReactNode }) => (
  <span className="inline-flex items-baseline gap-1.5">
    <span aria-hidden style={{ color: ok ? 'var(--good)' : 'var(--critical)', fontWeight: 700 }}>{ok ? '✓' : '✕'}</span>
    <span>{children}</span>
  </span>
);
