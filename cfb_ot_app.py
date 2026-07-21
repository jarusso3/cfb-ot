import pickle
import os
import streamlit as st
import altair as alt
import pandas as pd
import numpy as np

# ── constants ──────────────────────────────────────────────────────────────────

# Generic placeholder "teams" — the app defaults to these so it opens neutral
# rather than on real matchups. Listed first so they sit at the top of the dropdown.
GENERIC_TEAMS = ["AWAY", "HOME"]

FBS_TEAMS = GENERIC_TEAMS + [
    "Air Force", "Akron", "Alabama", "Appalachian State", "Arizona", "Arizona State",
    "Arkansas", "Arkansas State", "Army", "Auburn", "Ball State", "Baylor", "Boise State",
    "Boston College", "Bowling Green", "Buffalo", "BYU", "California", "Central Michigan",
    "Charlotte", "Cincinnati", "Clemson", "Coastal Carolina", "Colorado", "Colorado State",
    "Connecticut", "Duke", "East Carolina", "Eastern Michigan", "FIU", "Florida",
    "Florida Atlantic", "Florida State", "Georgia", "Georgia Southern", "Georgia State",
    "Georgia Tech", "Hawaii", "Houston", "Illinois", "Indiana", "Iowa", "Iowa State",
    "Jacksonville State", "James Madison", "Kansas", "Kansas State", "Kennesaw State",
    "Kent State", "Kentucky", "Liberty", "Louisiana", "Louisiana Monroe", "Louisiana Tech",
    "Louisville", "LSU", "Marshall", "Maryland", "Memphis", "Miami (FL)", "Miami (OH)",
    "Michigan", "Michigan State", "Middle Tennessee", "Minnesota", "Mississippi State",
    "Missouri", "Navy", "Nebraska", "Nevada", "New Mexico", "New Mexico State",
    "North Carolina", "North Carolina State", "Northern Illinois", "Northwestern",
    "Notre Dame", "Ohio", "Ohio State", "Oklahoma", "Oklahoma State", "Old Dominion",
    "Ole Miss", "Oregon", "Oregon State", "Penn State", "Pittsburgh", "Purdue", "Rice",
    "Rutgers", "Sam Houston", "San Diego State", "San Jose State", "SMU", "South Alabama",
    "South Carolina", "South Florida", "Southern Miss", "Stanford", "Syracuse", "TCU",
    "Temple", "Tennessee", "Texas", "Texas A&M", "Texas State", "Texas Tech", "Toledo",
    "Troy", "Tulane", "Tulsa", "UAB", "UCF", "UCLA", "UNLV", "USC", "Utah", "Utah State",
    "Vanderbilt", "Virginia", "Virginia Tech", "Wake Forest", "Washington",
    "Washington State", "West Virginia", "Western Kentucky", "Western Michigan",
    "Wisconsin", "Wyoming",
]

OUTCOME_LABELS = {
    "td_pat":   "TD + PAT (7 pts)",
    "td_2pt":   "TD + 2pt (8 pts)",
    "td_6":     "TD, miss PAT (6 pts)",
    "fg":       "Field Goal (3 pts)",
    "turnover": "Turnover / Miss FG (0 pts)",
    "def_td":   "Defensive TD (6 pts, defense scores)",
}

# League-average 2-pt conversion success rate. Single source of truth: drives both
# the mandatory-2pt TD split in OT2+ (td_2pt made vs td_6 failed) and the OT3+
# shootout success baseline, so the two rule regimes stay consistent.
TWO_PT_BASE_RATE = 0.45

# Second-possessor edge. The team that possesses SECOND in a given OT has an
# information advantage (they know exactly what they need). This single knob tilts
# the second possessor's scoring distribution up so an even matchup lands the second
# team at ~52.5%. Set to 0.0 to disable — e.g. once the aggressiveness ratings
# absorb this effect behaviorally. Calibrated empirically: 0.17 puts an even
# matchup's second possessor at ~52.4% (OT1) / ~52.2% (OT2) to win that period.
# Note: because possession ALTERNATES OT1->OT2, this per-period edge largely
# cancels over a full game, so the game-level moneyline stays near 50/50 — the
# edge shows up in the per-period ("OT N result") pricing, which is the intent.
SECOND_POSSESSOR_EDGE = 0.17

# Points scored by the OFFENSE on a given outcome
OFFENSE_PTS = {"td_pat": 7, "td_2pt": 8, "td_6": 6, "fg": 3, "turnover": 0, "def_td": 0}
# Points scored by the DEFENSE (i.e. the non-possessing team) on a given outcome
DEFENSE_PTS = {"td_pat": 0, "td_2pt": 0, "td_6": 0, "fg": 0, "turnover": 0, "def_td": 6}

OUTCOME_COLORS = {
    "td_2pt":   "#2E7D32",  # 8-pt TD — dark green
    "td_pat":   "#43A047",  # 7-pt TD — green
    "td_6":     "#5CB860",  # 6-pt TD — light green
    "fg":       "#F9A825",  # field goal — yellow
    "turnover": "#BDBDBD",  # turnover / miss FG — light gray
    "def_td":   "#616161",  # defensive TD — dark gray
}

# Order the drive pie arcs should follow (counter-clockwise): the three TDs by
# points (8 → 7 → 6), then FG, then the two zero-offense outcomes.
PIE_ORDER = ["td_2pt", "td_pat", "td_6", "fg", "turnover", "def_td"]

PERIOD_COLORS = {
    "away_wins": "#1565C0",
    "home_wins": "#C62828",
    "advance":   "#757575",
}

TEAM_ABBR = {
    "AWAY":               "AWAY", "HOME":               "HOME",
    "Air Force":          "AFA",  "Akron":              "AKR",  "Alabama":            "ALA",
    "Appalachian State":  "APP",  "Arizona":            "ARIZ", "Arizona State":      "ASU",
    "Arkansas":           "ARK",  "Arkansas State":     "ARST", "Army":               "ARMY",
    "Auburn":             "AUB",  "Ball State":         "BALL", "Baylor":             "BAY",
    "Boise State":        "BSU",  "Boston College":     "BC",   "Bowling Green":      "BGSU",
    "Buffalo":            "BUFF", "BYU":                "BYU",  "California":         "CAL",
    "Central Michigan":   "CMU",  "Charlotte":          "CLT",  "Cincinnati":         "CIN",
    "Clemson":            "CLEM", "Coastal Carolina":   "CCU",  "Colorado":           "COL",
    "Colorado State":     "CSU",  "Connecticut":        "UCONN","Duke":               "DUKE",
    "East Carolina":      "ECU",  "Eastern Michigan":   "EMU",  "FIU":                "FIU",
    "Florida":            "FLA",  "Florida Atlantic":   "FAU",  "Florida State":      "FSU",
    "Georgia":            "UGA",  "Georgia Southern":   "GASO", "Georgia State":      "GAST",
    "Georgia Tech":       "GT",   "Hawaii":             "HAW",  "Houston":            "HOU",
    "Illinois":           "ILL",  "Indiana":            "IND",  "Iowa":               "IOWA",
    "Iowa State":         "ISU",  "Jacksonville State": "JVST", "James Madison":      "JMU",
    "Kansas":             "KU",   "Kansas State":       "KSU",  "Kennesaw State":     "KENN",
    "Kent State":         "KENT", "Kentucky":           "UK",   "Liberty":            "LIB",
    "Louisiana":          "ULL",  "Louisiana Monroe":   "ULM",  "Louisiana Tech":     "LT",
    "Louisville":         "LOU",  "LSU":                "LSU",  "Marshall":           "MRSH",
    "Maryland":           "MD",   "Memphis":            "MEM",  "Miami (FL)":         "MIA",
    "Miami (OH)":         "MIOH", "Michigan":           "MICH", "Michigan State":     "MSU",
    "Middle Tennessee":   "MTSU", "Minnesota":          "MINN", "Mississippi State":  "MSST",
    "Missouri":           "MIZ",  "Navy":               "NAVY", "Nebraska":           "NEB",
    "Nevada":             "NEV",  "New Mexico":         "UNM",  "New Mexico State":   "NMSU",
    "North Carolina":     "UNC",  "North Carolina State":"NCST","Northern Illinois":  "NIU",
    "Northwestern":       "NW",   "Notre Dame":         "ND",   "Ohio":               "OHIO",
    "Ohio State":         "OSU",  "Oklahoma":           "OU",   "Oklahoma State":     "OKST",
    "Old Dominion":       "ODU",  "Ole Miss":           "MISS", "Oregon":             "ORE",
    "Oregon State":       "ORST", "Penn State":         "PSU",  "Pittsburgh":         "PITT",
    "Purdue":             "PUR",  "Rice":               "RICE", "Rutgers":            "RUT",
    "Sam Houston":        "SHSU", "San Diego State":    "SDSU", "San Jose State":     "SJSU",
    "SMU":                "SMU",  "South Alabama":      "USA",  "South Carolina":     "SC",
    "South Florida":      "USF",  "Southern Miss":      "USM",  "Stanford":           "STAN",
    "Syracuse":           "SYR",  "TCU":                "TCU",  "Temple":             "TEM",
    "Tennessee":          "TENN", "Texas":              "TEX",  "Texas A&M":          "TAMU",
    "Texas State":        "TXST", "Texas Tech":         "TTU",  "Toledo":             "TOL",
    "Troy":               "TROY", "Tulane":             "TUL",  "Tulsa":              "TLSA",
    "UAB":                "UAB",  "UCF":                "UCF",  "UCLA":               "UCLA",
    "UNLV":               "UNLV", "USC":                "USC",  "Utah":               "UTAH",
    "Utah State":         "USU",  "Vanderbilt":         "VAN",  "Virginia":           "UVA",
    "Virginia Tech":      "VT",   "Wake Forest":        "WAKE", "Washington":         "WASH",
    "Washington State":   "WSU",  "West Virginia":      "WVU",  "Western Kentucky":   "WKU",
    "Western Michigan":   "WMU",  "Wisconsin":          "WIS",  "Wyoming":            "WYO",
}


