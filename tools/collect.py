import json, subprocess, sys
def gh(*a):
    return json.loads(subprocess.check_output(["gh","api",*a]))
# PRs always included regardless of recency (flaky-test lane reviewed earlier)
EXTRA={"servicetalk":[3506,3521,3535,3570,3606,3622,3630]}
for repo in (sys.argv[1:] or ["pkl","servicetalk","app-store-server-library-java","pkl-spring"]):
    full=f"apple/{repo}"
    opens=gh("--paginate",f"repos/{full}/pulls?state=open&per_page=100")
    merged=gh(f"search/issues?q=repo:{full}+type:pr+is:merged&sort=updated&order=desc&per_page=30")["items"]
    nums=list(dict.fromkeys([p["number"] for p in opens]+[m["number"] for m in merged]+EXTRA.get(repo,[])))
    out=[]
    for n in nums:
        p=gh(f"repos/{full}/pulls/{n}")
        files=[f["filename"] for f in gh("--paginate",f"repos/{full}/pulls/{n}/files?per_page=100")]
        out.append(dict(number=n,title=p["title"],author=p["user"]["login"],state="merged" if p["merged_at"] else p["state"],
            draft=p["draft"],created=p["created_at"],merged_at=p["merged_at"],additions=p["additions"],deletions=p["deletions"],
            changed_files=p["changed_files"],comments=p["comments"]+p["review_comments"],labels=[l["name"] for l in p["labels"]],
            url=p["html_url"],base=p["base"]["ref"],files=files))
    json.dump(out,open(f"data/{repo}.prs.json","w"),indent=1)
    print(repo,len(out),flush=True)
