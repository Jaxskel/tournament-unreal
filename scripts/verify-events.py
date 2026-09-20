#!/usr/bin/env python3
"""Check actual server JSONL output. This is a diagnostic, not a settlement service."""
import argparse
import json
from pathlib import Path


def verify(events, require_complete=True):
    if not events:
        raise ValueError('empty event stream')
    match_id = events[0].get('match_id')
    if not isinstance(match_id, str) or not match_id:
        raise ValueError('missing match ID')
    counts = {}
    finished = False
    for index, event in enumerate(events, 1):
        if finished:
            raise ValueError('event emitted after match_end')
        if event.get('match_id') != match_id:
            raise ValueError('mixed match IDs')
        if event.get('event_id') != str(index):
            raise ValueError('duplicate, missing, or unordered event ID')
        if event.get('schema_version') != 1:
            raise ValueError('unsupported schema')
        if event.get('practice_demo') is not True or event.get('real_money') is not False:
            raise ValueError('demo/reward boundary violated')
        kind = event.get('type')
        if kind not in {'match_start', 'kill', 'frag_race_target_reached', 'match_end'}:
            raise ValueError('unknown event type')
        if index == 1 and kind != 'match_start':
            raise ValueError('first event is not match_start')
        if index > 1 and kind == 'match_start':
            raise ValueError('duplicate match_start')
        counts[kind] = counts.get(kind, 0) + 1
        if kind == 'kill':
            eligible = event.get('eligible_enemy_frag')
            if eligible and (event.get('suicide') or event.get('world_death') or event.get('teamkill')):
                raise ValueError('ineligible death labeled an enemy frag')
            if not eligible and event.get('practice_points_awarded') != 0:
                raise ValueError('points awarded for an ineligible death')
        if kind == 'match_end':
            finished = True
            rows = event.get('scoreboard', [])
            ids = [row['participant_id'] for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError('duplicate scoreboard participant')
            previous = None
            rank = 0
            for position, row in enumerate(rows, 1):
                score = row['vanilla_score']
                if previous is not None and score > previous:
                    raise ValueError('scoreboard is not sorted')
                if previous is None or score != previous:
                    rank = position
                if row['rank'] != rank:
                    raise ValueError('incorrect rank/tie handling')
                previous = score
    if require_complete and not finished:
        raise ValueError('match did not finish')
    return {'match_id': match_id, 'events': len(events), 'complete': finished, 'counts': counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    reports = []
    for path in args.files:
        try:
            events = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
            reports.append({'file': path.name, **verify(events, not args.allow_incomplete)})
        except (ValueError, KeyError, TypeError) as error:
            parser.exit(1, f'{path.name}: {error}\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
