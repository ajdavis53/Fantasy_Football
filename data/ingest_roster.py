"""Parse the league's preseason roster-and-salary workbook into contracts.

The commissioner distributes rosters as a spreadsheet laid out for printing,
not for machines: teams sit in side-by-side blocks two columns apart, each
block headed `"Team Name - Owner"` and terminated by its own totals rows, and
player cells pack name, NFL team, position and injury flag into one string
(`"Prescott, Dak DAL QB (Q)"`) separated by non-breaking spaces.

Blocks are located by scanning for the `Player` header cell rather than by
hardcoding column offsets, so a workbook with a different number of columns
per block still parses.

This is the fallback path. The league runs on MyFantasyLeague, so once a CSV
export is available `data/mfl.py` should supersede this -- but the workbook is
what actually gets circulated before the drop deadline, and it needs to parse.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from data.ingest_etr import slugify_player_id
from data.models import Contract, Player, Position
from data.name_matching import normalize_name

# The workbook's NFL team codes are three-letter; ETR's are the nflverse
# two-and-three-letter mix. Normalizing here means contracts and rankings
# produce identical player_ids and join without fuzzy matching.
TEAM_CODE_ALIASES = {
    "GBP": "GB", "KCC": "KC", "LVR": "LV", "NEP": "NE", "NOS": "NO",
    "SFO": "SF", "TBB": "TB", "JAC": "JAX", "LAR": "LA", "ARZ": "ARI",
}

_POSITION_ALIASES = {"DEF": Position.DEF, "DST": Position.DEF, "D/ST": Position.DEF}

# "Prescott, Dak DAL QB (Q)" -> name, team, position, status
_PLAYER_CELL = re.compile(
    r"^(?P<name>.*?)\s+(?P<team>[A-Z]{2,3})\s+(?P<pos>QB|RB|WR|TE|K|Def|DEF|DST)"
    r"(?:\s*\((?P<status>\w)\))?$"
)
_BLOCK_END = re.compile(r"^(\d+\s+Total Players|Total:|Salary Cap:|Cap Room)", re.IGNORECASE)


class RosterIngestError(ValueError):
    pass


@dataclass(frozen=True)
class TeamImport:
    team: str
    owner: str
    contracts: tuple[Contract, ...]
    bye_weeks: dict[str, int]
    """player_id -> bye week, where the workbook gives one."""
    prior_points: dict[str, float]
    """player_id -> previous season's fantasy points, as the workbook reports them."""

    @property
    def salary(self) -> int:
        return sum(c.salary for c in self.contracts)


def _clean(value: object) -> str:
    """Normalize a cell to text. The workbook is full of non-breaking spaces."""
    if value is None:
        return ""
    return str(value).replace("\xa0", " ").strip()


def parse_player_cell(cell: str) -> tuple[str, str, Position] | None:
    """Split a packed player cell into (name, nfl_team, position), or None.

    Names arrive surname-first (`"Prescott, Dak"`), including for defenses
    (`"Cowboys, Dallas"`), so both flip to natural order the same way.
    """
    match = _PLAYER_CELL.match(cell)
    if not match:
        return None

    raw_name = match.group("name")
    if "," in raw_name:
        last, first = (part.strip() for part in raw_name.split(",", 1))
        name = f"{first} {last}".strip()
    else:
        name = raw_name.strip()

    pos_token = match.group("pos").upper()
    position = _POSITION_ALIASES.get(pos_token) or Position(pos_token)
    team = TEAM_CODE_ALIASES.get(match.group("team"), match.group("team"))
    return name, team, position


def _find_blocks(grid: list[list[str]]) -> list[tuple[int, int]]:
    """Locate each team block as (header_row, column) by finding its `Player` header."""
    blocks = []
    for row_num, row in enumerate(grid):
        for col, cell in enumerate(row):
            if cell == "Player" and row_num > 0 and " - " in grid[row_num - 1][col]:
                blocks.append((row_num - 1, col))
    return blocks


