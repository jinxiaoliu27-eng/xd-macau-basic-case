from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import build_site  # noqa: E402

OUTPUT = ROOT / 'docs'

COLLECTIONS = [
    {
        'slug': 'three-phases',
        'title': 'Three Phases',
        'source_dir': ROOT / 'three phases',
        'buckets': ['2006-2013', '2014-2018', '2019-2024'],
        'intro': 'Cases regrouped into 2006-2013, 2014-2018, and 2019-2024 for mid-range phase analysis.',
    },
    {
        'slug': 'five-phases',
        'title': 'Five Phases',
        'source_dir': ROOT / 'five phases',
        'buckets': ['2006-2011', '2012-2013', '2014-2015', '2016-2018', '2019-2024'],
        'intro': 'Cases regrouped into five finer-grained periods for more detailed temporal analysis.',
    },
]


def clone_for_bucket(case: build_site.CaseRecord, bucket: str) -> build_site.CaseRecord:
    case.year_bucket = bucket
    case.source_bucket = bucket
    case.slug = build_site.slugify(f'{bucket}-{Path(case.source_name).stem}')
    return case


def load_cases(source_dir: Path, buckets: list[str]) -> tuple[dict[str, list[build_site.CaseRecord]], list[build_site.CaseRecord]]:
    grouped: dict[str, list[build_site.CaseRecord]] = {bucket: [] for bucket in buckets}
    all_cases: list[build_site.CaseRecord] = []
    for bucket in buckets:
        folder = source_dir / bucket
        for path in sorted(folder.glob('*.txt')):
            case = clone_for_bucket(build_site.parse_case(path, bucket), bucket)
            grouped[bucket].append(case)
            all_cases.append(case)
    for bucket in grouped:
        grouped[bucket].sort(key=lambda c: (c.decision_year or 0, c.date, c.number))
    all_cases.sort(key=lambda c: (c.decision_year or 0, c.date, c.number))
    return grouped, all_cases


def render_home(slug: str, title: str, intro: str, grouped: dict[str, list[build_site.CaseRecord]], all_cases: list[build_site.CaseRecord]) -> str:
    stats = ''.join(
        f'''
        <a class="stat-card" href="./{bucket}/index.html">
          <span class="stat-card__value">{len(cases)}</span>
          <span class="stat-card__label">{bucket}</span>
        </a>
        '''
        for bucket, cases in grouped.items()
    )
    sections = ''.join(
        f'''
        <section class="year-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Phase Group</p>
              <h2>{bucket}</h2>
            </div>
            <a class="text-link" href="./{bucket}/index.html">Open Phase</a>
          </div>
          <div class="case-grid">
            {''.join(build_site.case_card(case) for case in cases[:6])}
          </div>
        </section>
        '''
        for bucket, cases in grouped.items()
    )
    search_json = json.dumps([
        {
            'url': f'./{case.year_bucket}/{case.slug}.html',
            'number': case.number,
            'theme': case.theme,
            'summary': case.summary,
            'year_bucket': case.year_bucket,
            'lang': case.lang,
        }
        for case in all_cases
    ], ensure_ascii=False)
    body = f'''
<div class="site-shell">
  <header class="hero">
    <nav class="topbar">
      <a class="brand" href="../index.html">XD Macau Basic Case</a>
      <div class="topbar__links">
        <a href="../index.html">Main Site</a>
        <a href="#directory">Directory</a>
      </div>
    </nav>
    <div class="hero__content">
      <div>
        <p class="eyebrow">Phase Collection</p>
        <h1>{title}</h1>
        <p class="hero__lead">{intro}</p>
      </div>
      <aside class="hero-panel">
        <p class="hero-panel__label">Cases</p>
        <p class="hero-panel__value">{len(all_cases)}</p>
        <p class="hero-panel__note">This collection reorganizes the same judgments into alternate historical phases.</p>
      </aside>
    </div>
    <div class="stat-grid">{stats}</div>
  </header>
  <main>
    <section id="directory" class="search-section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Directory</p>
          <h2>{title} Search</h2>
        </div>
      </div>
      <div class="search-box">
        <input id="global-search" type="search" placeholder="Search by case number, theme, or summary">
        <div id="search-results" class="search-results"></div>
      </div>
    </section>
    {sections}
  </main>
</div>
<script id="search-data" type="application/json">{build_site.html.escape(search_json)}</script>
'''
    return build_site.page_shell(f'{title} | XD Macau Basic Case', body, 'home-page', '../')


