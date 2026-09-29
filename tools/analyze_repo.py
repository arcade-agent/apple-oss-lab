import json, sys, dataclasses, time, traceback
from arcade_agent.tools.analyze import _run_sync_pipeline
from arcade_agent.tools.diff_impact import diff_impact
repo, lang = sys.argv[1], (sys.argv[2] if len(sys.argv)>2 and sys.argv[2]!="auto" else None)
t=time.time()
r=_run_sync_pipeline(f"src/{repo}", language=lang, exclude_tests=True, use_cache=False)
def d(x):
    return dataclasses.asdict(x) if dataclasses.is_dataclass(x) else x
arch=r.architecture
comps=[dict(name=c.name,size=len(c.entities)) for c in arch.components]
base=dict(repo=repo,language=r.repository.language,seconds=round(time.time()-t,1),
    entities=len(r.graph.entities),edges=len(r.graph.edges),
    components=comps,smells=[d(s) for s in r.smells],metrics=[d(m) for m in r.metrics])
prs=json.load(open(f"data/{repo}.prs.json"))
impacts={}
for p in prs:
    try:
        impacts[p["number"]]=diff_impact(r.graph,p["files"],arch)
    except Exception as e:
        impacts[p["number"]]={"error":repr(e)}
json.dump(dict(base=base,impacts=impacts),open(f"data/{repo}.analysis.json","w"),indent=1,default=str)
print(repo,base["language"],base["entities"],"entities",len(comps),"components",len(base["smells"]),"smells",base["seconds"],"s")
