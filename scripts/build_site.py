from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs"
ASSETS = OUTPUT / "assets"

SOURCE_DIRS = [
    ("1999-2010", ROOT / "1999-2010"),
    ("2011-2018", ROOT / "2011-2018"),
    ("2019-2025", ROOT / "2019-2025"),
]

YEAR_BUCKETS = [
    ("1999-2010", 1999, 2010),
    ("2011-2018", 2011, 2018),
    ("2019-2025", 2019, 2025),
]


@dataclass
class CaseRecord:
    year_bucket: str
    source_bucket: str
    decision_year: int | None
    source_name: str
    slug: str
    lang: str
    number: str
    date: str
    title: str
    theme: str
    summary: str
    keywords: list[str]
    court: str
    author: str
    category: str
    body_html: str
    plain_text: str
    source_relpath: str


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "case"


def normalize_space(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\ufeff", "").replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(lines)


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in normalize_space(text).splitlines()]


def strip_css_noise(lines: list[str]) -> list[str]:
    cleaned = []
    skip_exact = {
        "body {",
        "font-size: 13px;",
        "line-height: 25px;",
        "background-color: #fff;",
        "}",
        ".highlight-key {",
        "font-weight: bold;",
        "background: #FFFF00;",
        "打印全文",
        "裁判書製作人",
        "O Relator,",
    }
    for line in lines:
        if not line:
            cleaned.append("")
            continue
        if line in skip_exact:
            continue
        if line.startswith("---------------") or line.startswith("------------------------------------------------------------"):
            continue
        cleaned.append(line)
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return cleaned


def detect_lang(path: Path) -> str:
    name = path.stem.lower()
    if name.endswith("_zh"):
        return "中文"
    if name.endswith("_pt"):
        return "Português"
    return "Unknown"


def match_first(lines: Iterable[str], patterns: list[str]) -> str:
    for line in lines:
        for pattern in patterns:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return ""


def collect_bullets(lines: list[str], start: int) -> tuple[list[str], int]:
    items: list[str] = []
    idx = start
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            if items:
                break
            idx += 1
            continue
        if line.startswith("-"):
            items.append(line.lstrip("-").strip())
            idx += 1
            continue
        break
    return items, idx


def extract_summary(lines: list[str], start_markers: list[str], stop_markers: list[str]) -> str:
    start_idx = -1
    inline = ""
    for idx, line in enumerate(lines):
        for marker in start_markers:
            if line.startswith(marker):
                start_idx = idx
                inline = line[len(marker) :].strip(" :：")
                break
        if start_idx != -1:
            break
    if start_idx == -1:
        return ""

    chunks: list[str] = []
    if inline:
        chunks.append(inline)
    idx = start_idx + 1
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            if chunks:
                break
            idx += 1
            continue
        if any(line.startswith(marker) for marker in stop_markers):
            break
        if re.match(r"^[IVX一二三四五六七八九十]+[\.\、\)]", line):
            break
        chunks.append(line.lstrip("-").strip())
        idx += 1
        if len(" ".join(chunks)) > 420:
            break
    return " ".join(chunks).strip()


