"""Generate one static Pages site per Apple fork + a hub. Data in data/*.json."""
import json, html, os, re, shutil, datetime
from collections import Counter

ORG = "arcade-agent"
REPOS = {
    "pkl": "Configuration language on the JVM",
    "servicetalk": "Reactive networking library on Netty",
    "app-store-server-library-java": "App Store Server API SDK for Java",
    "pkl-spring": "Pkl integration for Spring",
}
# Static build/CI audit. Every row is backed by a grep of the upstream default branch (see `evidence`).
AUDIT = {
    "pkl": [
        ("Gradle parallel + local build cache", "on", "gradle.properties: org.gradle.parallel=true, org.gradle.caching=true"),
        ("CI Gradle setup", "on", "gradle/actions/setup-gradle in .github/workflows/build.yml"),
        ("Configuration cache", "off", "Not enabled in gradle.properties; only referenced by pkl-gradle plugin tests"),
        ("Test fork tuning", "info", "maxParallelForks / forkEvery are templated in build-logic/.../BuildInfo.kt"),
        ("CI daemon", "info", "CI runs ./gradlew --no-daemon ... check with -DpklMultiJdkTesting=true"),
    ],
    "servicetalk": [
        ("Gradle parallel + local build cache", "on", "gradle.properties: org.gradle.parallel=true, org.gradle.caching=true, configureondemand=true"),
        ("Configuration cache", "off", "No reference anywhere in the repo"),
        ("Remote build cache / Develocity", "off", "No reference anywhere in the repo"),
        ("PR CI matrix", "info", "ci-prb.yml: JDK 8/11/17/21/25 on ubuntu, JDK 11 on self-hosted macOS, plus a Netty 4.1.x variant; each runs the full suite"),
        ("JUnit class parallelism", "off", "junit-platform.properties: parallel.enabled=true but mode.default and mode.classes.default are same_thread"),
        ("Workflow timeouts", "off", "No timeout-minutes in .github/workflows"),
        ("Test sharding within a module", "off", "None found; a job runs one module's tests sequentially"),
    ],
    "app-store-server-library-java": [
        ("Gradle parallel / caching in gradle.properties", "off", "gradle.properties sets only version and group"),
        ("CI command", "info", "ci-prb.yml: ./gradlew --no-daemon --parallel clean test on JDK 17/21/25; `clean` discards up-to-date outputs"),
        ("CI dependency cache", "on", "actions/setup-java with cache: gradle"),
        ("Configuration cache", "off", "No reference anywhere in the repo"),
    ],
    "pkl-spring": [
        ("Gradle parallel", "on", "gradle.properties: org.gradle.parallel=true"),
        ("Local build cache", "off", "org.gradle.caching not set"),
        ("Configuration cache", "off", "No reference anywhere in the repo"),
        ("CI command", "info", "prb.yml/build.yml: ./gradlew build on JDK 21 with setup-java cache: gradle"),
    ],
}

CSS = """
:root{--bg:#fbfbfa;--fg:#1c1c1a;--mut:#6b6a63;--line:#e3e2dc;--card:#fff;--acc:#2a5db0;--ok:#2f7d4f;--warn:#b26a00;--bad:#b3362b}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#16161a;--fg:#e8e8e4;--mut:#9a9990;--line:#2c2c33;--card:#1e1e24;--acc:#7aa7f0;--ok:#63c28a;--warn:#e0a24a;--bad:#ef7b6f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,system-ui,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:.2em 0}h2{font-size:18px;margin:2em 0 .6em;border-bottom:1px solid var(--line);padding-bottom:.3em}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.mut{color:var(--mut)}.crumb{font-size:13px;color:var(--mut)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.card b{display:block;font-size:22px}.card span{font-size:12px;color:var(--mut)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:14px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;color:var(--mut);font-weight:600}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;border:1px solid var(--line);color:var(--mut);margin-right:4px}
.on{color:var(--ok)}.off{color:var(--warn)}.info{color:var(--mut)}
.bar{height:8px;background:var(--acc);border-radius:4px;opacity:.7}
code{font:12.5px ui-monospace,Menlo,monospace;word-break:break-all}
.note{font-size:13px;color:var(--mut);background:var(--card);border:1px solid var(--line);border-left:3px solid var(--warn);padding:8px 12px;border-radius:4px}
select{font:inherit;padding:3px 6px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px}
@media(max-width:600px){table{font-size:13px}.hide-sm{display:none}}
"""
E = html.escape