def team_abbr(name: str) -> str:
    return TEAM_ABBR.get(name, name[:4].upper())


TEAM_COLORS = {
    "AWAY":               "#E8710A",  # orange
    "HOME":               "#2E7D32",  # green
    "Air Force":          "#003087",
    "Akron":              "#041E42",
    "Alabama":            "#9E1B32",
    "Appalachian State":  "#FFB300",
    "Arizona":            "#003366",
    "Arizona State":      "#8C1D40",
    "Arkansas":           "#9D2235",
    "Arkansas State":     "#CC0000",
    "Army":               "#FFD700",
    "Auburn":             "#0C2340",
    "Ball State":         "#BA0C2F",
    "Baylor":             "#003015",
    "Boise State":        "#0033A0",
    "Boston College":     "#8B0000",
    "Bowling Green":      "#4B2200",
    "Buffalo":            "#005BBB",
    "BYU":                "#002E5D",
    "California":         "#003262",
    "Central Michigan":   "#6A0032",
    "Charlotte":          "#046A38",
    "Cincinnati":         "#E00122",
    "Clemson":            "#F56600",
    "Coastal Carolina":   "#006F71",
    "Colorado":           "#CFB87C",
    "Colorado State":     "#1E4D2B",
    "Connecticut":        "#000E2F",
    "Duke":               "#003087",
    "East Carolina":      "#592A8A",
    "Eastern Michigan":   "#007A53",
    "FIU":                "#081E3F",
    "Florida":            "#0021A5",
    "Florida Atlantic":   "#003366",
    "Florida State":      "#782F40",
    "Georgia":            "#BA0C2F",
    "Georgia Southern":   "#011E41",
    "Georgia State":      "#0039A6",
    "Georgia Tech":       "#B3A369",
    "Hawaii":             "#024731",
    "Houston":            "#C8102E",
    "Illinois":           "#E84A27",
    "Indiana":            "#990000",
    "Iowa":               "#FFCD00",
    "Iowa State":         "#C8102E",
    "Jacksonville State": "#CC0000",
    "James Madison":      "#450084",
    "Kansas":             "#0051A5",
    "Kansas State":       "#512888",
    "Kennesaw State":     "#FDBB30",
    "Kent State":         "#002664",
    "Kentucky":           "#0033A0",
    "Liberty":            "#002868",
    "Louisiana":          "#CE181E",
    "Louisiana Monroe":   "#800000",
    "Louisiana Tech":     "#002F8B",
    "Louisville":         "#AD0000",
    "LSU":                "#461D7C",
    "Marshall":           "#009B77",
    "Maryland":           "#E03A3E",
    "Memphis":            "#003087",
    "Miami (FL)":         "#005030",
    "Miami (OH)":         "#B61E2E",
    "Michigan":           "#00274C",
    "Michigan State":     "#18453B",
    "Middle Tennessee":   "#0066CC",
    "Minnesota":          "#7A0019",
    "Mississippi State":  "#660000",
    "Missouri":           "#F1B82D",
    "Navy":               "#00205B",
    "Nebraska":           "#E41C38",
    "Nevada":             "#003366",
    "New Mexico":         "#BA0C2F",
    "New Mexico State":   "#861F41",
    "North Carolina":     "#4B9CD3",
    "North Carolina State":"#CC0000",
    "Northern Illinois":  "#BA0C2F",
    "Northwestern":       "#4E2A84",
    "Notre Dame":         "#0C2340",
    "Ohio":               "#00694E",
    "Ohio State":         "#BB0000",
    "Oklahoma":           "#841617",
    "Oklahoma State":     "#FF6600",
    "Old Dominion":       "#003057",
    "Ole Miss":           "#14213D",
    "Oregon":             "#154733",
    "Oregon State":       "#DC4405",
    "Penn State":         "#041E42",
    "Pittsburgh":         "#003594",
    "Purdue":             "#CEB888",
    "Rice":               "#00205B",
    "Rutgers":            "#CC0033",
    "Sam Houston":        "#F47920",
    "San Diego State":    "#A6192E",
    "San Jose State":     "#0055A2",
    "SMU":                "#0033A0",
    "South Alabama":      "#00205B",
    "South Carolina":     "#73000A",
    "South Florida":      "#006747",
    "Southern Miss":      "#FFB300",
    "Stanford":           "#8C1515",
    "Syracuse":           "#D44500",
    "TCU":                "#4D1979",
    "Temple":             "#9D2235",
    "Tennessee":          "#FF8200",
    "Texas":              "#BF5700",
    "Texas A&M":          "#500000",
    "Texas State":        "#501214",
    "Texas Tech":         "#CC0000",
    "Toledo":             "#15397F",
    "Troy":               "#8B0000",
    "Tulane":             "#006747",
    "Tulsa":              "#002D62",
    "UAB":                "#1E6B52",
    "UCF":                "#BA9B37",
    "UCLA":               "#2D68C4",
    "UNLV":               "#B10202",
    "USC":                "#990000",
    "Utah":               "#CC0000",
    "Utah State":         "#0F2439",
    "Vanderbilt":         "#866D4B",
    "Virginia":           "#232D4B",
    "Virginia Tech":      "#630031",
    "Wake Forest":        "#9E7E38",
    "Washington":         "#33006F",
    "Washington State":   "#981E32",
    "West Virginia":      "#002855",
    "Western Kentucky":   "#B01E24",
    "Western Michigan":   "#6C4023",
    "Wisconsin":          "#C5050C",
    "Wyoming":            "#492F24",
}
NEUTRAL_COLOR = "#424242"


def team_color(name: str) -> str:
    return TEAM_COLORS.get(name, NEUTRAL_COLOR)


def text_color(bg_hex: str) -> str:
    h = bg_hex.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.55 else "#ffffff"


# ── possession order ───────────────────────────────────────────────────────────

def first_team_for_period(period: int, ot1_first: str) -> str:
    """
    NCAA alternation rule: the team that went SECOND in period N goes FIRST in period N+1.
    Net result: strict alternation — OT1 first team alternates each period.
    """
    if period % 2 == 1:
        return ot1_first
    return "Home" if ot1_first == "Away" else "Away"


# ── model loading ──────────────────────────────────────────────────────────────

@st.cache_resource
def load_model():
    model_path = os.path.join(os.path.dirname(__file__), "cfb_ot_model.pkl")
    with open(model_path, "rb") as f:
        return pickle.load(f)


# ── probability engine ─────────────────────────────────────────────────────────

