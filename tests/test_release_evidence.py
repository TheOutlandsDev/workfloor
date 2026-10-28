import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from release_evidence import qualified, JOBS

class EvidenceGate(unittest.TestCase):
    def setUp(self):
        self.source = 'a' * 40
        self.run = dict(head_sha=self.source, event='push', path='.github/workflows/recovery-release.yml', conclusion='success')
        self.jobs = [dict(name=name, conclusion='success') for name in JOBS]

    def test_only_complete_same_source_push_is_reusable(self):
        self.assertTrue(qualified(self.run, self.jobs, self.source))
        for field, wrong in [('head_sha', 'b'*40), ('event', 'pull_request'), ('path', 'other.yml'), ('conclusion', None)]:
            with self.subTest(field=field): self.assertFalse(qualified(dict(self.run, **{field: wrong}), self.jobs, self.source))

    def test_every_platform_and_comparison_must_pass(self):
        for index in range(len(self.jobs)):
            jobs = [dict(j) for j in self.jobs]; jobs[index]['conclusion'] = 'failure'
            self.assertFalse(qualified(self.run, jobs, self.source))
            self.assertFalse(qualified(self.run, self.jobs[:index] + self.jobs[index+1:], self.source))

    def test_current_running_publisher_still_requires_completed_platform_jobs(self):
        running = dict(self.run, conclusion=None)
        self.assertTrue(qualified(running, self.jobs, self.source, require_complete=False))
        self.assertFalse(qualified(running, [], self.source, require_complete=False))

if __name__ == '__main__': unittest.main()