def page(title, body, root=""):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)}</title>'
            f'<style>{CSS}</style></head><body><main>{body}</main></body></html>')


def kind_of(path):
    p = path.lower()
    if p.startswith(".github/"): return "ci"
    if re.search(r"(^|/)(build\.gradle(\.kts)?|settings\.gradle(\.kts)?|gradle\.properties|gradlew(\.bat)?|gradle/|buildsrc/|build-logic/|.*\.gradle\.kts$)", p): return "build"
    if re.search(r"(^|/)(src/)?(test|tests|testfixtures|jmh)(/|$)|test\.(java|kt)$", p) or "/src/test" in p: return "test"
    if p.endswith((".md", ".adoc", ".txt")) or p.startswith(("docs/", "docs-site/")): return "docs"
    if "/src/main/" in p or p.startswith("src/main/"): return "main"
    return "other"


def pr_class(kinds):
    k = set(kinds)
    return next(iter(k)) + "-only" if len(k) == 1 else "mixed"


def module_of(path, repo):
    parts = path.split("/")
    if repo == "app-store-server-library-java" or len(parts) == 1: return parts[0] if len(parts) == 1 else "/".join(parts[:2]) if parts[0] == "src" else parts[0]
    return parts[0]


def fmt_date(s):
    return s[:10] if s else "-"


def metrics_map(base):
    return {m["name"]: m for m in base["metrics"]}


def perf_section(repo, root):
    """Render any measured Gradle --profile result captured in data/<repo>.perf.*.json."""
    out = ""
    for fn in sorted(os.listdir("data")):
        if fn.startswith(repo + ".perf.") and fn.endswith(".json"):
            d = json.load(open("data/" + fn))
            out += (f'<tr><td><code>{E(d["cmd"])}</code></td><td>{d["wall_s"]} s</td><td>{E(d["result"])}</td>'
                    f'<td class="mut">{E(d["note"])}</td></tr>')
    if not out:
        return '<p class="mut">No measured Gradle run for this repository (static audit only).</p>'
    return ('<table><tr><th>Command</th><th>Wall</th><th>Result</th><th>Note</th></tr>' + out + '</table>'
            '<p class="mut">Single cold run on one laptop (macOS, JDK 25), no repetition: a data point, not a benchmark.</p>')