def strip_leading_labels(text: str) -> str:
    text = text.strip()
    prefixes = [
        "主題：",
        "主 題：",
        "關鍵詞：",
        "摘要：",
        "摘 要",
        "SUMÁRIO :",
        "SUMÁRIO:",
        "Assuntos:",
        "Assunto:",
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def parse_metadata(lines: list[str], lang: str) -> dict[str, str | list[str]]:
    number = match_first(
        lines,
        [
            r"^卷宗編號[:：]\s*(.+)$",
            r"^編號[:：]\s*(.+)$",
            r"^第\s*([0-9]+/[0-9]+號.*)$",
            r"^Processo\s+n\.?[ºo]\s*(.+)$",
            r"^Processo nº\s*(.+)$",
        ],
    )
    date = match_first(
        lines,
        [
            r"^日期[:：]\s*(.+)$",
            r"^Data[:：]\s*(.+)$",
            r"^Data\s*[:：]\s*(.+)$",
            r"^Data\s+(.+)$",
        ],
    )
    court = match_first(
        lines,
        [
            r"^(澳門特別行政區.+法院.+)$",
            r"^(行政、稅務及海關方面的上訴裁判書)$",
            r"^(合議庭裁判書)$",
            r"^(ACORDAM OS JUÍZES.+)$",
            r"^(Acordam os Juízes.+)$",
        ],
    )
    author = ""
    for idx, line in enumerate(lines):
        if line in {"裁判書製作人", "O Relator,"} and idx + 1 < len(lines):
            author = lines[idx + 1].strip("_ ").strip()
            break
        if line.startswith("Relator:"):
            author = line.split(":", 1)[1].strip()
            break

    title = strip_leading_labels(lines[0]) if lines else ""
    if title.startswith("-"):
        title = title.lstrip("-").strip()

    keywords: list[str] = []
    theme = ""

    for idx, line in enumerate(lines):
        if line.startswith(("主題", "主 題", "關鍵詞", "Assuntos", "Assunto")):
            inline = strip_leading_labels(line)
            if inline:
                keywords.append(inline)
            bullet_items, _ = collect_bullets(lines, idx + 1)
            keywords.extend(bullet_items)
            break

    if not keywords:
        early_bullets, _ = collect_bullets(lines, 0)
        keywords.extend(early_bullets)

    keywords = [item for item in dict.fromkeys(k for k in keywords if k)]
    theme = " / ".join(keywords[:3]).strip()
    if not theme:
        theme = title or number or "未命名案件"

    summary = extract_summary(
        lines,
        ["摘要", "摘要：", "摘 要", "SUMÁRIO :", "SUMÁRIO:"],
        [
            "裁判書製作人",
            "卷宗編號",
            "編號",
            "一.",
            "一、",
            "I)",
            "I -",
            "Relator:",
            "Processo",
        ],
    )
    if not summary:
        summary = extract_summary(
            lines,
            ["概述", "I) RELATÓRIO", "I - RELATÓRIO", "一、 案情敘述", "一. 概述"],
            ["二.", "二、", "II)", "II -"],
        )

    category = ""
    for line in lines[:30]:
        if any(token in line for token in ["刑事上訴案", "行政", "稅務", "海關", "recurso contencioso", "Autos de recurso contencioso"]):
            category = line
            break

    return {
        "number": number,
        "date": date,
        "court": court,
        "author": author,
        "title": title,
        "theme": theme,
        "summary": summary,
        "keywords": keywords,
        "category": category,
    }


def paragraphs_to_html(lines: list[str]) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{html.escape(' '.join(paragraph))}</p>")
            paragraph = []

    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            flush_paragraph()
            idx += 1
            continue
        if line.startswith("-"):
            flush_paragraph()
            items: list[str] = []
            while idx < len(lines):
                current = lines[idx].strip()
                if not current.startswith("-"):
                    break
                items.append(f"<li>{html.escape(current.lstrip('-').strip())}</li>")
                idx += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"^[IVX一二三四五六七八九十]+[\.\、\)]", line):
            flush_paragraph()
            level = 2 if len(line) < 80 else 3
            blocks.append(f"<h{level}>{html.escape(line)}</h{level}>")
            idx += 1
            continue
        if len(line) < 40 and (
            line.endswith("：")
            or line.endswith(":")
            or "裁判" in line
            or "RELATÓRIO" in line
            or "事實" in line
            or "理由" in line
        ):
            flush_paragraph()
            blocks.append(f"<h3>{html.escape(line)}</h3>")
            idx += 1
            continue
        paragraph.append(line)
        idx += 1

    flush_paragraph()
    return "\n".join(blocks)


def extract_decision_year(date_text: str, lines: list[str]) -> int | None:
    probes = [date_text] + lines[:20]
    for probe in probes:
        match = re.search(r"(19\d{2}|20\d{2})", probe)
        if match:
            return int(match.group(1))
    return None


