"""Fuzzy player-name matching, shared by keeper resolution and live pick entry.

During a live draft a name is typed under a pick clock, often partially and
sometimes misspelled ("jefferson", "amon ra", "st brown"), so matching has to
tolerate abbreviation and punctuation while never silently picking the wrong
player. `match_players` ranks candidates and leaves the choice to the caller;
`resolve_one` commits only when a single candidate is clearly ahead.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from data.models import Player

DEFAULT_THRESHOLD = 60.0
# How far clear the top candidate must be for `resolve_one` to auto-commit.
UNAMBIGUOUS_MARGIN = 15.0


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation and suffixes so "A.J. Brown Jr." ~ "aj brown".

    Punctuation is not all handled the same way, because it does not all mean
    the same thing. Periods and apostrophes sit *inside* a name part -- "A.J.",
    "Ja'Marr" -- and are deleted, so those become "aj" and "jamarr". Hyphens
    *join* two parts -- "Amon-Ra", "Smith-Njigba" -- and become a space, so the
    parts stay separately matchable.

    That distinction is what makes token matching work on the names people
    actually type at a draft table. Deleting hyphens too would collapse
    "Amon-Ra St Brown" to "amonra st brown", which shares no token at all with
    "amon ra" and scores 54 -- below any sane threshold, so the match this
    module exists to make silently fails on exactly the awkward names a human
    reaches for help with.
    """
    lowered = name.lower()
    joined = re.sub(r"[-‐-―/]+", " ", lowered)
    cleaned = re.sub(r"[^a-z0-9\s]", "", joined)
    cleaned = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def match_players(
    query: str,
    players: list[Player],
    limit: int = 5,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[tuple[Player, float]]:
    """Best `limit` players for `query`, ranked by score descending."""
    if not query.strip() or not players:
        return []

    choices = {i: normalize_name(p.name) for i, p in enumerate(players)}
    # token_set_ratio, not WRatio: shared surnames are everywhere in the player
    # pool, and WRatio's partial-substring bonus scores "amon ra st brown"
    # against "AJ Brown" at 86 -- close enough to the true match to look
    # ambiguous. Comparing token sets keeps the real match well clear.
    results = process.extract(
        normalize_name(query),
        choices,
        scorer=fuzz.token_set_ratio,
        limit=limit,
        score_cutoff=threshold,
    )
    return [(players[index], score) for _, score, index in results]


def resolve_one(
    query: str, players: list[Player], threshold: float = DEFAULT_THRESHOLD
) -> Player | None:
    """The single clearly-best match for `query`, or None if it is ambiguous.

    Returning None on a close call is deliberate: recording the wrong player
    mid-draft is far more costly than asking which one was meant.
    """
    # An exact name, typed in full, is not a close call -- it is the answer.
    # Without this the margin rule rejects it whenever a similar name exists:
    # "bijan robinson" scores 100, but "Brian Robinson" scores in the low 90s
    # on the shared surname and near-identical forename, leaving a margin under
    # 15. Refusing to record a perfectly typed name is the wrong failure, and
    # it is worst for exactly the players whose names invite a typo.
    normalized = normalize_name(query)
    exact = [p for p in players if normalize_name(p.name) == normalized]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None  # two players genuinely share a name; ask

    matches = match_players(query, players, limit=2, threshold=threshold)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0][0]

    (best, best_score), (_, runner_up_score) = matches
    return best if best_score - runner_up_score >= UNAMBIGUOUS_MARGIN else None


class KeeperResolutionError(ValueError):
    pass


def resolve_keepers(league_keepers, players: list[Player]) -> dict[str, str]:
    """Map each keeper's configured name to a player_id.

    Raises rather than guessing: a keeper silently unmatched would leave an
    already-rostered player sitting on the board as though available.
    """
    resolved: dict[str, str] = {}
    for keeper in league_keepers:
        player = resolve_one(keeper.player_name, players)
        if player is None:
            candidates = [p.name for p, _ in match_players(keeper.player_name, players, limit=3)]
            hint = f"; did you mean {candidates}?" if candidates else ""
            raise KeeperResolutionError(
                f"keeper {keeper.player_name!r} (team {keeper.team_slot}) "
                f"did not match exactly one player in the rankings{hint}"
            )
        resolved[keeper.player_name] = player.player_id
    return resolved
