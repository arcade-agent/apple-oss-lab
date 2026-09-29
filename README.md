# apple-oss-lab

Architecture and build analysis of four open-source Apple JVM repositories, produced with [arcade-agent](https://github.com/arcade-agent/arcade-agent).
Independent and unofficial; not affiliated with Apple.

Sites: [pkl](https://arcade-agent.github.io/pkl/) · [servicetalk](https://arcade-agent.github.io/servicetalk/) · [app-store-server-library-java](https://arcade-agent.github.io/app-store-server-library-java/) · [pkl-spring](https://arcade-agent.github.io/pkl-spring/)

Pipeline (`tools/`): `collect.py` (GitHub API → PR metadata) → `analyze_repo.py` (arcade-agent baseline + `diff_impact` per PR) → `perf.sh` (Gradle `--profile`) → `gen_site.py` (static pages).
Scripts expect `src/<repo>` clones and a `data/` directory next to them.