def base_drive_probs(strength_delta: float, off_def_tendency: float,
                     down: int = 1, distance: int = 10, yards_to_goal: int = 25,
                     aggressiveness: float = 0.0, ot_period: int = 1) -> dict:
    """
    Returns a drive outcome probability distribution using the trained ML model
    as the base, then applies strength and tendency adjustments on top.

    strength_delta  > 0 → this team's offense is stronger
    off_def_tendency > 0 → high-scoring game; < 0 → defensive game
    down/distance/yards_to_goal → field situation (defaults to OT start)
    aggressiveness   0 → normal play (no effect); 1 → fairly extreme. Suppresses
                     FG (going for it instead of kicking), pushing that mass into
                     TD and turnover, and shifts the TD point-split from PAT (7)
                     toward 2pt (8) and missed-PAT (6). Meant for the ACTIVE drive
                     only — leave at 0 for base/future distributions.
    ot_period        the OT period this drive belongs to. NCAA mandates a 2-pt try
                     after any TD starting in OT2, so for ot_period >= 2 the 7-pt
                     PAT outcome is impossible: its mass collapses onto td_2pt
                     (made, 8) and td_6 (failed, 6) at TWO_PT_BASE_RATE.
    """
    payload = load_model()
    model   = payload["model"]
    classes = payload["classes"]   # e.g. ["fg", "td_pat", "turnover"]
    def_td_base = payload.get("def_td_base_prob", 0.005)

    # Query the model for the 3 trained outcomes
    raw_probs = model.predict_proba([[down, distance, yards_to_goal]])[0]
    p = {cls: prob for cls, prob in zip(classes, raw_probs)}

    # Scale down by def_td_base to leave room, then add def_td back
    scale = 1.0 - def_td_base
    p = {k: v * scale for k, v in p.items()}
    p["def_td"] = def_td_base

    # td_2pt and td_6 aren't modeled — split a small portion from td_pat
    td_total = p.get("td_pat", 0)
    p["td_pat"] = td_total * 0.87
    p["td_2pt"] = td_total * 0.08
    p["td_6"]   = td_total * 0.05

    # Apply strength adjustment (positive = this team favored)
    td_keys = ["td_pat", "td_2pt", "td_6"]
    if strength_delta > 0:
        for k in td_keys:
            p[k] *= (1 + strength_delta * 0.5)
        p["turnover"] /= (1 + strength_delta * 0.3)
        p["fg"]       /= (1 + strength_delta * 0.3)
    elif strength_delta < 0:
        d = abs(strength_delta)
        for k in td_keys:
            p[k] /= (1 + d * 0.5)
        p["turnover"] *= (1 + d * 0.3)
        p["fg"]       *= (1 + d * 0.3)

    # Apply off/def tendency (affects both teams equally — done at call site)
    if off_def_tendency > 0:
        for k in td_keys:
            p[k] *= (1 + off_def_tendency * 0.4)
        p["turnover"] *= (1 - off_def_tendency * 0.3)
    elif off_def_tendency < 0:
        for k in td_keys:
            p[k] *= (1 + off_def_tendency * 0.3)
        p["fg"]       *= (1 - off_def_tendency * 0.2)
        p["turnover"] *= (1 - off_def_tendency * 0.4)

    # Apply aggressiveness (0 = normal, 1 = fairly extreme). Active-drive only.
    a = max(0.0, min(1.0, aggressiveness))
    if a > 0:
        # 1) Suppress FGs — the team goes for it instead of kicking. At a=1 we strip
        #    ~85% of FG mass and reallocate it: more to TD (they convert) than to
        #    turnover (they fail on downs). Split the freed mass 60/40 TD/turnover.
        fg_removed = p["fg"] * (0.85 * a)
        p["fg"] -= fg_removed
        td_mass_before = sum(p[k] for k in td_keys)
        if td_mass_before > 0:
            # distribute the TD share proportionally across the existing td split
            td_gain = fg_removed * 0.60
            for k in td_keys:
                p[k] += td_gain * (p[k] / td_mass_before)
        else:
            p["td_pat"] += fg_removed * 0.60
        p["turnover"] += fg_removed * 0.40

        # 2) Shift the TD point-split away from PAT (7) toward 2pt (8) and miss (6).
        #    Reweight the TD mass onto new fractions that ramp with a. Normal split
        #    is 87/8/5 (pat/2pt/6); at a=1 it moves toward ~55/33/12.
        td_mass = sum(p[k] for k in td_keys)
        if td_mass > 0:
            frac_pat = 0.87 - 0.32 * a
            frac_2pt = 0.08 + 0.25 * a
            frac_6   = 0.05 + 0.07 * a
            s = frac_pat + frac_2pt + frac_6
            p["td_pat"] = td_mass * frac_pat / s
            p["td_2pt"] = td_mass * frac_2pt / s
            p["td_6"]   = td_mass * frac_6   / s

    # Mandatory 2-pt try in OT2+: the 7-pt PAT is not allowed. Collapse all TD mass
    # onto the two 2-pt outcomes — made (td_2pt, 8) vs failed (td_6, 6) — at the
    # league 2-pt conversion rate. Runs last so it's the final word on the TD split.
    if ot_period >= 2:
        td_mass = p["td_pat"] + p["td_2pt"] + p["td_6"]
        p["td_pat"] = 0.0
        p["td_2pt"] = td_mass * TWO_PT_BASE_RATE
        p["td_6"]   = td_mass * (1 - TWO_PT_BASE_RATE)

    total = sum(p.values())
    return {k: v / total for k, v in p.items()}


def _apply_second_edge(probs: dict, edge: float | None = None) -> dict:
    """
    Tilt a drive distribution toward scoring to represent the second possessor's
    advantage. Scales TD outcomes up by (1+edge) and FG up slightly, pulling the
    freed mass out of turnover, then renormalizes. edge=0 returns probs unchanged.
    Resolves SECOND_POSSESSOR_EDGE at call time (not as a frozen default).
    """
    if edge is None:
        edge = SECOND_POSSESSOR_EDGE
    if edge <= 0:
        return probs
    q = dict(probs)
    for k in ("td_pat", "td_2pt", "td_6"):
        q[k] *= (1 + edge)
    q["fg"] *= (1 + edge * 0.5)
    total = sum(q.values())
    return {k: v / total for k, v in q.items()}


def period_outcome_probs_ordered(first_probs: dict, second_probs: dict,
                                  first_score: int, second_score: int,
                                  second_edge: bool = True) -> dict:
    """
    Enumerate all (first_outcome × second_outcome) combinations for one OT period.

    Possession logic:
      1. First team possesses. Their offense may score; the defending second team's
         defense may score a DefTD (6 pts to second team).
      2. Second team then possesses. Their offense may score; the defending first
         team's defense may score a DefTD (6 pts to first team).
      3. Compare totals → first wins / second wins / advance.

    Note: both possessions always happen (no walk-off mid-possession in this model).
    Returns P(first wins), P(second wins), P(advance to next OT).

    second_edge: when True (default), the second possessor's distribution is tilted
    toward scoring via SECOND_POSSESSOR_EDGE to reflect their information advantage.
    Pass False when the second team's distribution is already known/collapsed (mid-
    period), so we don't double-apply the edge to a certain outcome.
    """
    if second_edge:
        second_probs = _apply_second_edge(second_probs)

    p_first = p_second = p_advance = 0.0

    for fk, fp in first_probs.items():
        # After first team's possession
        f_score_mid = first_score  + OFFENSE_PTS[fk]   # first team offense
        s_score_mid = second_score + DEFENSE_PTS[fk]   # second team defense (DefTD)

        for sk, sp in second_probs.items():
            # After second team's possession
            final_first  = f_score_mid + DEFENSE_PTS[sk]   # first team defense (DefTD)
            final_second = s_score_mid + OFFENSE_PTS[sk]   # second team offense

            joint = fp * sp
            if final_first > final_second:
                p_first   += joint
            elif final_second > final_first:
                p_second  += joint
            else:
                p_advance += joint

    total = p_first + p_second + p_advance
    if total > 0:
        p_first   /= total
        p_second  /= total
        p_advance /= total

    return {"first_wins": p_first, "second_wins": p_second, "advance": p_advance}


def _p_away_wins_from_period_start(period: int, ot1_first: str,
                                    away_probs: dict, home_probs: dict,
                                    p_away_shootout: float) -> float:
    """
    Recursive helper. Returns P(away wins game) assuming we're at the START of
    `period` with scores tied. OT3+ uses the pre-computed shootout probability.
    """
    if period >= 3:
        return p_away_shootout

    first_this = first_team_for_period(period, ot1_first)
    fp = away_probs if first_this == "Away" else home_probs
    sp = home_probs if first_this == "Away" else away_probs

    # Scores always tied at start of each OT period
    outcome = period_outcome_probs_ordered(fp, sp, 0, 0)
    p_future = _p_away_wins_from_period_start(period + 1, ot1_first,
                                               away_probs, home_probs, p_away_shootout)

    if first_this == "Away":
        return outcome["first_wins"] + outcome["advance"] * p_future
    else:
        return outcome["second_wins"] + outcome["advance"] * p_future


def game_win_probs(away_probs: dict, home_probs: dict,
                   away_succ: float, home_succ: float,
                   current_period: int, ot1_first: str,
                   first_possession_logged: bool,
                   period_first_pts: int, period_second_pts: int,
                   future_away_probs: dict | None = None,
                   future_home_probs: dict | None = None,
                   first_shootout_result: str | None = None) -> dict:
    """
    Compute P(away wins game outright) from the current live state.

    IMPORTANT: OT period outcomes are decided on within-period scores only.
    Teams always enter each period tied; we compare what each scores IN that period.

    away_probs / home_probs describe the CURRENT period (may be live/collapsed —
    e.g. the first possessor's outcome is known with certainty). future_away_probs /
    future_home_probs describe FUTURE periods and must be the neutral base
    distributions — never the live/collapsed ones, or every hypothetical future
    period would inherit the current period's known result. Defaults to the current
    dists for backward compatibility.

    Three cases:
      A. Shootout period (OT3+): closed-form.
      B. Start of standard OT period: enumerate all first×second outcome pairs,
         compare within-period totals (both start at 0).
      C. Mid-period: first team has possessed. We know their within-period total
         (period_first_pts for offense, period_second_pts for the defensive score
         that went to the second team). Enumerate only second team outcomes and
         compare resulting within-period totals.
    """
    if future_away_probs is None:
        future_away_probs = away_probs
    if future_home_probs is None:
        future_home_probs = home_probs

    # Unconditioned P(away wins | shootout goes to completion) — used as the value
    # of any FUTURE shootout period in the recursion below. Never condition this on
    # the current period's known result.
    s_away  = away_succ * (1 - home_succ)
    s_home  = (1 - away_succ) * home_succ
    s_total = s_away + s_home
    p_away_shootout = s_away / s_total if s_total > 0 else 0.5

    if current_period >= 3:
        first_this = first_team_for_period(current_period, ot1_first)
        if first_possession_logged and first_shootout_result is not None:
            # Mid-period: condition on the first possessor's known attempt. An
            # "advance" (both convert / both miss) rolls into a fresh shootout,
            # whose away-win value is the unconditioned p_away_shootout.
            sp = shootout_period_probs(away_succ, home_succ, first_this, first_shootout_result)
            p_away = sp["away_wins"] + sp["advance"] * p_away_shootout
        else:
            p_away = p_away_shootout
        return {"away_wins": p_away, "home_wins": 1 - p_away}

    p_future_away = _p_away_wins_from_period_start(
        current_period + 1, ot1_first, future_away_probs, future_home_probs, p_away_shootout
    )

    first_this = first_team_for_period(current_period, ot1_first)

    if not first_possession_logged:
        # ── Case B: start of period, within-period scores both 0 ──
        fp = away_probs if first_this == "Away" else home_probs
        sp = home_probs if first_this == "Away" else away_probs
        outcome = period_outcome_probs_ordered(fp, sp, 0, 0)
        if first_this == "Away":
            p_away = outcome["first_wins"] + outcome["advance"] * p_future_away
        else:
            p_away = outcome["second_wins"] + outcome["advance"] * p_future_away

    else:
        # ── Case C: mid-period, first possession done ──
        # Within-period: first possessor has period_first_pts,
        # second team already has period_second_pts (from a defensive TD if any).
        second_this  = "Home" if first_this == "Away" else "Away"
        second_probs = home_probs if second_this == "Home" else away_probs
        # Same second-possessor edge as Case B (period_outcome_probs_ordered applies
        # it internally there; here we enumerate the second team directly, so apply
        # it explicitly for consistency).
        second_probs = _apply_second_edge(second_probs)

        p_away = 0.0
        for sk, sp_prob in second_probs.items():
            # After second team possesses, compute within-period final totals
            # first_pts_final  = period_first_pts  + any def TD second team's defense scores
            # second_pts_final = period_second_pts + second team's offense
            first_pts_final  = period_first_pts  + DEFENSE_PTS[sk]
            second_pts_final = period_second_pts + OFFENSE_PTS[sk]

            # Map back to away/home
            if first_this == "Away":
                away_period = first_pts_final
                home_period = second_pts_final
            else:
                away_period = second_pts_final
                home_period = first_pts_final

            if away_period > home_period:
                p_away += sp_prob
            elif home_period > away_period:
                pass
            else:
                p_away += sp_prob * p_future_away

    p_home = 1.0 - p_away
    return {"away_wins": p_away, "home_wins": p_home}


