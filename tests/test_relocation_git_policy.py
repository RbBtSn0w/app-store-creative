"""Actual Git ignore and index state gate relocation staging writes."""
from pathlib import Path
import shutil
import subprocess
import unittest
import test_relocation_lifecycle as fixtures


class RelocationGitTests(unittest.TestCase):
    setUp = fixtures.RelocationTests.setUp
    source = fixtures.RelocationTests.source
    targets = fixtures.RelocationTests.targets

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def plan(self):
        self.git('init', '--quiet')
        self.source()
        return self.store.plan_relocation(self.targets())

    def test_unignored_staging_is_rejected_before_copy(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, 'ignored'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        self.assertEqual(list(self.root.glob('.creative-relocate-*')), [])
        self.assertFalse((self.root / '.gitignore').exists())

    def test_exact_suggestions_preserve_user_rules_and_allow_prepare(self):
        plan = self.plan()
        rules = self.root / '.gitignore'; rules.write_text('user-cache/\n')
        policy = self.store.relocation_git_policy(plan['id'])
        self.assertFalse(policy['applied'])
        self.assertEqual(rules.read_text(), 'user-cache/\n')
        rules.write_text(rules.read_text() + '\n'.join(policy['gitignore']) + '\n')
        self.assertEqual(self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')['status'], 'PREPARED')

    def test_negated_rule_does_not_bypass_actual_ignore_gate(self):
        plan = self.plan()
        policy = self.store.relocation_git_policy(plan['id'])
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n!.creative-relocate-*/\n')
        with self.assertRaisesRegex(ValueError, 'ignored'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')

    def test_tracked_staging_is_rejected_even_with_ignore_rule(self):
        plan = self.plan()
        policy = self.store.relocation_git_policy(plan['id'])
        stage = Path(next(iter(policy['staging'].values())))
        stage.mkdir(); (stage / 'sentinel').write_text('tracked')
        self.git('add', str(stage.relative_to(self.root)))
        shutil.rmtree(stage)
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        with self.assertRaisesRegex(ValueError, 'tracked'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')

    def test_tracked_path_with_glob_characters_cannot_escape_index_check(self):
        self.git('init', '--quiet'); self.source()
        target = {**self.targets(), 'workspaceRoot': 'target [set]/new work'}
        plan = self.store.plan_relocation(target)
        policy = self.store.relocation_git_policy(plan['id'])
        stage = Path(policy['staging']['workspace'])
        stage.mkdir(parents=True); (stage / 'sentinel').write_text('tracked')
        self.git('--literal-pathspecs', 'add', str(stage.relative_to(self.root)))
        shutil.rmtree(stage)
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        with self.assertRaisesRegex(ValueError, 'tracked'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')

    def test_similarly_named_tracked_directory_does_not_block_exact_staging_path(self):
        self.git('init', '--quiet'); self.source()
        plan = self.store.plan_relocation({**self.targets(), 'workspaceRoot': 'target [set]/new work'})
        policy = self.store.relocation_git_policy(plan['id'])
        actual = Path(policy['staging']['workspace'])
        other = self.root / 'target s' / actual.name
        other.mkdir(parents=True); (other / 'sentinel').write_text('unrelated tracked bytes')
        self.git('--literal-pathspecs', 'add', str(other.relative_to(self.root)))
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        self.assertEqual(self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')['status'], 'PREPARED')

    def test_storage_control_characters_cannot_inject_ignore_lines(self):
        self.source()
        with self.assertRaisesRegex(ValueError, 'Invalid storage'):
            self.store.plan_relocation({**self.targets(), 'workspaceRoot': 'new\nwork'})

    def test_each_target_repository_needs_its_own_real_ignore_rules(self):
        self.git('init', '--quiet'); self.source()
        other = self.root / 'other-repo'; other.mkdir()
        subprocess.check_call(['git', '-C', str(other), 'init', '--quiet'])
        plan = self.store.plan_relocation({**self.targets(), 'objectRoot': 'other-repo/new objects'})
        policy = self.store.relocation_git_policy(plan['id'])
        self.assertEqual({entry['root'] for entry in policy['repositories']}, {str(self.root), str(other)})
        own = next(entry for entry in policy['repositories'] if entry['root'] == str(self.root))
        (self.root / '.gitignore').write_text('\n'.join(own['patterns']) + '\n')
        with self.assertRaisesRegex(ValueError, 'ignored'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        additional = next(entry for entry in policy['repositories'] if entry['root'] == str(other))
        (other / '.gitignore').write_text('\n'.join(additional['patterns']) + '\n')
        self.assertEqual(self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')['status'], 'PREPARED')

    def test_prepared_retry_rechecks_current_git_rules(self):
        plan = self.plan(); policy = self.store.relocation_git_policy(plan['id'])
        rules = self.root / '.gitignore'; rules.write_text('\n'.join(policy['gitignore']) + '\n')
        self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        rules.write_text('user-cache/\n')
        with self.assertRaisesRegex(ValueError, 'ignored'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Retry')
