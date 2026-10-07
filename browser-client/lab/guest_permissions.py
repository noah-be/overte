# SPDX-License-Identifier: Apache-2.0
"""Bounded diagnostics for the isolated lab's intended guest rows only."""
GROUPS = ('anonymous', 'localhost', 'logged-in', 'friends')
FLAGS = ('id_can_connect', 'id_can_rez_avatar_entities', 'id_can_adjust_locks', 'id_can_rez',
         'id_can_rez_tmp', 'id_can_write_to_asset_server', 'id_can_connect_past_max_capacity',
         'id_can_kick', 'id_can_replace_content', 'id_can_get_and_set_private_user_data', 'id_can_view_asset_urls')


def guest_permission_diagnostics(rows, expected):
    if set(expected) != set(FLAGS) or any(type(expected[key]) is not bool for key in FLAGS):
        raise ValueError('Invalid intended guest baseline')
    report = {'kind': 'guest-permission-readback', 'passed': False, 'shape': 'valid',
              'unknownRows': 0, 'duplicateRows': 0, 'missingRows': [], 'differences': []}
    if not isinstance(rows, list) or len(rows) > 16:
        report['shape'] = 'invalid-or-over-limit'
        return report
    groups = {}
    for row in rows:
        if not isinstance(row, dict):
            report['unknownRows'] += 1
            continue
        name = row.get('permissions_id')
        if type(name) is not str or name not in GROUPS:
            report['unknownRows'] += 1
            continue
        if name in groups:
            report['duplicateRows'] += 1
            continue
        groups[name] = row
    for group in GROUPS:
        if group not in groups:
            report['missingRows'].append(group)
            continue
        for flag in FLAGS:
            actual = groups[group].get(flag)
            if type(actual) is not bool or actual != expected[flag]:
                report['differences'].append({'group': group, 'flag': flag, 'expected': expected[flag],
                                              'actual': actual if type(actual) is bool else 'missing-or-non-boolean'})
    report['passed'] = not any((report['unknownRows'], report['duplicateRows'], report['missingRows'], report['differences']))
    return report