def shootout_period_probs(away_succ: float, home_succ: float,
                          first_this: str | None = None,
                          first_result: str | None = None) -> dict:
    """
    Closed-form P(away wins / home wins / advance) for one 2-pt shootout period.

    Start of period (first_this / first_result not supplied): enumerate both
    attempts. Mid-period (first possessor's attempt already logged, first_result
    is "Success"/"Failure"): condition on that known result so the price actually
    moves when the first team goes.
    """
    if first_this is None or first_result is None:
        p_away = away_succ * (1 - home_succ)
        p_home = (1 - away_succ) * home_succ
        p_tie  = away_succ * home_succ + (1 - away_succ) * (1 - home_succ)
        total  = p_away + p_home + p_tie
        return {"away_wins": p_away/total, "home_wins": p_home/total, "advance": p_tie/total}

    # ── Mid-period: the first possessor's attempt is known ──
    second_this = "Home" if first_this == "Away" else "Away"
    second_succ = away_succ if second_this == "Away" else home_succ
    first_scored = (first_result == "Success")

    if first_scored:
        # Second team must convert to tie (→ advance); a miss hands the first team the win.
        p_first_wins  = 1 - second_succ
        p_second_wins = 0.0
        p_advance     = second_succ
    else:
        # First team missed: second converting wins outright; a miss advances (0-0).
        p_first_wins  = 0.0
        p_second_wins = second_succ
        p_advance     = 1 - second_succ

    if first_this == "Away":
        return {"away_wins": p_first_wins, "home_wins": p_second_wins, "advance": p_advance}
    return {"away_wins": p_second_wins, "home_wins": p_first_wins, "advance": p_advance}


def game_length_table(away_probs: dict, home_probs: dict,
                       away_succ: float, home_succ: float,
                       current_period: int, ot1_first: str,
                       current_period_probs: dict | None = None) -> pd.DataFrame:
    """
    Forward-looking table starting from current_period.
    current_period_probs: if provided, used as-is for the current period row (must have
    away_wins/home_wins/advance keys). Future periods always use base distributions.
    """
    rows = []
    p_live = 1.0

    for period in range(current_period, current_period + 7):
        if period == current_period and current_period_probs is not None:
            outcome = current_period_probs
        elif period >= 3:
            outcome = shootout_period_probs(away_succ, home_succ)
        else:
            first_this = first_team_for_period(period, ot1_first)
            fp = away_probs if first_this == "Away" else home_probs
            sp = home_probs if first_this == "Away" else away_probs
            raw = period_outcome_probs_ordered(fp, sp, 0, 0)
            outcome = {"away_wins": raw["first_wins"] if first_this == "Away" else raw["second_wins"],
                       "home_wins": raw["second_wins"] if first_this == "Away" else raw["first_wins"],
                       "advance": raw["advance"]}

        p_ends = (outcome["away_wins"] + outcome["home_wins"]) * p_live
        label  = f"OT {period}" if period < current_period + 6 else f"OT {period}+"
        rows.append({
            "OT Period":             label,
            "P(Ends This OT)":       p_ends,
            "P(Still Live Entering)": p_live,
        })
        p_live *= outcome["advance"]

    return pd.DataFrame(rows)


# ── chart helpers ──────────────────────────────────────────────────────────────

def pie_chart(data: pd.DataFrame, title: str) -> alt.Chart:
    # If the data carries an explicit "order" column, stack arcs by it so the
    # slice sequence is deterministic (see PIE_ORDER); otherwise fall back to
    # value order.
    theta_kwargs = {"field": "value", "type": "quantitative", "stack": True}
    encode_kwargs = {}
    if "order" in data.columns:
        encode_kwargs["order"] = alt.Order("order:Q")
        theta_kwargs["sort"] = None
    return (
        alt.Chart(data)
        .encode(
            theta=alt.Theta(**theta_kwargs),
            color=alt.Color(
                field="label", type="nominal",
                sort=data["label"].tolist(),
                scale=alt.Scale(domain=data["label"].tolist(), range=data["color"].tolist()),
                legend=alt.Legend(title=None, orient="bottom", columns=2),
            ),
            tooltip=[alt.Tooltip("label:N", title="Outcome"),
                     alt.Tooltip("value:Q", title="Probability", format=".1%")],
            **encode_kwargs,
        )
        .mark_arc(innerRadius=50, outerRadius=110)
        .properties(title=title, width=300, height=280)
    )


def prob_to_american(p: float) -> str:
    if p <= 0 or p >= 1:
        return "N/A"
    if p >= 0.5:
        return str(-round((p / (1 - p)) * 100))
    return f"+{round(((1 - p) / p) * 100)}"


