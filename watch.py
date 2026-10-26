"""Simplify Summer2027-Internships watcher -> ntfy push.

Runs in GitHub Actions every ~5 min. Keeps state in state.json.
Edit the CONFIG block to change what you get pinged for.
"""
import json, os, re, sys, urllib.request

# ---------------- CONFIG ----------------
REPO = "SimplifyJobs/Summer2027-Internships"
BRANCH = "dev"
CATEGORIES = {"Software", "Software Engineering", "AI/ML/Data",
              "Data Science, AI & Machine Learning"}  # add "Quant", "Hardware", "Product" if wanted
TERM_MATCH = "2027"            # any term containing this (Spring/Summer/Fall/Winter 2027)
US_ONLY = True
# High-priority pings (louder notification, "star" tag)
HIGH_LOC = re.compile(r"(, MA$|Massachusetts|Boston|Cambridge|NYC|New York|, NY$|Jersey City|Hoboken|Providence|, RI$|Remote)", re.I)
HIGH_TITLE = re.compile(r"co-?op", re.I)
MAX_INDIVIDUAL = 25            # per run; extras get rolled into one summary ping
# ----------------------------------------

US_NAMES = {"NYC", "LA", "SF", "United States", "Remote in USA", "Remote in US", "USA", "Remote"}
US_STATES = {"Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut","Delaware","Florida",
 "Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana","Maine","Maryland",
 "Massachusetts","Michigan","Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada","New Hampshire",
 "New Jersey","New Mexico","New York","North Carolina","North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania",
 "Rhode Island","South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont","Virginia","Washington",
 "West Virginia","Wisconsin","Wyoming","Washington, DC"}

STATE_FILE = "state.json"
TOPIC = os.environ.get("NTFY_TOPIC", "")
DRY = os.environ.get("DRY_RUN") == "1"
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "simplify-watcher", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def is_us(loc):
    loc = loc.strip()
    return bool(re.search(r", [A-Z]{2}$", loc)) or loc in US_NAMES or loc in US_STATES or loc.startswith("Remote in US")


def wanted(x):
    if not (x.get("active") and x.get("is_visible", True)):
        return False
    if x.get("category") not in CATEGORIES:
        return False
    if not any(TERM_MATCH in t for t in x.get("terms", [])):
        return False
    if US_ONLY and not any(is_us(l) for l in x.get("locations", [])):
        return False
    return True


def is_high(x):
    return bool(HIGH_TITLE.search(x.get("title", ""))) or any(HIGH_LOC.search(l) for l in x.get("locations", []))


def push(title, message, click=None, priority=3, tags=None):
    body = {"topic": TOPIC, "title": title, "message": message, "priority": priority}
    if click: body["click"] = click
    if tags: body["tags"] = tags
    if DRY or not TOPIC:
        print("PUSH", json.dumps(body)); return
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def main():
    state = {"sha": None, "seen": []}
    if os.path.exists(STATE_FILE):
        state = json.load(open(STATE_FILE))
    seen = set(state["seen"])

    if os.environ.get("LOCAL_FILE"):  # offline testing
        sha, data = "local", json.load(open(os.environ["LOCAL_FILE"]))
    else:
        sha, data = fetch(state)
        if data is None:
            print("no upstream change"); return
    _process(state, seen, sha, data)


def fetch(state):
    hdr = {"Authorization": f"Bearer {GH_TOKEN}"} if GH_TOKEN else {}
    sha = json.loads(get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}", hdr))["sha"]
    if sha == state.get("sha") and state["seen"]:
        return sha, None
    return sha, json.loads(get(f"https://raw.githubusercontent.com/{REPO}/{sha}/.github/scripts/listings.json"))


def _process(state, seen, sha, data):

    first_run = not seen
    new = [x for x in data if x["id"] not in seen and wanted(x)]
    seen |= {x["id"] for x in data}

    if first_run:
        push("Internship watcher is live", f"Seeded {len(seen)} listings. You'll get pinged for new matches.", tags=["white_check_mark"])
    else:
        new.sort(key=lambda x: not is_high(x))  # high-priority first
        for x in new[:MAX_INDIVIDUAL]:
            high = is_high(x)
            locs = ", ".join(x.get("locations", [])[:3])
            terms = ", ".join(x.get("terms", []))
            push(f"{x['company_name']}: {x['title']}", f"{locs}\n{terms}",
                 click=x.get("url"), priority=5 if high else 3,
                 tags=["star"] if high else ["briefcase"])
        extra = new[MAX_INDIVIDUAL:]
        if extra:
            push(f"+{len(extra)} more new internships",
                 "\n".join(f"{x['company_name']}: {x['title']}" for x in extra[:40]),
                 click=f"https://github.com/{REPO}", tags=["inbox_tray"])
    print(f"sha={sha[:7]} new_matches={len(new)} first_run={first_run}")

    state = {"sha": sha, "seen": sorted(seen)}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