def build_repo(repo):
    a = json.load(open(f"data/{repo}.analysis.json"))
    prs = json.load(open(f"data/{repo}.prs.json"))
    base = a["base"]
    mm = metrics_map(base)
    out = f"site/{repo}"
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(f"{out}/pr")
    upstream = f"https://github.com/apple/{repo}"
    smells = base["smells"]
    comps = sorted(base["components"], key=lambda c: -c["size"])
    mx = max([c["size"] for c in comps] or [1])

    rows = []
    for p in sorted(prs, key=lambda p: -p["number"]):
        kinds = [kind_of(f) for f in p["files"]]
        cls = pr_class(kinds) if kinds else "empty"
        imp = a["impacts"].get(str(p["number"]), {})
        comps_hit = ", ".join(imp.get("affected_components", [])) or "-"
        rows.append((p, cls, imp, comps_hit))
        write_pr(out, repo, p, cls, imp, kinds, upstream)

    cls_counts = Counter(r[1] for r in rows)
    body = f'<div class="crumb"><a href="https://{ORG}.github.io/apple-oss-lab/">apple-oss-lab</a> / {repo}</div>'
    body += f'<h1>apple/{repo}</h1><p class="mut">{E(REPOS[repo])}. Architecture and build analysis by <a href="https://github.com/{ORG}/arcade-agent">arcade-agent</a>. Upstream: <a href="{upstream}">apple/{repo}</a> · Fork: <a href="https://github.com/{ORG}/{repo}">{ORG}/{repo}</a></p>'
    body += ('<div class="note">Scope: static analysis of the default branch plus GitHub metadata for open PRs and the 30 most recently merged PRs. '
             f'Java sources only ({base["entities"]} entities, tests excluded); Kotlin files are not parsed. '
             'This is an independent, unofficial analysis; it does not evaluate people.</div>')
    body += '<h2>Architecture baseline</h2><div class="grid">'
    for v, l in [(base["entities"], "entities"), (base["edges"], "dependency edges"), (len(comps), "components (package-based)"),
                 (len(smells), "smells"), (mm.get("RCI", {}).get("value", "-"), "RCI (intra-edge ratio)"),
                 (mm.get("BasicMQ", {}).get("value", "-"), "BasicMQ")]:
        body += f'<div class="card"><b>{v}</b><span>{l}</span></div>'
    body += '</div><h2>Components</h2><table><tr><th>Component</th><th>Entities</th><th class="hide-sm"></th></tr>'
    for c in comps:
        body += f'<tr><td>{E(c["name"])}</td><td>{c["size"]}</td><td class="hide-sm" style="width:40%"><div class="bar" style="width:{max(2, 100*c["size"]//mx)}%"></div></td></tr>'
    body += '</table>'
    body += f'<h2>Architectural smells ({len(smells)})</h2>'
    if smells:
        body += '<table><tr><th>Type</th><th>Severity</th><th>Description</th></tr>'
        for s in sorted(smells, key=lambda s: {"high": 0, "medium": 1, "low": 2}.get(s["severity"], 3)):
            body += f'<tr><td>{E(s["smell_type"])}</td><td>{E(s["severity"])}</td><td>{E(s["description"])}</td></tr>'
        body += '</table>'
    else:
        body += '<p class="mut">None detected by the package-based recovery.</p>'
    body += '<h2>Build &amp; CI audit (Gradle)</h2><p class="mut">Same measure → report → fix methodology as mvn-perf, ported to Gradle (mvn-perf itself only hooks Maven). Each row cites where it was found.</p><table><tr><th>Check</th><th>State</th><th>Evidence</th></tr>'
    for name, st, ev in AUDIT[repo]:
        body += f'<tr><td>{E(name)}</td><td class="{st}">{st}</td><td class="mut">{E(ev)}</td></tr>'
    body += '</table><h3>Measured</h3>' + perf_section(repo, "")
    body += f'<h2>Pull requests ({len(rows)})</h2><p>Filter: <select id="fs"><option value="">all states</option><option>open</option><option>merged</option></select> <select id="fk"><option value="">all kinds</option>'
    for k in sorted(cls_counts): body += f'<option>{k}</option>'
    body += '</select></p><table id="t"><tr><th>#</th><th>Title</th><th>State</th><th>Kind</th><th class="hide-sm">Components</th><th>+/−</th></tr>'
    for p, cls, imp, ch in rows:
        body += (f'<tr data-s="{p["state"]}" data-k="{cls}"><td><a href="pr/{p["number"]}.html">{p["number"]}</a></td><td>{E(p["title"])}</td>'
                 f'<td>{p["state"]}</td><td><span class="tag">{cls}</span></td><td class="hide-sm">{E(ch)}</td><td>+{p["additions"]}/−{p["deletions"]}</td></tr>')
    body += ('</table><script>const s=document.getElementById("fs"),k=document.getElementById("fk");'
             'function f(){document.querySelectorAll("#t tr[data-s]").forEach(r=>{r.hidden=(s.value&&r.dataset.s!=s.value)||(k.value&&r.dataset.k!=k.value)})}'
             's.onchange=k.onchange=f</script>')
    body += f'<p class="mut">Generated {datetime.date.today()} · arcade-agent baseline computed in {base["seconds"]} s.</p>'
    open(f"{out}/index.html", "w").write(page(f"apple/{repo} · architecture and PR analysis", body))
    open(f"{out}/.nojekyll", "w").write("")
    return dict(repo=repo, desc=REPOS[repo], prs=len(rows), entities=base["entities"], comps=len(comps), smells=len(smells))