# ── session state init ─────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "ot_period":               1,
        "away_score":              0,
        "home_score":              0,
        "ot_history":              [],
        "ot1_first":               "Away",
        "first_possession_logged": False,
        "first_possession_key":    None,
        # True after the TD button is pressed but before the PAT try (+2/+1/+0) is chosen.
        "pending_td":              False,
        # Points the first possessor scored in the current period (offense + any def TD against them)
        # Needed for mid-period probability calculations. Always in "first possessor's frame".
        "period_first_pts":        0,
        "period_second_pts":       0,
        # Undo stack — snapshots of the core game state pushed before each logged play.
        "undo_stack":              [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── undo support ─────────────────────────────────────────────────────────────
# The single source of truth for which session keys constitute the "game state"
# that an undo must restore. Transient field-position widgets (field_position,
# down_select, etc.) are intentionally NOT snapshotted — they're cleared on undo
# so the sidebar reverts to 1st & 10 from the 25, matching a fresh possession.
UNDO_KEYS = (
    "ot_period", "away_score", "home_score", "ot_history",
    "first_possession_logged", "first_possession_key", "pending_td",
    "period_first_pts", "period_second_pts",
)
# Transient live-drive widget keys wiped on undo so field position resets cleanly.
_TRANSIENT_KEYS = ("field_position", "down_select", "distance_input",
                   "prev_ytg", "cur_down", "cur_dist")


def push_undo():
    """Snapshot the current game state onto the undo stack before a mutating play."""
    import copy
    snap = {k: copy.deepcopy(st.session_state[k]) for k in UNDO_KEYS if k in st.session_state}
    st.session_state.undo_stack.append(snap)


def pop_undo():
    """Restore the most recent snapshot and clear transient field widgets."""
    if not st.session_state.undo_stack:
        return
    snap = st.session_state.undo_stack.pop()
    for k, v in snap.items():
        st.session_state[k] = v
    for k in _TRANSIENT_KEYS:
        st.session_state.pop(k, None)


# ── sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar() -> dict:

    # ── Compact sidebar spacing ──
    # Streamlit's default sidebar has generous padding/gaps; tighten them so the
    # controls fit without so much scrolling.
    st.sidebar.markdown(
        "<style>"
        # trim the big top padding above the first widget
        "section[data-testid='stSidebar'] div[data-testid='stSidebarUserContent']{padding-top:1rem!important;}"
        # shrink the vertical gap between stacked widgets
        "section[data-testid='stSidebar'] div[data-testid='stVerticalBlock']{gap:0.4rem!important;}"
        # pull slider value/label rows in tight
        "section[data-testid='stSidebar'] div[data-testid='stSlider']{padding-bottom:0!important;}"
        # tighten captions and markdown headers
        "section[data-testid='stSidebar'] div[data-testid='stCaptionContainer']{margin-top:-4px!important;margin-bottom:0!important;}"
        "section[data-testid='stSidebar'] div[data-testid='stMarkdownContainer'] p{margin-bottom:0.15rem!important;}"
        # slimmer expander + dataframe padding
        "section[data-testid='stSidebar'] div[data-testid='stExpander']{margin-bottom:0.3rem!important;}"
        "</style>",
        unsafe_allow_html=True,
    )

    # ── Game Setup (collapsible) ──
    with st.sidebar.expander("Game Setup", expanded=not bool(st.session_state.get("ot_history")) and not st.session_state.get("first_possession_logged")):
        t1, t2 = st.columns(2)
        with t1:
            away_team = st.selectbox("Away", FBS_TEAMS, index=FBS_TEAMS.index("AWAY"), key="away_team")
        with t2:
            home_team = st.selectbox("Home", FBS_TEAMS, index=FBS_TEAMS.index("HOME"), key="home_team")

        reg_score = st.number_input(
            "Tied score entering OT", min_value=0, max_value=999, step=1,
            key="reg_score",
        )
        if not st.session_state.ot_history and not st.session_state.first_possession_logged:
            st.session_state.away_score = reg_score
            st.session_state.home_score = reg_score

        ot1_first = st.radio(
            "Who goes first in OT 1?", ["Away", "Home"],
            index=0 if st.session_state.ot1_first == "Away" else 1,
            horizontal=True, key="ot1_first_radio",
        )
        st.session_state.ot1_first = ot1_first

        ot_period = st.session_state.ot_period
        seq = []
        for p in range(ot_period, ot_period + 4):
            f = first_team_for_period(p, ot1_first)
            fn = away_team if f == "Away" else home_team
            sn = home_team if f == "Away" else away_team
            line = f"**OT {p}:** {fn} → {sn}"
            if p == ot_period:
                line += " ← now"
            seq.append(line)
        st.caption("  \n".join(seq))

    # Read team names back from session state if expander was collapsed
    away_team = st.session_state.get("away_team", "AWAY")
    home_team = st.session_state.get("home_team", "HOME")
    ot1_first = st.session_state.get("ot1_first", "Away")
    ot_period = st.session_state.ot_period

    # ── Strength sliders (always visible) ──
    st.sidebar.markdown("**Team Strength**")
    raw_strength = st.sidebar.slider(
        "Overall Strength", -1.0, 1.0, 0.0, 0.05, key="strength_delta",
        help=(
            "Negative = Away favored; positive = Home favored.\n\n"
            "**Pricing guide (by pregame spread):**\n\n"
            "- Spread 1–3 → ~PK, -120/-110 to -130/+100\n"
            "- Spread 3–6 → ~-140/+110 to -150/+120\n"
            "- Spread 7–10 → ~-170/+140 to -190/+145\n"
            "- Spread 10+ → ~-230/+185 to -250/+200"
        ),
    )
    strength_delta = -raw_strength
    if raw_strength < -0.02:
        fav_label = f"{away_team} +{abs(raw_strength):.2f}"
    elif raw_strength > 0.02:
        fav_label = f"{home_team} +{raw_strength:.2f}"
    else:
        fav_label = "Even"
    st.sidebar.caption(f"Favored: **{fav_label}**")

    off_def_tendency = st.sidebar.slider(
        "Off / Def Tendency", -1.0, 1.0, 0.0, 0.05, key="off_def_tendency",
        help="Positive = offensive game; negative = defensive game.",
    )
    if off_def_tendency < -0.05:
        tend_label = f"Defensive ({off_def_tendency:+.2f})"
    elif off_def_tendency > 0.05:
        tend_label = f"Offensive ({off_def_tendency:+.2f})"
    else:
        tend_label = "Neutral"
    st.sidebar.caption(f"Environment: **{tend_label}**")

    # ── Team aggressiveness (UI only — not yet wired to the model) ──
    away_bg = team_color(away_team)
    home_bg = team_color(home_team)
    # Color each aggressiveness slider's thumb to its team. These are the only
    # column-wrapped sliders in the sidebar (away = 1st column, home = 2nd), so
    # target by column position — robust regardless of other sidebar widgets.
    st.sidebar.markdown(
        f"<style>"
        f"section[data-testid='stSidebar'] div[data-testid='column']:nth-of-type(1) "
        f"div[role='slider']{{background:{away_bg}!important;border-color:{away_bg}!important}}"
        f"section[data-testid='stSidebar'] div[data-testid='column']:nth-of-type(2) "
        f"div[role='slider']{{background:{home_bg}!important;border-color:{home_bg}!important}}"
        f"</style>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("**Aggressiveness**")
    ag1, ag2 = st.sidebar.columns(2)
    with ag1:
        st.markdown(
            f"<div style='font-size:0.72rem;font-weight:700;color:{away_bg};"
            f"filter:brightness(1.6);margin-bottom:-6px;'>{team_abbr(away_team)}</div>",
            unsafe_allow_html=True,
        )
        away_aggr = st.slider(
            "Away aggressiveness", 0.0, 1.0, 0.0, 0.05, key="away_aggr",
            label_visibility="collapsed",
            help="0 = normal play. Higher = suppresses FG (goes for it → more TD/TO) "
                 "and skews TD tries toward 2pt (8) / miss (6) vs PAT (7).",
        )
    with ag2:
        st.markdown(
            f"<div style='font-size:0.72rem;font-weight:700;color:{home_bg};"
            f"filter:brightness(1.6);margin-bottom:-6px;'>{team_abbr(home_team)}</div>",
            unsafe_allow_html=True,
        )
        home_aggr = st.slider(
            "Home aggressiveness", 0.0, 1.0, 0.0, 0.05, key="home_aggr",
            label_visibility="collapsed",
            help="0 = normal play. Higher = suppresses FG (goes for it → more TD/TO) "
                 "and skews TD tries toward 2pt (8) / miss (6) vs PAT (7).",
        )

    is_shootout = ot_period >= 3
    first_this  = first_team_for_period(ot_period, ot1_first)
    second_this = "Home" if first_this == "Away" else "Away"
    first_name  = away_team if first_this == "Away" else home_team
    second_name = home_team if first_this == "Away" else away_team

    st.sidebar.markdown(f"**OT {ot_period} — Log Results**")

    outcome_opts = list(OUTCOME_LABELS.values())
    outcome_keys = list(OUTCOME_LABELS.keys())

    if is_shootout:
        st.sidebar.caption("2-pt Conversion Shootout — from the 3-yd line")

        # Show first team's result as a badge if already logged, then show second team's buttons
        if st.session_state.first_possession_logged:
            first_result = st.session_state.first_possession_key  # "Success" or "Failure"
            st.sidebar.markdown(
                f"<div style='background:#1a1a1a;border-radius:6px;padding:5px 10px;"
                f"font-size:0.8rem;color:#aaa;margin-bottom:6px;'>"
                f"{first_name}: <strong style='color:#fff;'>{first_result} ✓</strong>"
                f"</div>",
                unsafe_allow_html=True,
            )
            ball_name = second_name
            ball_side = second_this
        else:
            ball_name = first_name
            ball_side = first_this

        off_bg = team_color(ball_name)
        off_fg = text_color(off_bg)

        st.sidebar.markdown(
            f"<div style='font-size:0.8rem;color:#aaa;margin-bottom:4px;'>"
            f"<strong style='color:#fff;'>{ball_name}</strong> — 2-pt attempt:</div>",
            unsafe_allow_html=True,
        )

        def _log_shootout(result: str):
            pts = 2 if result == "Success" else 0
            if not st.session_state.first_possession_logged:
                if first_this == "Away":
                    st.session_state.away_score += pts
                else:
                    st.session_state.home_score += pts
                st.session_state.first_possession_logged = True
                st.session_state.first_possession_key    = result
            else:
                first_result_key = st.session_state.first_possession_key
                if second_this == "Away":
                    st.session_state.away_score += pts
                else:
                    st.session_state.home_score += pts
                a_succ = (first_result_key == "Success") if first_this == "Away" else (result == "Success")
                h_succ = (first_result_key == "Success") if first_this == "Home" else (result == "Success")
                st.session_state.ot_history.append({
                    "period":       ot_period,
                    "away_pts":     2 if a_succ else 0,
                    "home_pts":     2 if h_succ else 0,
                    "away_success": a_succ,
                    "home_success": h_succ,
                })
                st.session_state.first_possession_logged = False
                st.session_state.first_possession_key    = None
                if st.session_state.away_score != st.session_state.home_score:
                    pass  # game over
                else:
                    st.session_state.ot_period += 1
            st.rerun()

        st.sidebar.markdown(
            f"<style>.stSidebar div[data-testid='stHorizontalBlock'] button:nth-of-type(1){{"
            f"background:{off_bg}!important;color:{off_fg}!important;border:none!important;"
            f"font-size:1.1rem!important;font-weight:800!important;border-radius:8px!important}}"
            f"</style>",
            unsafe_allow_html=True,
        )
        sb1, sb2 = st.sidebar.columns(2)
        with sb1:
            if st.button("✓ Success", key="btn_success", use_container_width=True):
                push_undo()
                _log_shootout("Success")
        with sb2:
            if st.button("✗ Failure", key="btn_failure", use_container_width=True):
                push_undo()
                _log_shootout("Failure")

        field_position = down = distance = None

    else:
        # ── Which team has the ball right now ──
        ball_team = first_name if not st.session_state.first_possession_logged else second_name
        ball_side = first_this if not st.session_state.first_possession_logged else second_this
        off_bg    = team_color(ball_team)
        off_fg    = text_color(off_bg)

        # ── Field position slider (0-40 yds from end zone) ──
        prev_ytg = st.session_state.get("prev_ytg", 25)
        field_position = st.sidebar.slider(
            "Field Position (yds from end zone)", 0, 40, 25, key="field_position",
        )
        yards_gained = prev_ytg - field_position
        st.session_state["prev_ytg"] = field_position

        # Auto-advance down/distance based on movement
        cur_down = st.session_state.get("cur_down", 1)
        cur_dist = st.session_state.get("cur_dist", 10)
        if yards_gained > 0:
            if yards_gained >= cur_dist:
                cur_down = 1
                cur_dist = 10
            else:
                cur_down = min(cur_down + 1, 4)
                cur_dist = cur_dist - yards_gained
        st.session_state["cur_down"] = cur_down
        st.session_state["cur_dist"] = cur_dist

        # ── Down & Distance side by side ──
        down_opts = ["1st", "2nd", "3rd", "4th"]
        dc1, dc2 = st.sidebar.columns(2)
        with dc1:
            down = st.selectbox("Down", down_opts, index=cur_down - 1, key="down_select")
        with dc2:
            distance = st.number_input("Dist", min_value=1, max_value=40, value=int(cur_dist), key="distance_input")
        # Keep session vars in sync if user manually overrides
        st.session_state["cur_down"] = down_opts.index(down) + 1
        st.session_state["cur_dist"] = int(distance)

        # ── Show first team result if already logged ──
        if st.session_state.first_possession_logged:
            first_key_logged = st.session_state.first_possession_key
            st.sidebar.markdown(
                f"<div style='background:#1a1a1a;border-radius:6px;padding:5px 10px;"
                f"font-size:0.8rem;color:#aaa;margin-bottom:4px;'>"
                f"{first_name}: <strong style='color:#fff;'>{OUTCOME_LABELS[first_key_logged]}</strong> ✓"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ── Label ──
        st.sidebar.markdown(
            f"<div style='font-size:0.8rem;color:#aaa;margin:6px 0 4px 0;'>"
            f"<strong style='color:{off_bg};filter:brightness(1.6);'>{ball_team}</strong> — log result:</div>",
            unsafe_allow_html=True,
        )

        def _log_result(outcome_key):
            off = OFFENSE_PTS[outcome_key]
            dfd = DEFENSE_PTS[outcome_key]
            reset_keys = ("field_position", "down_select", "distance_input", "prev_ytg", "cur_down", "cur_dist")
            st.session_state.pending_td = False  # PAT try resolved (or non-TD outcome)
            if not st.session_state.first_possession_logged:
                if first_this == "Away":
                    st.session_state.away_score += off
                    st.session_state.home_score += dfd
                else:
                    st.session_state.home_score += off
                    st.session_state.away_score += dfd
                st.session_state.period_first_pts        = off
                st.session_state.period_second_pts       = dfd
                st.session_state.first_possession_logged = True
                st.session_state.first_possession_key    = outcome_key
                for k in reset_keys:
                    if k in st.session_state: del st.session_state[k]
            else:
                first_key_l = st.session_state.first_possession_key
                if second_this == "Away":
                    st.session_state.away_score += off
                    st.session_state.home_score += dfd
                else:
                    st.session_state.home_score += off
                    st.session_state.away_score += dfd
                if first_this == "Away":
                    a_key, h_key = first_key_l, outcome_key
                    a_pts = OFFENSE_PTS[first_key_l] + DEFENSE_PTS[outcome_key]
                    h_pts = OFFENSE_PTS[outcome_key] + DEFENSE_PTS[first_key_l]
                else:
                    h_key, a_key = first_key_l, outcome_key
                    h_pts = OFFENSE_PTS[first_key_l] + DEFENSE_PTS[outcome_key]
                    a_pts = OFFENSE_PTS[outcome_key] + DEFENSE_PTS[first_key_l]
                st.session_state.ot_history.append({
                    "period":       ot_period,
                    "away_outcome": a_key,
                    "home_outcome": h_key,
                    "away_pts":     a_pts,
                    "home_pts":     h_pts,
                })
                st.session_state.first_possession_logged = False
                st.session_state.first_possession_key    = None
                st.session_state.period_first_pts        = 0
                st.session_state.period_second_pts       = 0
                for k in reset_keys:
                    if k in st.session_state: del st.session_state[k]
                if st.session_state.away_score != st.session_state.home_score:
                    pass
                else:
                    st.session_state.ot_period += 1
            st.rerun()

        btn_css = (
            f"<style>.stSidebar div[data-testid='stHorizontalBlock'] button:nth-of-type(1){{"
            f"background:#1B5E20!important;color:#fff!important;border:none!important;"
            f"font-size:1.5rem!important;font-weight:900!important;border-radius:8px!important}}"
            f".stSidebar div[data-testid='stHorizontalBlock'] button:nth-of-type(2){{"
            f"background:#0D47A1!important;color:#fff!important;border:none!important;"
            f"font-size:1.5rem!important;font-weight:900!important;border-radius:8px!important}}"
            f".stSidebar div[data-testid='stHorizontalBlock'] button:nth-of-type(3){{"
            f"font-size:1.5rem!important;font-weight:900!important;border-radius:8px!important}}"
            f"</style>"
        )
        st.sidebar.markdown(btn_css, unsafe_allow_html=True)

        if st.session_state.pending_td:
            # NCAA mandates a 2-pt try after a TD starting in OT2 — no 1-pt PAT.
            mandatory_2pt = ot_period >= 2
            if mandatory_2pt:
                # ── TD scored in OT2+ — the try is 2-pt only: +2 (made) / +0 (failed) ──
                st.sidebar.markdown(
                    f"<div style='font-size:0.8rem;color:#aaa;margin:2px 0 4px 0;'>"
                    f"<strong style='color:#fff;'>{ball_team}</strong> scored a TD — mandatory 2-pt try:</div>",
                    unsafe_allow_html=True,
                )
                pb1, pb2 = st.sidebar.columns(2)
                with pb1:
                    if st.button("+2", key="btn_pat2", use_container_width=True):
                        _log_result("td_2pt")   # 8 pts
                with pb2:
                    if st.button("+0", key="btn_pat0", use_container_width=True):
                        _log_result("td_6")     # 6 pts
            else:
                # ── TD scored in OT1 — choose the try: +2 (2pt), +1 (PAT), +0 (missed) ──
                st.sidebar.markdown(
                    f"<div style='font-size:0.8rem;color:#aaa;margin:2px 0 4px 0;'>"
                    f"<strong style='color:#fff;'>{ball_team}</strong> scored a TD — the try:</div>",
                    unsafe_allow_html=True,
                )
                pb1, pb2, pb3 = st.sidebar.columns(3)
                with pb1:
                    if st.button("+2", key="btn_pat2", use_container_width=True):
                        _log_result("td_2pt")   # 8 pts
                with pb2:
                    if st.button("+1", key="btn_pat1", use_container_width=True):
                        _log_result("td_pat")   # 7 pts
                with pb3:
                    if st.button("+0", key="btn_pat0", use_container_width=True):
                        _log_result("td_6")     # 6 pts
        else:
            b1, b2, b3 = st.sidebar.columns(3)
            with b1:
                if st.button("TD", key="btn_td", use_container_width=True):
                    # Snapshot BEFORE entering the pending-TD state so a single undo
                    # reverts the whole play (TD press + try choice). The +2/+1/+0
                    # try buttons deliberately do NOT push again.
                    push_undo()
                    st.session_state.pending_td = True
                    st.rerun()
            with b2:
                if st.button("FG", key="btn_fg", use_container_width=True):
                    push_undo()
                    _log_result("fg")
            with b3:
                if st.button("TO", key="btn_to", use_container_width=True):
                    push_undo()
                    _log_result("turnover")

    # ── Undo last play ──
    undo_n = len(st.session_state.get("undo_stack", []))
    if st.sidebar.button(f"↩ Undo last play{f'  ({undo_n})' if undo_n else ''}",
                         key="undo_btn", use_container_width=True,
                         disabled=(undo_n == 0)):
        pop_undo()
        st.rerun()

    # Full Reset
    st.sidebar.markdown(
        "<style>.stSidebar div[data-testid='stBaseButton-secondary']{{"
        "background:#F9A825!important;color:#111!important;border:none!important;font-weight:700!important}}"
        "</style>",
        unsafe_allow_html=True,
    )
    if st.sidebar.button("⚠️ Full Reset", type="secondary", key="reset_btn", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ("away_team", "home_team", "strength_delta",
                         "off_def_tendency", "ot1_first_radio",
                         "away_aggr", "home_aggr"):
                del st.session_state[k]
        for k in ("prev_ytg", "cur_down", "cur_dist"):
            st.session_state.pop(k, None)
        st.rerun()

    # ── OT History (bottom) ──
    if st.session_state.ot_history:
        st.sidebar.markdown("**OT History**")
        rows = []
        for entry in st.session_state.ot_history:
            p = entry["period"]
            a_val = str(entry.get("away_pts", "—"))
            h_val = str(entry.get("home_pts", "—"))
            rows.append({"OT": f"OT {p}", away_team: a_val, home_team: h_val})
        st.sidebar.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    return {
        "away_team":                away_team,
        "home_team":                home_team,
        "strength_delta":           strength_delta,
        "off_def_tendency":         off_def_tendency,
        "away_aggr":                away_aggr,
        "home_aggr":                home_aggr,
        "away_score":               st.session_state.away_score,
        "home_score":               st.session_state.home_score,
        "ot_period":                ot_period,
        "is_shootout":              is_shootout,
        "ot1_first":                ot1_first,
        "first_this":               first_this,
        "first_name":               first_name,
        "second_name":              second_name,
        "first_possession_logged":  st.session_state.first_possession_logged,
        "field_position":           field_position if not is_shootout else None,
        "down":                     down           if not is_shootout else None,
        "distance":                 distance       if not is_shootout else None,
        "down_int":                 {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}.get(down, 1) if not is_shootout else 1,
        "distance_int":             int(distance)  if not is_shootout and distance else 10,
    }


# ── main panel ────────────────────────────────────────────────────────────────

def render_main(inputs: dict):
    away_team              = inputs["away_team"]
    home_team              = inputs["home_team"]
    strength_delta         = inputs["strength_delta"]
    off_def_tendency       = inputs["off_def_tendency"]
    away_score             = inputs["away_score"]
    home_score             = inputs["home_score"]
    ot_period              = inputs["ot_period"]
    is_shootout            = inputs["is_shootout"]
    ot1_first              = inputs["ot1_first"]
    first_possession_logged = inputs["first_possession_logged"]
    away_aggr              = inputs.get("away_aggr", 0.0)
    home_aggr              = inputs.get("home_aggr", 0.0)

    # Live situation from sidebar (default to OT start if not set)
    live_down       = inputs.get("down_int", 1)
    live_distance   = inputs.get("distance_int", 10)
    live_ytg        = inputs.get("field_position", 25) if inputs.get("field_position") else 25

    # Base distributions — OT start defaults (1st & 10 from 25).
    # Used ONLY for forward-looking math (future periods in the game-win recursion
    # and the game-length table) — never the current period. The only future
    # STANDARD period is OT2 (period 3+ is always the shootout, which ignores these),
    # and OT2 mandates a 2-pt try, so build these at ot_period=2 so the mandatory-2pt
    # TD split is baked into every future standard period.
    away_probs_base = base_drive_probs( strength_delta, off_def_tendency, 1, 10, 25, ot_period=2)
    home_probs_base = base_drive_probs(-strength_delta, off_def_tendency, 1, 10, 25, ot_period=2)
    # Shootout 2-pt success rates — anchored on the same league base as the
    # mandatory-2pt TD split (TWO_PT_BASE_RATE), then nudged by tendency/strength.
    away_succ  = max(0.1, min(0.9, TWO_PT_BASE_RATE + off_def_tendency * 0.1 + strength_delta * 0.1))
    home_succ  = max(0.1, min(0.9, TWO_PT_BASE_RATE + off_def_tendency * 0.1 - strength_delta * 0.1))

    # Live distributions — both teams' CURRENT-period drives. Each team always
    # carries its OWN aggressiveness (it's a team property for this period, and both
    # teams possess within the period). What flips based on possession is only the
    # FIELD SITUATION: the team with the ball uses the live down/distance/field
    # position; the other team uses OT-start defaults (their drive hasn't begun).
    # The base/future distributions (away_probs_base/home_probs_base above) stay at
    # aggressiveness=0, so future OT PERIODS are unaffected until they become current.
    first_this_live = inputs["first_this"]
    if not is_shootout:
        # Which side currently has the ball?
        if not first_possession_logged:
            ball_side = first_this_live
        else:
            ball_side = "Home" if first_this_live == "Away" else "Away"

        if ball_side == "Away":
            away_probs_live = base_drive_probs( strength_delta, off_def_tendency, live_down, live_distance, live_ytg, away_aggr, ot_period=ot_period)
            home_probs_live = base_drive_probs(-strength_delta, off_def_tendency, 1, 10, 25, home_aggr, ot_period=ot_period)
        else:
            away_probs_live = base_drive_probs( strength_delta, off_def_tendency, 1, 10, 25, away_aggr, ot_period=ot_period)
            home_probs_live = base_drive_probs(-strength_delta, off_def_tendency, live_down, live_distance, live_ytg, home_aggr, ot_period=ot_period)
    else:
        away_probs_live = dict(away_probs_base)
        home_probs_live = dict(home_probs_base)

    # Display distributions — collapsed to certainty once the first team has possessed.
    # Second team's display uses the live situation above.
    away_probs = dict(away_probs_live)
    home_probs = dict(home_probs_live)
    if first_possession_logged and not is_shootout:
        first_key = st.session_state.first_possession_key
        collapsed = {k: (1.0 if k == first_key else 0.0) for k in OUTCOME_LABELS}
        if inputs["first_this"] == "Away":
            away_probs = collapsed
        else:
            home_probs = collapsed

    # TD pending — the ball team has scored a TD but the try (+2/+1/+0) isn't chosen
    # yet. Converge that team's distribution onto the three TD point totals (6/7/8),
    # renormalized, so both the drive pie and the moneyline reflect the certain TD.
    if st.session_state.get("pending_td") and not is_shootout:
        td_keys = ("td_pat", "td_2pt", "td_6")
        ball_is_away = (
            (inputs["first_this"] == "Away" and not first_possession_logged) or
            (inputs["first_this"] == "Home" and first_possession_logged)
        )
        src = away_probs if ball_is_away else home_probs
        td_mass = sum(src[k] for k in td_keys)
        if td_mass > 0:
            converged = {k: (src[k] / td_mass if k in td_keys else 0.0) for k in OUTCOME_LABELS}
        else:
            # No TD mass to reweight (e.g. already collapsed elsewhere) — split evenly.
            converged = {k: (1.0 / len(td_keys) if k in td_keys else 0.0) for k in OUTCOME_LABELS}
        if ball_is_away:
            away_probs = converged
        else:
            home_probs = converged

    away_bg  = team_color(away_team)
    home_bg  = team_color(home_team)
    away_fg  = text_color(away_bg)
    home_fg  = text_color(home_bg)

    # ── Game-win moneyline ──
    # Use the display distributions (live/collapsed) so the moneyline reflects
    # what we actually know about the current situation.
    gw = game_win_probs(
        away_probs, home_probs,
        away_succ, home_succ,
        ot_period, ot1_first,
        first_possession_logged,
        st.session_state.get("period_first_pts", 0),
        st.session_state.get("period_second_pts", 0),
        future_away_probs=away_probs_base,
        future_home_probs=home_probs_base,
        first_shootout_result=(st.session_state.first_possession_key
                               if is_shootout and first_possession_logged else None),
    )
    away_win_p = gw["away_wins"]
    home_win_p = gw["home_wins"]

    ml_a = prob_to_american(away_win_p)
    ml_h = prob_to_american(home_win_p)

    away_abbr = team_abbr(away_team)
    home_abbr = team_abbr(home_team)

    # Title + score + moneyline — abbreviations keep widths stable
    st.markdown(
        f"""
        <table style="width:100%;border-collapse:separate;border-spacing:6px;margin-bottom:2px;table-layout:fixed;">
          <colgroup><col style="width:40%"><col style="width:20%"><col style="width:40%"></colgroup>
          <tr>
            <td style="background:{away_bg};border-radius:10px;padding:12px 14px;text-align:center;overflow:hidden;">
              <div style="color:{away_fg};font-size:0.85rem;font-weight:600;opacity:0.85;">AWAY</div>
              <div style="color:{away_fg};font-size:1.25rem;font-weight:800;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{away_team}</div>
              <div style="color:{away_fg};font-size:2.4rem;font-weight:900;line-height:1.1;">{ml_a}</div>
              <div style="color:{away_fg};font-size:0.85rem;opacity:0.85;">{away_win_p:.1%} to win</div>
            </td>
            <td style="background:#1a1a1a;border-radius:10px;padding:10px 6px;text-align:center;vertical-align:middle;">
              <div style="color:#aaa;font-size:0.7rem;font-weight:600;letter-spacing:0.08em;">CFB OT PRICER</div>
              <div style="color:#fff;font-size:2rem;font-weight:900;line-height:1.1;margin:4px 0;">{away_score} – {home_score}</div>
              <div style="background:#333;color:#ddd;font-size:0.8rem;font-weight:700;border-radius:6px;padding:2px 10px;display:inline-block;margin-top:2px;">OT {ot_period}</div>
            </td>
            <td style="background:{home_bg};border-radius:10px;padding:12px 14px;text-align:center;overflow:hidden;">
              <div style="color:{home_fg};font-size:0.85rem;font-weight:600;opacity:0.85;">HOME</div>
              <div style="color:{home_fg};font-size:1.25rem;font-weight:800;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{home_team}</div>
              <div style="color:{home_fg};font-size:2.4rem;font-weight:900;line-height:1.1;">{ml_h}</div>
              <div style="color:{home_fg};font-size:0.85rem;opacity:0.85;">{home_win_p:.1%} to win</div>
            </td>
          </tr>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ── OT Tracker + Drive Pies ──
    # Build rows for every period that has been played plus the current active one.
    max_period = max(ot_period, max((e["period"] for e in st.session_state.ot_history), default=ot_period))
    tracker_rows = []
    for p in range(1, max_period + 1):
        hist = next((e for e in st.session_state.ot_history if e["period"] == p), None)
        first_this_p = first_team_for_period(p, ot1_first)
        if hist:
            if p >= 3:
                a_cell = "✓" if hist.get("away_success") else "✗"
                h_cell = "✓" if hist.get("home_success") else "✗"
            else:
                a_cell = str(hist.get('away_pts', '—'))
                h_cell = str(hist.get('home_pts', '—'))
            a_possession = False
            h_possession = False
        else:
            # Who currently has the ball?
            away_has_ball = (
                (first_this_p == "Away" and not first_possession_logged) or
                (first_this_p == "Home" and first_possession_logged)
            )
            home_has_ball = (
                (first_this_p == "Home" and not first_possession_logged) or
                (first_this_p == "Away" and first_possession_logged)
            )
            if p == ot_period and first_possession_logged and not is_shootout:
                fk = st.session_state.first_possession_key
                logged = str(OFFENSE_PTS[fk])
                a_cell = logged if first_this_p == "Away" else ""
                h_cell = logged if first_this_p == "Home" else ""
            else:
                a_cell = ""
                h_cell = ""
            a_possession = p == ot_period and away_has_ball
            h_possession = p == ot_period and home_has_ball
        tracker_rows.append({"period": p, "away": a_cell, "home": h_cell,
                              "a_possession": a_possession, "h_possession": h_possession})

    def _tracker_html(rows, away_team, home_team, away_bg, away_fg, home_bg, home_fg):
        a_abbr = team_abbr(away_team)
        h_abbr = team_abbr(home_team)
        CELL = "background:#1a1a1a;color:#ddd;font-weight:400;"
        td_base = "font-size:0.9rem;padding:6px 10px;text-align:center;border-top:1px solid #333;"
        html = f"""<table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;table-layout:fixed;">
          <colgroup><col style="width:40%"><col style="width:20%"><col style="width:40%"></colgroup>
          <thead><tr>
            <th style="background:{away_bg};padding:6px 10px;text-align:center;font-size:0.85rem;font-weight:800;color:{away_fg};">{a_abbr}</th>
            <th style="background:#1a1a1a;padding:6px 10px;text-align:center;font-size:0.75rem;font-weight:600;color:#aaa;letter-spacing:0.05em;">OT</th>
            <th style="background:{home_bg};padding:6px 10px;text-align:center;font-size:0.85rem;font-weight:800;color:{home_fg};">{h_abbr}</th>
          </tr></thead><tbody>"""
        for row in rows:
            p = row["period"]
            a_content = "🏈" if row["a_possession"] else row["away"]
            h_content = "🏈" if row["h_possession"] else row["home"]
            html += f"""<tr>
              <td style="{CELL}{td_base}">{a_content}</td>
              <td style="background:#222;color:#fff;font-weight:800;font-size:0.8rem;{td_base}">OT {p}</td>
              <td style="{CELL}{td_base}">{h_content}</td>
            </tr>"""
        html += "</tbody></table>"
        return html

    away_pie_col, tracker_col, home_pie_col = st.columns([1, 1, 1])

    with tracker_col:
        st.markdown(
            _tracker_html(tracker_rows, away_team, home_team,
                          away_bg, away_fg, home_bg, home_fg),
            unsafe_allow_html=True,
        )

    if is_shootout:
        with away_pie_col:
            st.metric(f"{away_team} 2-pt Success", f"{away_succ:.1%}")
        with home_pie_col:
            st.metric(f"{home_team} 2-pt Success", f"{home_succ:.1%}")
    else:
        with away_pie_col:
            away_df = pd.DataFrame([{"label": OUTCOME_LABELS[k], "value": away_probs[k],
                                     "color": OUTCOME_COLORS[k], "order": i}
                                    for i, k in enumerate(PIE_ORDER)])
            st.altair_chart(pie_chart(away_df, f"{away_team} Drive"), use_container_width=True)
        with home_pie_col:
            home_df = pd.DataFrame([{"label": OUTCOME_LABELS[k], "value": home_probs[k],
                                     "color": OUTCOME_COLORS[k], "order": i}
                                    for i, k in enumerate(PIE_ORDER)])
            st.altair_chart(pie_chart(home_df, f"{home_team} Drive"), use_container_width=True)

        with st.expander("Drive probability breakdown"):
            st.dataframe(
                pd.DataFrame([{"Outcome": OUTCOME_LABELS[k],
                                away_team: f"{away_probs[k]:.1%}",
                                home_team: f"{home_probs[k]:.1%}"} for k in PIE_ORDER]),
                hide_index=True, use_container_width=True,
            )

    st.divider()

    # ── Period outcome (compute here so game length table can reuse it) ──
    first_this = first_team_for_period(ot_period, ot1_first)
    if is_shootout:
        if first_possession_logged:
            period_probs = shootout_period_probs(
                away_succ, home_succ, first_this, st.session_state.first_possession_key)
        else:
            period_probs = shootout_period_probs(away_succ, home_succ)
    else:
        fp = away_probs if first_this == "Away" else home_probs
        sp = home_probs if first_this == "Away" else away_probs
        raw = period_outcome_probs_ordered(fp, sp, 0, 0)
        period_probs = {
            "away_wins": raw["first_wins"]  if first_this == "Away" else raw["second_wins"],
            "home_wins": raw["second_wins"] if first_this == "Away" else raw["first_wins"],
            "advance":   raw["advance"],
        }

    # ── Game Length table with odds columns ──
    gl_df = game_length_table(
        away_probs_base, home_probs_base,
        away_succ, home_succ, ot_period, ot1_first,
        current_period_probs=period_probs,
    )
    # P(reaches this OT) = P(still live entering) for the current period = 1.0,
    # for future periods it's the cumulative advance probability.
    gl_df["P(Reaches This OT)"] = [1.0] + list(gl_df["P(Still Live Entering)"].iloc[1:])

    # ── Period outcome pie — compact, no legend, no big metrics ──
    period_df = pd.DataFrame([
        {"label": f"{away_team} wins", "value": period_probs["away_wins"], "color": away_bg},
        {"label": f"Advance",          "value": period_probs["advance"],   "color": PERIOD_COLORS["advance"]},
        {"label": f"{home_team} wins", "value": period_probs["home_wins"], "color": home_bg},
    ])
    compact_pie = (
        alt.Chart(period_df)
        .encode(
            theta=alt.Theta(field="value", type="quantitative", stack=True),
            color=alt.Color(
                field="label", type="nominal",
                scale=alt.Scale(domain=period_df["label"].tolist(), range=period_df["color"].tolist()),
                legend=None,
            ),
            tooltip=[alt.Tooltip("label:N", title="Outcome"),
                     alt.Tooltip("value:Q", title="Probability", format=".1%")],
        )
        .mark_arc(innerRadius=35, outerRadius=75)
        .properties(width=200, height=180)
    )

    pie_col, table_col = st.columns([1, 2])

    with pie_col:
        st.markdown(f"**OT {ot_period} Result Probabilities**")
        st.altair_chart(compact_pie, use_container_width=True)
        # Color-coded percentage pills — no labels, just the numbers
        st.markdown(
            f"""<div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap;margin-top:-8px;">
              <span style="background:{away_bg};color:{away_fg};border-radius:4px;padding:2px 7px;font-size:0.75rem;font-weight:600;">{period_probs['away_wins']:.1%}</span>
              <span style="background:#555;color:#fff;border-radius:4px;padding:2px 7px;font-size:0.75rem;font-weight:600;">{period_probs['advance']:.1%}</span>
              <span style="background:{home_bg};color:{home_fg};border-radius:4px;padding:2px 7px;font-size:0.75rem;font-weight:600;">{period_probs['home_wins']:.1%}</span>
            </div>""",
            unsafe_allow_html=True,
        )

    with table_col:
        st.markdown("**Game Length Markets**")
        ends_vals    = gl_df["P(Ends This OT)"].tolist()
        reaches_vals = gl_df["P(Reaches This OT)"].tolist()

        def _prob_bg(p: float) -> str:
            # green gradient: low prob = very light green, high prob = medium green
            # r: 220→160, g: 240→195, b: 220→160 — stays readable at all intensities
            r = int(220 - p * 60)
            g = int(240 - p * 45)
            b = int(220 - p * 60)
            return f"background-color: rgb({r},{g},{b}); color: #111;"

        def _style_row(row):
            ends_p    = ends_vals[row.name]
            reaches_p = reaches_vals[row.name]
            base = [""] * len(row)
            cols = list(row.index)
            for col, p in [("Ends This OT", ends_p), ("Ends This OT (odds)", ends_p),
                           ("Reaches This OT", reaches_p), ("Reaches This OT (odds)", reaches_p)]:
                if col in cols:
                    base[cols.index(col)] = _prob_bg(p)
            return base

        display = pd.DataFrame({
            "OT Period":              gl_df["OT Period"],
            "Ends This OT":           gl_df["P(Ends This OT)"].apply(lambda x: f"{x:.1%}"),
            "Ends This OT (odds)":    gl_df["P(Ends This OT)"].apply(prob_to_american),
            "Reaches This OT":        gl_df["P(Reaches This OT)"].apply(lambda x: f"{x:.1%}"),
            "Reaches This OT (odds)": gl_df["P(Reaches This OT)"].apply(prob_to_american),
        })
        st.dataframe(
            display.style.apply(_style_row, axis=1),
            hide_index=True, use_container_width=True,
        )

    st.caption("v0.4 — CFB OT Pricer | Placeholder probabilities")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="CFB OT Pricer",
        page_icon="🏈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    inputs = render_sidebar()
    render_main(inputs)


if __name__ == "__main__":
    main()
