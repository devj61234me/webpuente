"""
The URL matching engine. Pure Python, no database access, so it is easy to test.

For every old page we look for the best new page using real evidence:
  1. exact_url      - same normalised URL                              -> 100
  2. exact_path     - same path (and query) on a different host        -> 97
  3. fuzzy scoring  - weighted mix of: slug, path words, hierarchy,
                      page title, H1, meta description and (optionally) embedding similarity.
                      Evidence that is missing (e.g. no titles supplied) is left out and the
                      remaining weights are re-balanced; nothing is invented.

To avoid comparing every old page with every new page, an inverted word index first picks
the most promising candidates (at most MATCH_MAX_CANDIDATES per old page).

A high score means "very similar", NOT "certainly the same page". People review every result.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import unquote

from services.urlnorm import slug_of, tokens

STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "at", "by", "from", "is", "are", "your", "our", "we", "us"}
EXACT_PATH_SCORE = 97
TEXT_LIMIT = 300  # SequenceMatcher is slow on long text, so only the start is compared


@dataclass
class Page:
    """One URL prepared for matching."""

    id: int
    full: str
    path_key: str
    title: str = ""
    meta: str = ""
    h1: str = ""
    segments: list = field(init=False)
    slug: str = field(init=False)
    slug_tokens: list = field(init=False)
    path_tokens: list = field(init=False)

    def __post_init__(self):
        path = self.path_key.split("?")[0]
        self.segments = [unquote(s) for s in path.split("/") if s]
        self.slug = slug_of(self.segments).lower()
        self.slug_tokens = tokens(self.slug)
        words = []
        for segment in self.segments:
            lowered = segment.lower()
            for ext in (".html", ".htm", ".php", ".asp", ".aspx", ".jsp", ".shtml"):
                if lowered.endswith(ext):
                    segment = segment[: -len(ext)]
            words.extend(tokens(segment))
        self.path_tokens = words


@dataclass
class MatchResult:
    new_id: int = None
    score: int = 0
    band: str = "unmatched"
    match_type: str = "none"
    reasons: list = field(default_factory=list)
    components: dict = field(default_factory=dict)  # evidence name -> 0..100
    alternatives: list = field(default_factory=list)  # [{"new_id", "score"}]
    evidence: str = "url_only"
    ambiguous: bool = False


# ---------------------------------------------------------------- similarity helpers (each returns 0.0 - 1.0)
def dice(a, b):
    """Overlap of two word lists: 2*|common| / (|a|+|b|)."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return 2 * len(sa & sb) / (len(sa) + len(sb))


def ratio(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:TEXT_LIMIT], b[:TEXT_LIMIT]).ratio()


def slug_similarity(old, new):
    if not old.segments and not new.segments:
        return 1.0  # both are the home page
    if old.slug and old.slug == new.slug:
        return 1.0
    return 0.6 * dice(old.slug_tokens, new.slug_tokens) + 0.4 * ratio(" ".join(old.slug_tokens), " ".join(new.slug_tokens))


def path_similarity(old, new):
    if not old.path_tokens and not new.path_tokens:
        return 1.0
    return 0.7 * dice(old.path_tokens, new.path_tokens) + 0.3 * ratio(" ".join(old.path_tokens), " ".join(new.path_tokens))


def hierarchy_similarity(old, new):
    """Same depth and same parent sections (for example both under /blog/)."""
    da, db = len(old.segments), len(new.segments)
    if da == 0 and db == 0:
        return 1.0
    depth = 1 - abs(da - db) / max(da, db)
    parents_old, parents_new = old.segments[:-1], new.segments[:-1]
    if not parents_old and not parents_new:
        parents = 1.0
    elif not parents_old or not parents_new:
        parents = 0.0
    else:
        parents = dice(tokens(" ".join(parents_old)), tokens(" ".join(parents_new)))
    return 0.4 * depth + 0.6 * parents


def text_tokens(text):
    return [t for t in tokens(text) if t not in STOPWORDS]


def text_similarity(a, b):
    ta, tb = text_tokens(a), text_tokens(b)
    if not ta or not tb:
        return 0.0
    return 0.6 * dice(ta, tb) + 0.4 * ratio(" ".join(ta), " ".join(tb))


def cosine(u, v):
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    if nu == 0 or nv == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (nu * nv)))  # negative similarity counts as "not similar"