def determine_year_bucket(year: int | None, fallback_bucket: str) -> str:
    if year is not None:
        for bucket, start, end in YEAR_BUCKETS:
            if start <= year <= end:
                return bucket
    return fallback_bucket


def parse_case(path: Path, source_bucket: str) -> CaseRecord:
    raw = path.read_text(encoding="utf-8-sig", errors="ignore")
    lines = strip_css_noise(clean_lines(raw))
    meta = parse_metadata(lines, detect_lang(path))
    decision_year = extract_decision_year(str(meta["date"] or ""), lines)
    year_bucket = determine_year_bucket(decision_year, source_bucket)

    plain_text = "\n".join(lines)
    number = str(meta["number"] or path.stem)
    slug = slugify(f"{year_bucket}-{path.stem}")
    title = str(meta["title"] or meta["theme"] or number)
    summary = str(meta["summary"] or "")
    if not summary:
        summary = re.sub(r"\s+", " ", plain_text[:220]).strip()

    body_html = paragraphs_to_html(lines)
    theme = str(meta["theme"] or title)

    return CaseRecord(
        year_bucket=year_bucket,
        source_bucket=source_bucket,
        decision_year=decision_year,
        source_name=path.name,
        slug=slug,
        lang=detect_lang(path),
        number=number,
        date=str(meta["date"] or ""),
        title=title,
        theme=theme,
        summary=summary,
        keywords=list(meta["keywords"]),
        court=str(meta["court"] or ""),
        author=str(meta["author"] or ""),
        category=str(meta["category"] or ""),
        body_html=body_html,
        plain_text=plain_text,
        source_relpath=str(path.relative_to(ROOT)).replace("\\", "/"),
    )
def case_card(case: CaseRecord) -> str:
    summary = html.escape(case.summary[:170] + ("..." if len(case.summary) > 170 else ""))
    tags = "".join(f"<span>{html.escape(tag)}</span>" for tag in case.keywords[:4])
    return f"""
    <article class="case-card" data-lang="{html.escape(case.lang)}" data-search="{html.escape((case.number + ' ' + case.theme + ' ' + case.summary).lower())}">
      <a class="case-card__link" href="{html.escape(case.year_bucket)}/{html.escape(case.slug)}.html">
        <div class="case-card__top">
          <p class="eyebrow">{html.escape(case.year_bucket)}</p>
          <p class="meta-chip">{html.escape(case.lang)}</p>
        </div>
        <h3>{html.escape(case.theme)}</h3>
        <p class="case-number">{html.escape(case.number)}</p>
        <p class="case-summary">{summary}</p>
        <div class="tag-row">{tags}</div>
      </a>
    </article>
    """