def load_roster_workbook(
    path: str | Path, sheet_name: str | None = None, *, season: int | None = None
) -> list[TeamImport]:
    """Read every team block in the workbook into contracts.

    `season` is accepted for symmetry with the rest of the ingestion layer but
    is not used to date the contracts: the workbook records salaries only, and
    tag/protection state has to come from the league's rules sheet.
    """
    workbook = load_workbook(Path(path), data_only=True, read_only=True)
    worksheet = workbook[sheet_name] if sheet_name else workbook.worksheets[0]
    grid = [[_clean(cell) for cell in row] for row in worksheet.iter_rows(values_only=True)]
    workbook.close()

    blocks = _find_blocks(grid)
    if not blocks:
        raise RosterIngestError(
            f"{path}: found no team blocks -- expected a 'Player' header cell "
            "directly beneath a 'Team Name - Owner' cell"
        )

    imports = []
    for header_row, col in blocks:
        header = grid[header_row][col].strip('"')
        team, _, owner = (part.strip() for part in header.partition(" - "))

        contracts: list[Contract] = []
        bye_weeks: dict[str, int] = {}
        prior_points: dict[str, float] = {}

        for row in grid[header_row + 2 :]:
            cell = row[col] if col < len(row) else ""
            if not cell or _BLOCK_END.match(cell):
                break
            parsed = parse_player_cell(cell)
            if parsed is None:
                continue
            name, nfl_team, position = parsed

            try:
                salary = int(float(row[col + 3]))
            except (IndexError, TypeError, ValueError) as exc:
                raise RosterIngestError(
                    f"{path}: {name!r} on {team!r} has an unreadable salary "
                    f"{row[col + 3] if col + 3 < len(row) else '<missing>'!r}"
                ) from exc

            player_id = slugify_player_id(name, nfl_team, position)
            contracts.append(
                Contract(
                    player_name=name,
                    salary=salary,
                    position=position,
                    nfl_team=nfl_team,
                    team=team,
                )
            )
            bye = row[col + 2] if col + 2 < len(row) else ""
            if bye.isdigit():
                bye_weeks[player_id] = int(bye)
            try:
                prior_points[player_id] = float(row[col + 1])
            except (IndexError, TypeError, ValueError):
                pass  # the workbook writes "-" for players with no prior season

        imports.append(
            TeamImport(
                team=team,
                owner=owner,
                contracts=tuple(contracts),
                bye_weeks=bye_weeks,
                prior_points=prior_points,
            )
        )
    return imports


def contract_player_id(contract: Contract) -> str:
    """The `player_id` a contract joins on, matching `ingest_etr`'s scheme."""
    if contract.position is None:
        raise RosterIngestError(f"contract for {contract.player_name!r} has no position to key on")
    return slugify_player_id(contract.player_name, contract.nfl_team, contract.position)


def link_contracts_to_players(
    contracts: Sequence[Contract], players: Sequence[Player]
) -> tuple[dict[str, str], list[Contract]]:
    """Map each contract to a ranked player_id; return (mapping, unmatched).

    Joins on the synthesized player_id first, which requires the NFL team to
    agree. It often does not: a player who changed teams between the roster
    sheet and the rankings, or who is a free agent in one source and rostered
    in the other, produces two different ids for the same person. So the
    fallback drops the team and joins on normalized name plus position.

    Unmatched contracts are returned rather than dropped. A player missing
    from the rankings is not worth zero -- he is unranked, which usually means
    replacement level, and silently pricing him at zero would make every such
    contract look like a mandatory cut.

    Team defenses get a third pass, keyed on NFL team alone. The two sources
    name them irreconcilably -- the workbook writes "Cowboys, Dallas" and ETR
    writes "DAL DST" -- so no amount of name normalization will join them, but
    the NFL team is unambiguous and there is exactly one defense per team.
    """
    by_id = {p.player_id: p.player_id for p in players}
    by_name_pos: dict[tuple[str, Position], str] = {}
    by_team_defense: dict[str, str] = {}
    for player in players:
        by_name_pos.setdefault((normalize_name(player.name), player.position), player.player_id)
        if player.position is Position.DEF and player.nfl_team:
            by_team_defense.setdefault(player.nfl_team, player.player_id)

    mapping: dict[str, str] = {}
    unmatched: list[Contract] = []
    for contract in contracts:
        key = contract_player_id(contract)
        if key in by_id:
            mapping[key] = key
            continue
        fallback = by_name_pos.get((normalize_name(contract.player_name), contract.position))
        if fallback is None and contract.position is Position.DEF and contract.nfl_team:
            fallback = by_team_defense.get(contract.nfl_team)
        if fallback is not None:
            mapping[key] = fallback
        else:
            unmatched.append(contract)
    return mapping, unmatched
