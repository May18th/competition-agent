# -*- coding: utf-8 -*-
"""Shared cover-field normalization for Word/PDF/PPT exports.

The cover is a user-editable template. Missing identity data stays as an
explicit placeholder instead of being invented or silently omitted.
"""


def _clean(value):
    return str(value or "").strip()


def cover_team_lines(team=None, team_name=None, leader=None, members=None,
                     contact=None):
    """Return the compact identity fields shown on the cover.

    Members and their division of work belong in the body of the proposal,
    not on the cover.  Keep ``members`` in the signature for compatibility
    with existing render callers, but deliberately do not render it here.
    """
    raw_team = _clean(team)
    team_name = _clean(team_name)
    leader = _clean(leader)
    members = _clean(members)
    contact = _clean(contact)

    # Existing UI submissions commonly put the team name and member roles in
    # one multiline field. Preserve it, while keeping the first line as the
    # display name and the remaining lines as editable member information.
    raw_lines = [x.strip() for x in raw_team.splitlines() if x.strip()]
    if not team_name and raw_lines:
        first = raw_lines[0]
        if not any(k in first for k in ("成员", "队长", "负责人", "分工")):
            team_name = first
    if not members and raw_lines:
        if len(raw_lines) > 1:
            members = "\n".join(raw_lines[1:])
        elif any(k in raw_lines[0] for k in ("成员", "队长", "负责人", "分工")):
            members = raw_lines[0]

    return [
        ("团队名称", team_name or "________________"),
        ("负责人", leader or "________________"),
    ]
