import { useEffect, useState } from 'react';
import type { Overview as OverviewData } from './api';
import { useApi } from './components/ui';
import { IssueDetail, Issues } from './views/Issues';
import { Overview } from './views/Overview';
import { Quality } from './views/Quality';
import { Recommendation } from './views/Recommendation';
import { ReviewTrace } from './views/ReviewTrace';

const TABS: [string, string][] = [['overview', 'Overview'], ['issues', 'Issue ranking'], ['recommendation', 'Recommendation'], ['quality', 'Evidence and quality']];

function useRoute() {
  const read = () => window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export default function App() {
  const [section = 'overview', id] = useRoute();
  const run = useApi<OverviewData>('/overview').data?.run;
  const active = section === 'reviews' ? '' : section;
  return (
    <div className="max-w-[1120px] mx-auto px-4 pb-16">
      <header className="pt-6 pb-4">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <h1 className="text-[20px] font-semibold">Spotify review insights</h1>
          {run && <span className="muted text-[12.5px]">Run <span className="mono">{run.run_id}</span> · published {new Date(run.published_at).toLocaleDateString('en-US', { dateStyle: 'medium' })}</span>}
        </div>
        <p className="ink-2 text-[14px] mt-1">Where should the next quarter of product effort go? Saved results of a multi-agent review pipeline, served from its database.</p>
        <nav className="flex gap-1 mt-4 flex-wrap" aria-label="Sections">
          {TABS.map(([key, label]) => (
            <a key={key} href={`#/${key}`} aria-current={active === key ? 'page' : undefined} className="px-3 py-1.5 rounded-md text-[14px] no-underline"
               style={{ textDecoration: 'none', background: active === key ? 'var(--surface)' : 'transparent', border: `1px solid ${active === key ? 'var(--border)' : 'transparent'}`,
                        fontWeight: active === key ? 600 : 400, color: active === key ? 'var(--ink)' : 'var(--ink-2)' }}>{label}</a>))}
        </nav>
      </header>
      <main>
        {section === 'overview' && <Overview />}
        {section === 'issues' && (id ? <IssueDetail key={id} id={id} /> : <Issues />)}
        {section === 'recommendation' && <Recommendation />}
        {section === 'quality' && <Quality />}
        {section === 'reviews' && id && <ReviewTrace key={id} id={id} />}
      </main>
      <footer className="muted text-[12.5px] mt-10">
        Data: public Google Play reviews of Spotify (BwandoWando, Kaggle, CC0). Labels and the recommendation are model-generated and checked by code; see Evidence and quality.
      </footer>
    </div>
  );
}
