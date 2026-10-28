"""Packaging boundaries and browser dispatch without opening a desktop browser."""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build
import launch

sys.path.insert(0,str(build.ROOT))
import app


class PortableBoundaries(unittest.TestCase):
    def test_changed_upstream_bytes_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'archive.zip';path.write_bytes(b'wrong archive')
            with self.assertRaisesRegex(ValueError,'UPSTREAM_DIGEST_MISMATCH'):
                build.download('https://www.python.org/', '0'*64, 100, path)

    def test_archive_traversal_and_duplicate_entries_are_refused(self):
        for names in [('../escape',),('/absolute',),('bad\\member',),('duplicate','duplicate')]:
            with self.subTest(names=names):
                out=io.BytesIO()
                with zipfile.ZipFile(out,'w') as z:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore',UserWarning)
                        for name in names:z.writestr(name.replace('\\','/'),b'fictional')
                with self.assertRaisesRegex(ValueError,'UNEXPECTED_ARCHIVE_MEMBER'):build.members(out.getvalue().replace(b'bad/member',b'bad\\member'))

    def test_browser_dispatch_uses_only_the_new_loopback_server(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'private data'
            with patch.object(sys,'argv',['launch.py','--data-dir',str(data)]), \
                 patch.object(launch,'check_package',return_value={}), \
                 patch.object(app.WorkfloorServer,'serve_forever',side_effect=KeyboardInterrupt), \
                 patch.object(launch.webbrowser,'open',return_value=True) as browser:
                launch.main()
                self.assertRegex(browser.call_args.args[0],r'^http://127\.0\.0\.1:[0-9]+/$')
                self.assertTrue((data/'workfloor.sqlite3').is_file())

    def test_data_inside_application_is_refused_before_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'private data'
            with patch.object(launch,'ROOT',root),patch.object(launch,'check_package',return_value={}), \
                 patch.object(sys,'argv',['launch.py','--data-dir',str(target)]):
                with self.assertRaises(SystemExit) as result:launch.main()
            self.assertEqual(result.exception.code,1);self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
