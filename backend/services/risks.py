"""
Redirect quality checks. Pure functions: rows in, findings out.

Every finding says WHERE it came from:
  proposal      - found by looking at the mappings we propose (always true, no live site needed)
  supplied_data - found in crawl data the user imported (status codes); only as reliable as that data
Things that need the live website or the server's own redirect rules (for example a chain through a rule
we never saw) are NOT claimed here. They are listed in NOT_CHECKED so the user knows.
"""
from collections import defaultdict
from fnmatch import fnmatchcase

NOT_CHECKED = [
    "Redirects that already exist on your server or CDN. Chains and loops that involve them can only be found by testing the live site.",
    "Whether each destination page really loads (status codes are checked only when you imported them from a crawl).",
    "Whether a destination is truly the right replacement for visitors and search engines: scores are similarity, not proof.",
]


def _risk(kind, severity, row, message, source="proposal", detail=None, new_id=None):
    return {
        "kind": kind, "severity": severity, "source": source,
        "old_id": row["old_id"] if row else None,
        "new_id": new_id if new_id is not None else (row["final_new_id"] if row else None),
        "review_id": row["review_id"] if row else None,
        "message": message[:500], "detail": detail or {},
    }


def _matches_excluded(path_key, patterns):
    path = path_key.split("?")[0]
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def evaluate(rows, new_pages, config):
    """
    rows      : one dict per old URL with keys review_id, old_id, old_full, old_path_key, final_new_id, final_full,
                final_path_key, final_status_code, status, origin, score
    new_pages : list of dicts with id, full
    """
    thresholds = config["thresholds"]
    excluded = [p for p in config.get("excluded_patterns", []) if p]
    findings = []

    active = [r for r in rows if r["final_new_id"] and r["status"] != "rejected"]  # mappings that would become rules
    source_graph = {r["old_full"]: r for r in active}

    # 1. old URLs that will not be redirected anywhere
    for r in rows:
        if not r["final_new_id"]:
            findings.append(_risk("no_destination", "medium", r, "No destination was found for this old URL. Assign one manually or leave it unredirected on purpose."))
        elif r["status"] == "rejected":
            findings.append(_risk("no_destination", "medium", r, "The suggested destination was rejected and no other destination is set."))

    # 2. new URLs nothing redirects to
    used = {r["final_new_id"] for r in active}
    for page in new_pages:
        if page["id"] not in used:
            findings.append(_risk("orphan_new_url", "info", None, "No old URL is mapped to this new page.", new_id=page["id"]))

    # 3. duplicate sources (the database prevents this; the check proves it)
    counts = defaultdict(int)
    for r in rows:
        counts[r["old_full"]] += 1
    for r in rows:
        if counts[r["old_full"]] > 1:
            findings.append(_risk("duplicate_source", "high", r, "This old URL appears more than once, so its rule would be ambiguous."))

    # 4. many old URLs -> one destination (allowed, but a person must confirm it is intentional)
    by_destination = defaultdict(list)
    for r in active:
        by_destination[r["final_new_id"]].append(r)
    for new_id, group in by_destination.items():
        if len(group) > 1:
            for r in group:
                findings.append(_risk("many_to_one", "medium", r, f"{len(group)} old URLs are mapped to this same destination. Confirm this is intended.", detail={"count": len(group)}))

    # 5-6. self redirects, chains and loops inside the proposed rules
    for r in active:
        if r["old_full"] == r["final_full"]:
            findings.append(_risk("self_redirect", "high", r, "This URL redirects to itself."))
            continue
        trail, current, loop = [r["old_full"]], r["final_full"], False
        for _ in range(len(active) + 1):
            if current in trail:
                loop = True
                break
            trail.append(current)
            nxt = source_graph.get(current)
            if nxt is None or nxt["old_full"] == nxt["final_full"]:
                break
            current = nxt["final_full"]
        if loop:
            findings.append(_risk("redirect_loop", "high", r, "These proposed redirects form a loop.", detail={"trail": trail[:6]}))
        elif len(trail) > 2:
            findings.append(_risk("redirect_chain", "medium", r, "The destination is itself redirected by another proposed rule, creating a chain. Point this rule at the final page.", detail={"trail": trail[:6]}))

    # 7. problems visible in supplied crawl data
    for r in active:
        code = r.get("final_status_code")
        if code and code >= 400:
            findings.append(_risk("invalid_destination", "high", r, f"The imported crawl data says the destination returns status {code}.", source="supplied_data", detail={"status_code": code}))
        elif code and 300 <= code < 400:
            findings.append(_risk("redirect_chain", "medium", r, f"The imported crawl data says the destination itself redirects (status {code}).", source="supplied_data", detail={"status_code": code}))

    # 8. weak matches that someone approved
    for r in active:
        if r["status"] == "approved" and r["origin"] == "auto" and r["score"] < thresholds["medium"]:
            findings.append(_risk("weak_match", "medium", r, f"Approved with a low similarity score ({r['score']}). Check that the pages really replace each other.", detail={"score": r["score"]}))

    # 9. redirects to the home page
    to_home = [r for r in active if r["final_path_key"] == "/" and r["old_path_key"].split("?")[0] != "/"]
    for r in to_home:
        findings.append(_risk("homepage_redirect", "low", r, "A deeper page redirects to the home page. Search engines may treat this as a soft 404."))
    if len(to_home) >= 5:
        findings.append(_risk("homepage_mass_redirect", "high", None, f"{len(to_home)} old URLs redirect to the home page (possible mass redirect).", detail={"count": len(to_home)}))

    # 10. paths the user said must never be redirected
    if excluded:
        for r in active:
            if _matches_excluded(r["old_path_key"], excluded):
                findings.append(_risk("excluded_pattern", "high", r, "This old URL matches an excluded pattern but has a redirect rule."))

    return findings


def summarize(findings):
    summary = {"high": 0, "medium": 0, "low": 0, "info": 0}
    by_kind = defaultdict(int)
    for f in findings:
        summary[f["severity"]] += 1
        by_kind[f["kind"]] += 1
    return {"by_severity": summary, "by_kind": dict(by_kind), "total": len(findings), "not_checked": NOT_CHECKED}