# ---------------------------------------------------------------- the engine
class Matcher:
    def __init__(self, new_pages, config, max_candidates=50, new_vectors=None):
        self.new_pages = {p.id: p for p in new_pages}
        self.weights = config["weights"]
        self.t = config["thresholds"]
        self.max_candidates = max_candidates
        self.new_vectors = new_vectors or {}
        # exact lookups
        self.by_full = {}
        self.by_path_key = {}
        for p in new_pages:
            self.by_full.setdefault(p.full, p.id)
            self.by_path_key.setdefault(p.path_key, p.id)
        # inverted index: word -> new page ids (path words + title + h1 words)
        self.index = defaultdict(set)
        for p in new_pages:
            for word in set(p.path_tokens) | set(text_tokens(p.title)) | set(text_tokens(p.h1)):
                self.index[word].add(p.id)
        self.common_limit = max(200, int(0.3 * len(new_pages)))  # words in almost every page carry no signal

    # ---- band helper
    def band_for(self, score):
        if score >= self.t["high"]:
            return "high"
        if score >= self.t["medium"]:
            return "medium"
        if score >= self.t["min_accept"]:
            return "low"
        return "unmatched"

    # ---- candidate selection (cheap filter before the expensive scoring)
    def candidates(self, old):
        words = set(old.path_tokens) | set(text_tokens(old.title)) | set(text_tokens(old.h1))
        heat = defaultdict(float)
        for word in words:
            ids = self.index.get(word)
            if not ids or len(ids) > self.common_limit:
                continue
            weight = 1.0 / (1.0 + math.log(len(ids)))  # rare words count more
            for new_id in ids:
                heat[new_id] += weight
        ranked = sorted(heat, key=lambda i: (-heat[i], i))
        return ranked[: self.max_candidates]

    # ---- scoring one pair
    def components(self, old, new, old_vec=None):
        parts = {
            "slug": slug_similarity(old, new),
            "path": path_similarity(old, new),
            "hierarchy": hierarchy_similarity(old, new),
        }
        if old.title and new.title:
            parts["title"] = text_similarity(old.title, new.title)
        if old.h1 and new.h1:
            parts["h1"] = text_similarity(old.h1, new.h1)
        if old.meta and new.meta:
            parts["meta"] = text_similarity(old.meta, new.meta)
        new_vec = self.new_vectors.get(new.id)
        if old_vec is not None and new_vec is not None:
            parts["semantic"] = cosine(old_vec, new_vec)
        return parts

    def weighted_score(self, parts):
        total = sum(self.weights.get(k, 0) for k in parts)
        if total <= 0:
            return 0.0
        return sum(self.weights.get(k, 0) * v for k, v in parts.items()) / total * 100

    def classify(self, parts):
        """Which kind of evidence drove the score? (used for the 'match type' label)"""
        contribution = {k: self.weights.get(k, 0) * v for k, v in parts.items()}
        url_part = sum(contribution.get(k, 0) for k in ("slug", "path", "hierarchy"))
        meta_part = sum(contribution.get(k, 0) for k in ("title", "h1", "meta"))
        semantic = contribution.get("semantic", 0)
        if semantic and semantic >= max(url_part, meta_part):
            return "semantic"
        if meta_part and meta_part >= url_part:
            return "metadata"
        if contribution["slug"] >= contribution["path"] + contribution["hierarchy"]:
            return "slug"
        return "path_structure"

    @staticmethod
    def evidence_level(parts):
        if "semantic" in parts:
            return "semantic"
        if any(k in parts for k in ("title", "h1", "meta")):
            return "metadata"
        return "url_only"

    def explain(self, old, new, parts, match_type, evidence):
        reasons = []
        pct = lambda value: f"{round(value * 100)}%"  # noqa: E731
        if parts["slug"] >= 0.5:
            reasons.append(f"Similar page name: '{old.slug or '/'}' and '{new.slug or '/'}' ({pct(parts['slug'])}).")
        if parts["hierarchy"] >= 0.6:
            reasons.append(f"Similar URL structure (depth and sections) ({pct(parts['hierarchy'])}).")
        elif parts["path"] >= 0.5:
            reasons.append(f"Shared words in the URL path ({pct(parts['path'])}).")
        if parts.get("title", 0) >= 0.5:
            reasons.append(f"Similar page title ({pct(parts['title'])}).")
        if parts.get("h1", 0) >= 0.5:
            reasons.append(f"Similar main heading (H1) ({pct(parts['h1'])}).")
        if parts.get("meta", 0) >= 0.5:
            reasons.append(f"Similar meta description ({pct(parts['meta'])}).")
        if parts.get("semantic", 0) >= 0.6:
            reasons.append(f"Similar meaning according to the embedding model ({pct(parts['semantic'])}).")
        if not reasons:
            reasons.append("Weak similarity only. Please check this match carefully.")
        if evidence == "url_only":
            reasons.append("Based on the URL only: no page titles or content were supplied, so content was not compared.")
        return reasons

    # ---- the public entry point
    def match(self, old, old_vec=None):
        # 1. exact normalised URL
        new_id = self.by_full.get(old.full)
        if new_id is not None:
            return MatchResult(new_id, 100, "high", "exact_url", ["Exact URL match after normalisation."], {}, [], "url_only", False)
        # 2. same path on another host (typical for a domain change)
        new_id = self.by_path_key.get(old.path_key)
        if new_id is not None:
            return MatchResult(
                new_id, EXACT_PATH_SCORE, "high", "exact_path",
                ["Same path and query on the new site (the host name differs)."], {}, [], "url_only", False,
            )
        # 3. fuzzy scoring on the shortlisted candidates
        scored = []
        for cid in self.candidates(old):
            new = self.new_pages[cid]
            parts = self.components(old, new, old_vec)
            score = min(self.weighted_score(parts), self.t["fuzzy_cap"])
            scored.append((score, cid, parts))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if not scored or round(scored[0][0]) < self.t["min_accept"]:
            return MatchResult(reasons=["No acceptable candidate was found on the new site."])
        score, cid, parts = scored[0]
        new = self.new_pages[cid]
        match_type = self.classify(parts)
        evidence = self.evidence_level(parts)
        alternatives = [
            {"new_id": other_id, "score": round(other_score)}
            for other_score, other_id, _ in scored[1:4]
            if round(other_score) >= self.t["min_accept"]
        ]
        ambiguous = bool(alternatives) and (round(score) - alternatives[0]["score"]) < self.t["ambiguity_gap"]
        rounded = round(score)
        return MatchResult(
            new_id=cid, score=rounded, band=self.band_for(rounded), match_type=match_type,
            reasons=self.explain(old, new, parts, match_type, evidence),
            components={k: round(v * 100) for k, v in parts.items()},
            alternatives=alternatives, evidence=evidence, ambiguous=ambiguous,
        )
