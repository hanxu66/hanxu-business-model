import importlib.util
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_release', ROOT / 'scripts/build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        shutil.copytree(ROOT / 'skills', self.root / 'skills')
        for name in ('LICENSE', 'INSTALL.md'):
            shutil.copyfile(ROOT / name, self.root / name)
        self.skill = self.root / 'skills' / release.NAME

    def test_installable_archive_is_complete_and_deterministic(self):
        a = Path(self.temp.name) / 'a.zip'
        b = Path(self.temp.name) / 'b.zip'
        release.build(self.root, a)
        release.build(self.root, b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with zipfile.ZipFile(a) as z:
            self.assertIsNone(z.testzip())
            expected = {f'{release.NAME}/{p}' for p in release.SKILL_FILES} | {
                f'{release.NAME}/README.md', f'{release.NAME}/LICENSE'}
            self.assertEqual(set(z.namelist()), expected)
            target = Path(self.temp.name) / 'installed'
            z.extractall(target)
            for p in (target / release.NAME).rglob('*.md'):
                for link in re.findall(r'\]\(([^)]+)\)', p.read_text()):
                    if not link.startswith(('http:', 'https:', '#')):
                        self.assertTrue((p.parent / link).is_file(), (p, link))

    def test_private_file_inside_skill_blocks_build_without_output(self):
        (self.skill / 'client-transcript.md').write_text('private data')
        output = Path(self.temp.name) / 'out.zip'
        with self.assertRaises(ValueError):
            release.build(self.root, output)
        self.assertFalse(output.exists())

    def test_private_file_outside_allowlist_is_never_exported(self):
        (self.root / 'research').mkdir()
        (self.root / 'research/transcript.txt').write_text('private data')
        entries = release.release_entries(self.root)
        self.assertNotIn(b'private data', entries.values())

    def test_symlink_cannot_export_a_private_file(self):
        p = self.skill / 'references/examples.md'
        p.unlink()
        private = Path(self.temp.name) / 'secret.txt'
        private.write_text('private data')
        p.symlink_to(private)
        with self.assertRaises(ValueError):
            release.release_entries(self.root)

    def test_private_path_or_contact_in_allowed_text_blocks_export(self):
        for value in ('/Users/example/private.txt', '13812345678', 'client@example.org',
                      'ghp_' + 'x' * 30, 'github_pat_' + 'x' * 30):
            with self.subTest(value=value):
                (self.skill / 'references/examples.md').write_text(value)
                with self.assertRaises(ValueError):
                    release.release_entries(self.root)

    def test_missing_reference_blocks_export(self):
        (self.skill / 'references/conversation.md').unlink()
        with self.assertRaises(ValueError):
            release.release_entries(self.root)

    def test_existing_release_is_preserved(self):
        out = Path(self.temp.name) / 'existing.zip'
        out.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            release.build(self.root, out)
        self.assertEqual(out.read_bytes(), b'keep')

    def test_output_cannot_pollute_installed_skill(self):
        out = self.skill / 'out.zip'
        with self.assertRaises(ValueError):
            release.build(self.root, out)
        self.assertFalse(out.exists())

    def test_racing_file_is_not_deleted(self):
        out = Path(self.temp.name) / 'race.zip'
        original_open = Path.open

        def racing_open(path, *args, **kwargs):
            if path == out and args and args[0] == 'xb':
                with original_open(out, 'wb') as stream:
                    stream.write(b'created elsewhere')
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', racing_open):
            with self.assertRaises(FileExistsError):
                release.build(self.root, out)
        self.assertEqual(out.read_bytes(), b'created elsewhere')

    def test_repository_relative_markdown_links_resolve(self):
        for p in ROOT.rglob('*.md'):
            if '.git' in p.parts:
                continue
            for link in re.findall(r'\]\(([^)]+)\)', p.read_text()):
                if not link.startswith(('http:', 'https:', '#')):
                    self.assertTrue((p.parent / link).is_file(), (p, link))

    def test_installed_skill_keeps_the_source_license(self):
        self.assertEqual((ROOT / 'LICENSE').read_bytes(),
                         (ROOT / 'skills' / release.NAME / 'LICENSE').read_bytes())


if __name__ == '__main__':
    unittest.main()
