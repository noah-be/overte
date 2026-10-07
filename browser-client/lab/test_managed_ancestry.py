"""Exact managed stop over fake kernel records; no live process operations."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parent / 'manage.py'


class ManagedAncestry(unittest.TestCase):
    def setup_case(self, mode):
        tree = ast.parse(SOURCE.read_text())
        definitions = [node for node in tree.body
                       if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                       and node.name in ('_OwnedStop', 'stop')]
        self.assertEqual({node.name for node in definitions}, {'_OwnedStop', 'stop'})
        self.rows = {
            101: dict(pid=101, birth='10', parent=7, group=101, session=101, uid=99),
            102: dict(pid=102, birth='11', parent=101, group=101, session=101, uid=99),
        }
        self.closed = []
        self.sent = []
        self.clock = 0.0
        self.next_fd = 700
        self.fd_roles = {}
        self.original = json.dumps({'owned': {'pid': 101, 'startTicks': '10'}})
        self.registry = SimpleNamespace(data=self.original)

        def identity(pid):
            return dict(self.rows[pid]) if pid in self.rows else None

        def open_fd(pid):
            self.next_fd += 1
            self.fd_roles[self.next_fd] = pid
            return self.next_fd

        def send_fd(fd, number):
            self.sent.append((self.fd_roles[fd], number))
            self.rows.pop(self.fd_roles[fd], None)

        def write_registry(text):
            self.registry.data = text

        class FakePath:
            def __init__(self, *unused):
                pass

            def read_bytes(self):
                return b'/owned-source-repository'

            def resolve(self):
                return '/owned-source-repository'

        fake_os = SimpleNamespace(getuid=lambda: 99, getpid=lambda: 7,
                                  pidfd_open=open_fd, close=self.closed.append,
                                  getpgid=lambda pid: pid)
        fake_signal = SimpleNamespace(SIGTERM=15, SIGKILL=9, pidfd_send_signal=send_fd)
        fake_time = SimpleNamespace(monotonic=lambda: self.clock,
                                    sleep=lambda delay: setattr(self, 'clock', self.clock + delay))
        self.registry.write_text = write_registry
        scope = dict(Path=FakePath, os=fake_os, signal=fake_signal, time=fake_time,
                     json=json, REPO='/owned-source-repository', STATE=self.registry,
                     load_state=lambda: json.loads(self.registry.data), alive=lambda pid: True,
                     start_ticks=lambda pid: '10', print=lambda *unused: None)
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(SOURCE), 'exec'), scope)
        actual = scope['_OwnedStop']
        actual.identity = staticmethod(identity)
        actual.group_absent = staticmethod(
            lambda group: not any(row['group'] == group for row in self.rows.values()))

        def children(owner, row):
            if row['pid'] != 101:
                return []
            if mode == 'stable':
                return [102]
            # Sample authentic child IDs, then the parent exits before the
            # production observer obtains the child's later identity record.
            self.rows.pop(101, None)
            self.rows[102]['parent'] = 303
            drift = {'reused': ('birth', '900'), 'uid': ('uid', 100),
                     'group': ('group', 404), 'session': ('session', 404)}.get(mode)
            if drift:
                self.rows[102][drift[0]] = drift[1]
            return [102]

        actual.children = children

        def owner(entry):
            self.owner = actual(entry)
            self.owner.admit(dict(self.rows[101]))
            if mode == 'missing-fd':
                self.owner.rows[102] = dict(self.rows[102])
            elif mode != 'foreign':
                self.owner.admit(dict(self.rows[102]))
            if mode == 'unknown-group':
                self.rows[103] = dict(pid=103, birth='12', parent=7, group=101,
                                      session=101, uid=99)
            return self.owner

        scope['_OwnedStop'] = owner
        return scope

    def assert_closed(self):
        self.assertEqual(sorted(self.closed), sorted(self.fd_roles))
        self.assertEqual(len(self.closed), len(set(self.closed)))
        self.assertLessEqual(self.clock, 3.0)

    def refuse(self, mode, category):
        actual = self.setup_case(mode)
        with self.assertRaisesRegex(RuntimeError, category):
            actual['stop']()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.registry.data, self.original)
        self.assert_closed()

    def test_known_same_birth_reparent_retires_pinned_child_and_proves_group_absence(self):
        actual = self.setup_case('known')
        actual['stop']()
        self.assertEqual(self.rows, {})
        self.assertEqual(json.loads(self.registry.data), {})
        self.assertEqual(self.sent, [(102, 15)])
        self.assert_closed()

    def test_original_stable_child_retires_via_pinned_term(self):
        actual = self.setup_case('stable')
        actual['stop']()
        self.assertEqual(self.rows, {})
        self.assertEqual(json.loads(self.registry.data), {})
        self.assertEqual(self.sent, [(102, 15), (101, 15)])
        self.assert_closed()

    def test_foreign_unadmitted_child_is_refused(self):
        self.refuse('foreign', 'ancestry changed')
        self.assertNotIn(102, self.owner.rows)

    def test_known_row_without_pinned_descriptor_is_refused(self):
        self.refuse('missing-fd', 'ancestry changed')
        self.assertNotIn(102, self.owner.descriptors)

    def test_reused_child_birth_is_refused(self):
        self.refuse('reused', 'identity changed')

    def test_changed_child_uid_is_refused(self):
        self.refuse('uid', 'ownership changed')

    def test_changed_child_group_is_refused(self):
        self.refuse('group', 'identity changed')

    def test_changed_child_session_is_refused(self):
        self.refuse('session', 'identity changed')

    def test_unattributed_surviving_group_is_not_declared_retired(self):
        actual = self.setup_case('unknown-group')
        with self.assertRaisesRegex(RuntimeError, 'retirement is unproven'):
            actual['stop']()
        self.assertEqual(self.registry.data, self.original)
        self.assertEqual(self.sent, [(102, 15)])
        self.assertIn(103, self.rows)
        self.assertEqual(self.clock, 3.0)
        self.assert_closed()


if __name__ == '__main__':
    unittest.main(verbosity=2)