def write_pr(out, repo, p, cls, imp, kinds, upstream):
    kc = Counter(kinds)
    mods = Counter(module_of(f, repo) for f in p["files"])
    body = f'<div class="crumb"><a href="../index.html">{repo}</a> / PR {p["number"]}</div><h1>{E(p["title"])}</h1>'
    body += f'<p><a href="{p["url"]}">apple/{repo}#{p["number"]}</a> <span class="tag">{p["state"]}</span><span class="tag">{cls}</span></p><div class="grid">'
    for v, l in [(f'+{p["additions"]}/−{p["deletions"]}', "lines"), (p["changed_files"], "files"), (p["comments"], "comments"),
                 (fmt_date(p["created"]), "opened"), (fmt_date(p["merged_at"]), "merged")]:
        body += f'<div class="card"><b>{v}</b><span>{l}</span></div>'
    body += '</div><h2>What it touches</h2><p>' + " ".join(f'<span class="tag">{k}: {n}</span>' for k, n in kc.most_common()) + '</p>'
    body += '<p>Modules: ' + ", ".join(f'<code>{E(m)}</code> ({n})' for m, n in mods.most_common(6)) + '</p>'
    body += '<h2>Architectural impact (arcade-agent <code>diff_impact</code>)</h2>'
    if imp.get("matched_files"):
        body += (f'<div class="grid"><div class="card"><b>{len(imp["matched_files"])}</b><span>files mapped to the graph</span></div>'
                 f'<div class="card"><b>{imp["num_changed_entities"]}</b><span>entities in those files</span></div>'
                 f'<div class="card"><b>{E(", ".join(imp["affected_components"]) or "-")}</b><span>components</span></div>'
                 f'<div class="card"><b>{imp["num_downstream"]}</b><span>entities within 3 hops downstream</span></div></div>')
        bc = imp.get("broken_contracts", [])[:8]
        if bc:
            body += '<h3>Most depended-upon changed entities</h3><table><tr><th>Entity</th><th>Dependents</th></tr>'
            for b in sorted(bc, key=lambda b: -b["num_dependents"]):
                body += f'<tr><td><code>{E(b["fqn"])}</code></td><td>{b["num_dependents"]}</td></tr>'
            body += '</table>'
        body += ('<p class="note">Computed against the current default branch, not the PR base commit; files renamed or deleted since then are '
                 'unmatched. Downstream counts are a reverse-dependency closure to depth 3 and over-approximate real blast radius.</p>')
    else:
        body += ('<p class="mut">No production Java file of this PR maps into the dependency graph '
                 f'({"tests, build, CI or docs only" if cls != "main-only" else "files not present on the current default branch"}). '
                 'Tests are excluded from the graph by design.</p>')
    flags = []
    if kc["build"]: flags.append("Touches Gradle/build files: review for build-time or cache impact.")
    if kc["ci"]: flags.append("Touches CI workflows: review runner matrix, timeouts, caching.")
    if any("junit-platform.properties" in f for f in p["files"]): flags.append("Changes JUnit platform properties (test parallelism).")
    if flags:
        body += '<h2>Build &amp; CI relevance</h2><ul>' + "".join(f"<li>{E(x)}</li>" for x in flags) + '</ul>'
    body += '<h2>Files</h2><table>' + "".join(f'<tr><td><span class="tag">{kind_of(f)}</span></td><td><code>{E(f)}</code></td></tr>' for f in p["files"][:60]) + '</table>'
    if len(p["files"]) > 60: body += f'<p class="mut">… and {len(p["files"])-60} more files.</p>'
    open(f"{out}/pr/{p['number']}.html", "w").write(page(f"apple/{repo}#{p['number']} · {p['title']}", body))


def build_hub(cards):
    os.makedirs("site/apple-oss-lab", exist_ok=True)
    body = f'<h1>apple-oss-lab</h1><p class="mut">Architecture and build analysis of four open-source Apple JVM repositories, one site per fork, one page per PR. Made with <a href="https://github.com/{ORG}/arcade-agent">arcade-agent</a>. Independent and unofficial; not affiliated with Apple.</p><div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">'
    for c in cards:
        body += (f'<a class="card" href="https://{ORG}.github.io/{c["repo"]}/"><b style="font-size:17px">{c["repo"]}</b><span>{E(c["desc"])}</span>'
                 f'<br><span>{c["prs"]} PRs · {c["entities"]} entities · {c["comps"]} components · {c["smells"]} smells</span></a>')
    body += f'</div><p class="mut">Generated {datetime.date.today()}.</p>'
    open("site/apple-oss-lab/index.html", "w").write(page("apple-oss-lab", body))
    open("site/apple-oss-lab/.nojekyll", "w").write("")


if __name__ == "__main__":
    os.makedirs("site", exist_ok=True)
    cards = [build_repo(r) for r in REPOS]
    build_hub(cards)
    print(cards)