def directory_table(cases: list[CaseRecord]) -> str:
    rows = []
    for case in cases:
        rows.append(
            f"""
            <tr data-search="{html.escape((case.number + ' ' + case.theme + ' ' + case.summary).lower())}">
              <td><a href="{html.escape(case.slug)}.html">{html.escape(case.number)}</a></td>
              <td>{html.escape(case.date)}</td>
              <td>{html.escape(case.lang)}</td>
              <td>{html.escape(case.theme)}</td>
              <td>{html.escape(case.summary[:150] + ('...' if len(case.summary) > 150 else ''))}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def page_shell(title: str, body: str, page_class: str = "", asset_prefix: str = "./") -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="澳門基本法案件靜態資料庫，按年份分卷收錄裁判全文、主題與摘要。">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{asset_prefix}assets/style.css">
</head>
<body class="{html.escape(page_class)}">
{body}
<script src="{asset_prefix}assets/app.js"></script>
</body>
</html>
"""


def render_home(cases: list[CaseRecord], grouped: dict[str, list[CaseRecord]]) -> str:
    stats = "".join(
        f"""
        <a class="stat-card" href="./{bucket}/index.html">
          <span class="stat-card__value">{len(bucket_cases)}</span>
          <span class="stat-card__label">{html.escape(bucket)}</span>
        </a>
        """
        for bucket, bucket_cases in grouped.items()
    )

    spotlight = "".join(case_card(case) for case in cases[:9])
    year_sections = "".join(
        f"""
        <section class="year-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">年份分卷</p>
              <h2>{html.escape(bucket)}</h2>
            </div>
            <a class="text-link" href="./{bucket}/index.html">查看该分卷</a>
          </div>
          <div class="case-grid">
            {''.join(case_card(case) for case in bucket_cases[:6])}
          </div>
        </section>
        """
        for bucket, bucket_cases in grouped.items()
    )

    search_json = json.dumps(
        [
            {
                "url": f"./{case.year_bucket}/{case.slug}.html",
                "number": case.number,
                "theme": case.theme,
                "summary": case.summary,
                "year_bucket": case.year_bucket,
                "lang": case.lang,
            }
            for case in cases
        ],
        ensure_ascii=False,
    )

    body = f"""
<div class="site-shell">
  <header class="hero">
    <nav class="topbar">
      <a class="brand" href="./index.html">XD Macau Basic Case</a>
      <div class="topbar__links">
        <a href="#directory">目录</a>
        <a href="#years">年份分卷</a>
      </div>
    </nav>
    <div class="hero__content">
      <div>
        <p class="eyebrow">GitHub Pages / Basic Law Cases</p>
        <h1>澳門基本法案件靜態資料庫</h1>
        <p class="hero__lead">按照 <code>1999-2010</code>、<code>2011-2018</code>、<code>2019-2025</code> 三個年份區間整理全文閱讀頁，並提供案件編號、主題、摘要與快速檢索。</p>
      </div>
      <aside class="hero-panel">
        <p class="hero-panel__label">收錄案件</p>
        <p class="hero-panel__value">{len(cases)}</p>
        <p class="hero-panel__note">含中文與葡文原文，適合公開閱讀與研究引用。</p>
      </aside>
    </div>
    <div class="stat-grid">{stats}</div>
  </header>

  <main>
    <section id="directory" class="search-section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">总目录</p>
          <h2>按编号、主题、摘要检索</h2>
        </div>
      </div>
      <div class="search-box">
        <input id="global-search" type="search" placeholder="搜索案件编号、主题、摘要">
        <div id="search-results" class="search-results"></div>
      </div>
    </section>

    <section class="spotlight">
      <div class="section-heading">
        <div>
          <p class="eyebrow">精选阅读</p>
          <h2>近期卷宗样式展示</h2>
        </div>
      </div>
      <div class="case-grid">{spotlight}</div>
    </section>

    <section id="years" class="year-stack">
      {year_sections}
    </section>
  </main>

  <footer class="footer">
    <p>本网站为静态整理页，源文件来自当前项目中的裁判文本。</p>
  </footer>
</div>
<script id="search-data" type="application/json">{html.escape(search_json)}</script>
"""
    return page_shell("XD Macau Basic Case", body, "home-page", "./")


def render_year_index(bucket: str, cases: list[CaseRecord]) -> str:
    body = f"""
<div class="site-shell subpage-shell">
  <header class="sub-hero">
    <nav class="topbar">
      <a class="brand" href="../index.html">XD Macau Basic Case</a>
      <div class="topbar__links">
        <a href="../index.html">首页</a>
      </div>
    </nav>
    <p class="eyebrow">年份分卷</p>
    <h1>{html.escape(bucket)}</h1>
    <p class="hero__lead">本分卷收錄 {len(cases)} 份案件文本，保留全文閱讀並補充主題、摘要與檢索入口。</p>
  </header>
  <main class="year-directory">
    <div class="search-box">
      <input class="table-search" type="search" placeholder="筛选本分卷案件">
    </div>
    <div class="table-wrap">
      <table class="directory-table">
        <thead>
          <tr>
            <th>案件编号</th>
            <th>日期</th>
            <th>语言</th>
            <th>主题</th>
            <th>摘要</th>
          </tr>
        </thead>
        <tbody>
          {directory_table(cases)}
        </tbody>
      </table>
    </div>
  </main>
</div>
"""
    return page_shell(f"{bucket} | XD Macau Basic Case", body, "year-page", "../")


def render_case(case: CaseRecord) -> str:
    tags = "".join(f"<span>{html.escape(tag)}</span>" for tag in case.keywords[:8])
    summary_html = html.escape(case.summary)
    body = f"""
<div class="site-shell detail-shell">
  <header class="detail-hero">
    <nav class="topbar">
      <a class="brand" href="../index.html">XD Macau Basic Case</a>
      <div class="topbar__links">
        <a href="./index.html">{html.escape(case.year_bucket)}</a>
        <a href="../index.html#directory">总目录</a>
      </div>
    </nav>
    <p class="eyebrow">{html.escape(case.year_bucket)} / {html.escape(case.lang)}</p>
    <h1>{html.escape(case.theme)}</h1>
    <p class="hero__lead">{summary_html}</p>
    <div class="detail-meta">
      <div><span>案件编号</span><strong>{html.escape(case.number)}</strong></div>
      <div><span>日期</span><strong>{html.escape(case.date or '未提取')}</strong></div>
      <div><span>来源文件</span><strong>{html.escape(case.source_name)}</strong></div>
      <div><span>原始路径</span><strong>{html.escape(case.source_relpath)}</strong></div>
    </div>
    <div class="tag-row">{tags}</div>
  </header>

  <main class="detail-layout">
    <aside class="detail-sidebar">
      <section>
        <h2>案件信息</h2>
        <dl>
          <dt>标题</dt><dd>{html.escape(case.title)}</dd>
          <dt>法院</dt><dd>{html.escape(case.court or '未标明')}</dd>
          <dt>裁判书制作人</dt><dd>{html.escape(case.author or '未标明')}</dd>
          <dt>分类</dt><dd>{html.escape(case.category or '未标明')}</dd>`r`n          <dt>原始分组</dt><dd>{html.escape(case.source_bucket)}</dd>`r`n          <dt>现归档分组</dt><dd>{html.escape(case.year_bucket)}</dd>
        </dl>
      </section>
      <section>
        <h2>阅读说明</h2>
        <p>该页保留原文段落结构，并针对长篇判词优化了行距、页边距与章节层次。</p>
      </section>
    </aside>

    <article class="judgment-body">
      <details class="summary-box" open>
        <summary>摘要</summary>
        <p>{summary_html}</p>
      </details>
      {case.body_html}
    </article>
  </main>
</div>
"""
    return page_shell(f"{case.number} | {case.theme}", body, "detail-page", "../")


STYLE_CSS = r"""
:root {
  --bg: #f5efe4;
  --bg-soft: #fbf7f1;
  --panel: rgba(255, 251, 245, 0.92);
  --panel-strong: #fffdf9;
  --ink: #1f1a17;
  --muted: #6d6257;
  --accent: #8b2e1f;
  --accent-soft: #c65d38;
  --line: rgba(71, 48, 32, 0.16);
  --shadow: 0 20px 60px rgba(60, 39, 24, 0.12);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(198, 93, 56, 0.16), transparent 34%),
    radial-gradient(circle at top right, rgba(92, 122, 113, 0.14), transparent 26%),
    linear-gradient(180deg, #f8f2e8 0%, #f1e9dd 100%);
  font-family: "Noto Serif TC", "Source Han Serif TC", serif;
}

a { color: inherit; text-decoration: none; }
code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }

.site-shell {
  width: min(1200px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0 60px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.topbar__links {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  color: var(--muted);
}

.brand {
  font-family: "Fraunces", Georgia, serif;
  font-size: 1rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero, .sub-hero, .detail-hero {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(255,255,255,0.72), rgba(255,249,241,0.96));
  box-shadow: var(--shadow);
  padding: 28px;
}

.hero::after, .sub-hero::after, .detail-hero::after {
  content: "";
  position: absolute;
  inset: auto -8% -20% auto;
  width: 280px;
  height: 280px;
  background: radial-gradient(circle, rgba(139,46,31,0.16), transparent 70%);
  pointer-events: none;
}

.hero__content {
  display: grid;
  grid-template-columns: 1.6fr 0.8fr;
  gap: 24px;
  align-items: end;
  margin: 52px 0 24px;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 0.8rem;
}

h1, h2, h3 {
  font-family: "Fraunces", Georgia, serif;
  line-height: 1.1;
  margin: 0;
}

h1 { font-size: clamp(2.4rem, 7vw, 4.8rem); max-width: 12ch; }
h2 { font-size: clamp(1.8rem, 4vw, 2.8rem); }
h3 { font-size: 1.25rem; }

.hero__lead {
  max-width: 68ch;
  color: var(--muted);
  font-size: 1rem;
  line-height: 1.9;
  margin-top: 18px;
}

.hero-panel, .stat-card, .case-card__link, .summary-box, .detail-sidebar section {
  border: 1px solid var(--line);
  background: var(--panel);
  backdrop-filter: blur(10px);
  box-shadow: var(--shadow);
}

.hero-panel {
  border-radius: 24px;
  padding: 20px;
}

.hero-panel__label, .hero-panel__note { color: var(--muted); margin: 0; }
.hero-panel__value {
  font-family: "Fraunces", Georgia, serif;
  font-size: 4.2rem;
  margin: 6px 0;
}

.stat-grid, .case-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  border-radius: 20px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-card__value {
  font-family: "Fraunces", Georgia, serif;
  font-size: 2.2rem;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  margin-bottom: 16px;
}

.text-link { color: var(--accent); }

main { margin-top: 26px; display: grid; gap: 28px; }

.search-section, .year-panel, .year-directory, .detail-layout {
  border: 1px solid var(--line);
  border-radius: 28px;
  background: rgba(255, 252, 247, 0.8);
  padding: 24px;
}

.search-box input {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 16px 18px;
  background: rgba(255,255,255,0.86);
  font: inherit;
}

.search-results {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.search-result {
  display: block;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: #fffaf3;
}

.search-result strong {
  display: block;
  margin-bottom: 6px;
}

.case-card__link {
  display: block;
  height: 100%;
  border-radius: 22px;
  padding: 18px;
  transition: transform 180ms ease, border-color 180ms ease;
}

.case-card__link:hover {
  transform: translateY(-3px);
  border-color: rgba(139,46,31,0.3);
}

.case-card__top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.meta-chip {
  margin: 0;
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(139,46,31,0.08);
  color: var(--accent);
  font-size: 0.84rem;
}

.case-number, .case-summary { color: var(--muted); }
.case-number { margin: 8px 0 6px; }
.case-summary { line-height: 1.8; margin: 0; }

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.tag-row span {
  border-radius: 999px;
  background: rgba(28, 54, 48, 0.08);
  color: #24453f;
  padding: 6px 10px;
  font-size: 0.82rem;
}

.table-wrap { overflow-x: auto; }

.directory-table {
  width: 100%;
  border-collapse: collapse;
}

.directory-table th,
.directory-table td {
  border-bottom: 1px solid var(--line);
  padding: 16px 12px;
  text-align: left;
  vertical-align: top;
}

.directory-table th {
  color: var(--muted);
  font-weight: 600;
}

.detail-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.detail-sidebar {
  position: sticky;
  top: 18px;
  display: grid;
  gap: 16px;
}

.detail-sidebar section {
  border-radius: 22px;
  padding: 18px;
}

.detail-sidebar dl {
  margin: 12px 0 0;
  display: grid;
  gap: 10px;
}

.detail-sidebar dt {
  color: var(--muted);
  font-size: 0.88rem;
}

.detail-sidebar dd {
  margin: 0;
  line-height: 1.7;
}

.detail-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.detail-meta div {
  border-top: 1px solid var(--line);
  padding-top: 10px;
}

.detail-meta span {
  display: block;
  color: var(--muted);
  margin-bottom: 4px;
}

.judgment-body {
  min-width: 0;
  border-radius: 28px;
  background: var(--panel-strong);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  padding: clamp(22px, 4vw, 42px);
}

.judgment-body p,
.judgment-body li {
  line-height: 2;
  margin: 0 0 1.1em;
}

.judgment-body h2,
.judgment-body h3 {
  margin: 1.4em 0 0.8em;
}

.summary-box {
  border-radius: 18px;
  padding: 14px 18px;
  margin-bottom: 22px;
}

.summary-box summary {
  cursor: pointer;
  font-family: "Fraunces", Georgia, serif;
}

.footer {
  color: var(--muted);
  padding: 18px 4px 0;
}

[hidden] { display: none !important; }

@media (max-width: 960px) {
  .hero__content,
  .detail-layout,
  .stat-grid,
  .case-grid,
  .detail-meta {
    grid-template-columns: 1fr;
  }

  .detail-sidebar {
    position: static;
  }
}
"""


APP_JS = r"""
function initSearch() {
  const input = document.getElementById("global-search");
  const results = document.getElementById("search-results");
  const payload = document.getElementById("search-data");
  if (!input || !results || !payload) return;
  const items = JSON.parse(payload.textContent);

  const render = (query) => {
    const value = query.trim().toLowerCase();
    if (!value) {
      results.innerHTML = "";
      return;
    }
    const matches = items
      .filter((item) => `${item.number} ${item.theme} ${item.summary}`.toLowerCase().includes(value))
      .slice(0, 12);

    results.innerHTML = matches.length
      ? matches.map((item) => `
          <a class="search-result" href="${item.url}">
            <strong>${item.number} · ${item.theme}</strong>
            <span>${item.year_bucket} · ${item.lang}</span>
            <p>${item.summary}</p>
          </a>
        `).join("")
      : `<div class="search-result"><strong>没有匹配结果</strong><span>请尝试更短的关键词或案件编号。</span></div>`;
  };

  input.addEventListener("input", (event) => render(event.target.value));
}

function initTableSearch() {
  document.querySelectorAll(".table-search").forEach((input) => {
    const table = input.closest(".year-directory")?.querySelector("tbody");
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("tr"));
    input.addEventListener("input", (event) => {
      const value = event.target.value.trim().toLowerCase();
      rows.forEach((row) => {
        const haystack = row.dataset.search || row.textContent.toLowerCase();
        row.hidden = value ? !haystack.includes(value) : false;
      });
    });
  });
}

initSearch();
initTableSearch();
"""


def write_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (ASSETS / "app.js").write_text(APP_JS, encoding="utf-8")


def main() -> None:
    if OUTPUT.exists():
      shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_assets()

    grouped: dict[str, list[CaseRecord]] = {bucket: [] for bucket, _, _ in YEAR_BUCKETS}
    all_cases: list[CaseRecord] = []
    moved_cases: list[CaseRecord] = []

    for source_bucket, folder in SOURCE_DIRS:
        for path in folder.glob("*.txt"):
            case = parse_case(path, source_bucket)
            grouped.setdefault(case.year_bucket, []).append(case)
            all_cases.append(case)
            if case.year_bucket != case.source_bucket:
                moved_cases.append(case)

    for bucket in grouped:
        grouped[bucket].sort(key=lambda c: (c.decision_year or 0, c.date, c.number))
    all_cases.sort(key=lambda c: (c.decision_year or 0, c.date, c.number))

    (OUTPUT / "index.html").write_text(render_home(all_cases, grouped), encoding="utf-8")

    for bucket, cases in grouped.items():
        target_dir = OUTPUT / bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "index.html").write_text(render_year_index(bucket, cases), encoding="utf-8")
        for case in cases:
            (target_dir / f"{case.slug}.html").write_text(render_case(case), encoding="utf-8")

    mismatch_report = [
        {
            "number": case.number,
            "date": case.date,
            "decision_year": case.decision_year,
            "source_bucket": case.source_bucket,
            "year_bucket": case.year_bucket,
            "source_name": case.source_name,
            "source_relpath": case.source_relpath,
        }
        for case in sorted(moved_cases, key=lambda c: (c.decision_year or 0, c.number))
    ]
    (OUTPUT / "bucket-reassignment-report.json").write_text(
        json.dumps(mismatch_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()