def render_bucket_index(title: str, bucket: str, cases: list[build_site.CaseRecord]) -> str:
    body = f'''
<div class="site-shell subpage-shell">
  <header class="sub-hero">
    <nav class="topbar">
      <a class="brand" href="../index.html">{title}</a>
      <div class="topbar__links">
        <a href="../../index.html">Main Site</a>
      </div>
    </nav>
    <p class="eyebrow">Phase Group</p>
    <h1>{bucket}</h1>
    <p class="hero__lead">This phase includes {len(cases)} cases with searchable index and full-text reading pages.</p>
  </header>
  <main class="year-directory">
    <div class="search-box">
      <input class="table-search" type="search" placeholder="Filter cases in this phase">
    </div>
    <div class="table-wrap">
      <table class="directory-table">
        <thead>
          <tr>
            <th>Case No.</th>
            <th>Date</th>
            <th>Lang</th>
            <th>Theme</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {build_site.directory_table(cases)}
        </tbody>
      </table>
    </div>
  </main>
</div>
'''
    return build_site.page_shell(f'{bucket} | {title}', body, 'year-page', '../../')


def render_case(title: str, case: build_site.CaseRecord) -> str:
    tags = ''.join(f'<span>{build_site.html.escape(tag)}</span>' for tag in case.keywords[:8])
    summary_html = build_site.html.escape(case.summary)
    body = f'''
<div class="site-shell detail-shell">
  <header class="detail-hero">
    <nav class="topbar">
      <a class="brand" href="../index.html">{title}</a>
      <div class="topbar__links">
        <a href="./index.html">{case.year_bucket}</a>
        <a href="../../index.html">Main Site</a>
      </div>
    </nav>
    <p class="eyebrow">{title} / {case.year_bucket} / {case.lang}</p>
    <h1>{build_site.html.escape(case.theme)}</h1>
    <p class="hero__lead">{summary_html}</p>
    <div class="detail-meta">
      <div><span>Case No.</span><strong>{build_site.html.escape(case.number)}</strong></div>
      <div><span>Date</span><strong>{build_site.html.escape(case.date or 'Unknown')}</strong></div>
      <div><span>Source File</span><strong>{build_site.html.escape(case.source_name)}</strong></div>
      <div><span>Phase Bucket</span><strong>{build_site.html.escape(case.year_bucket)}</strong></div>
    </div>
    <div class="tag-row">{tags}</div>
  </header>
  <main class="detail-layout">
    <aside class="detail-sidebar">
      <section>
        <h2>Metadata</h2>
        <dl>
          <dt>Title</dt><dd>{build_site.html.escape(case.title)}</dd>
          <dt>Court</dt><dd>{build_site.html.escape(case.court or 'Unknown')}</dd>
          <dt>Author</dt><dd>{build_site.html.escape(case.author or 'Unknown')}</dd>
          <dt>Category</dt><dd>{build_site.html.escape(case.category or 'Unknown')}</dd>
        </dl>
      </section>
    </aside>
    <article class="judgment-body">
      <details class="summary-box" open>
        <summary>Abstract</summary>
        <p>{summary_html}</p>
      </details>
      {case.body_html}
    </article>
  </main>
</div>
'''
    return build_site.page_shell(f'{case.number} | {case.theme}', body, 'detail-page', '../../')


def build_collection(collection: dict) -> None:
    grouped, all_cases = load_cases(collection['source_dir'], collection['buckets'])
    target_root = OUTPUT / collection['slug']
    if target_root.exists():
        import shutil
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / 'index.html').write_text(render_home(collection['slug'], collection['title'], collection['intro'], grouped, all_cases), encoding='utf-8')
    for bucket, cases in grouped.items():
        target_dir = target_root / bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / 'index.html').write_text(render_bucket_index(collection['title'], bucket, cases), encoding='utf-8')
        for case in cases:
            (target_dir / f'{case.slug}.html').write_text(render_case(collection['title'], case), encoding='utf-8')


def patch_main_index() -> None:
    index_path = OUTPUT / 'index.html'
    html = index_path.read_text(encoding='utf-8')
    marker = '<section id="years" class="year-stack">'
    insert = '''<section class="year-panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Phase Directories</p>
          <h2>Alternative Periodizations</h2>
        </div>
      </div>
      <div class="stat-grid">
        <a class="stat-card" href="./three-phases/index.html">
          <span class="stat-card__value">3</span>
          <span class="stat-card__label">Three Phases</span>
          <p class="hero-panel__note">2006-2013 / 2014-2018 / 2019-2024</p>
        </a>
        <a class="stat-card" href="./five-phases/index.html">
          <span class="stat-card__value">5</span>
          <span class="stat-card__label">Five Phases</span>
          <p class="hero-panel__note">2006-2011 / 2012-2013 / 2014-2015 / 2016-2018 / 2019-2024</p>
        </a>
      </div>
    </section>

    <section id="years" class="year-stack">'''
    if marker in html and 'three-phases/index.html' not in html:
        html = html.replace(marker, insert, 1)
    html = html.replace('<a href="#directory">目录</a>', '<a href="#directory">Directory</a>')
    html = html.replace('<a href="#years">年份分卷</a>', '<a href="#years">Buckets</a>')
    index_path.write_text(html, encoding='utf-8')


def main() -> None:
    for collection in COLLECTIONS:
        build_collection(collection)
    patch_main_index()


if __name__ == '__main__':
    main()
