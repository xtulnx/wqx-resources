"""No downloaded code is executed. Tests use synthetic files in temporary dirs."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import resources


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_root, self.old_local = resources.ROOT, resources.LOCAL
        self.addCleanup(self.restore)
        resources.ROOT = Path(self.temp.name)
        resources.LOCAL = resources.ROOT / '.local'
        self.roms = resources.ROOT / 'source-roms'
        self.programs = resources.ROOT / 'source-programs'
        self.roms.mkdir()
        self.programs.mkdir()
        (self.roms / 'nc1020.rom').write_bytes(b'fake-rom-for-tests')
        (self.roms / 'nc1020.state').write_bytes(b'private-state')
        (self.programs / 'GvBasic').mkdir()
        (self.programs / 'GvBasic/sample.bas').write_bytes(b'fake-basic-for-tests')
        (self.programs / 'GvBasic/copy.bas').write_bytes(b'fake-basic-for-tests')
        (self.programs / 'unknown.zip').write_bytes(b'not-an-archive')
        with contextlib.redirect_stdout(io.StringIO()):
            resources.intake(SimpleNamespace(roms=str(self.roms), collection=str(self.programs)))
        (resources.ROOT / 'review/entries').mkdir(parents=True)

    def restore(self):
        resources.ROOT, resources.LOCAL = self.old_root, self.old_local

    def test_unknown_resources_never_exported(self):
        with contextlib.redirect_stdout(io.StringIO()):
            resources.build(SimpleNamespace(export=True))
        self.assertEqual(resources.read(resources.ROOT / 'catalog.json')['categories'], [])
        self.assertEqual([p.name for p in (resources.ROOT / 'dist').iterdir()], ['catalog.json'])

    def test_intake_deduplicates_and_excludes_state_archive(self):
        summary = resources.read(resources.LOCAL / 'summary.json')
        self.assertEqual(summary['files'], 3)
        self.assertEqual(summary['uniqueObjects'], 2)
        self.assertEqual(summary['skippedFiles'], 2)
        self.assertEqual((self.roms / 'nc1020.state').read_bytes(), b'private-state')

    def test_kernel_mapping_and_unidentified_programs(self):
        for name in ['35.nor', '35.nand', '35.nand0', 'epc50.nor', '41cam.nand']:
            (self.roms / name).write_bytes(name.encode())
        (self.programs / 'ambiguous.bin').write_bytes(b'unknown')
        (self.programs / 'GvBasic/unrelated.bin').write_bytes(b'not-basic')
        with contextlib.redirect_stdout(io.StringIO()):
            resources.intake(SimpleNamespace(roms=str(self.roms), collection=str(self.programs)))
        records = list(resources.iter_records(resources.LOCAL, resources.LOCAL / 'inventory.json'))
        kernels = [r for r in records if r['classification'] == 'nc2000-nc2600-kernels']
        self.assertEqual(len(kernels), 3)
        sun = next(r for r in kernels if r['author'] == 'Sun')
        self.assertEqual(sun['modelHints'], ['nc2000', 'nc2600'])
        self.assertEqual({f['role'] for f in sun['files']}, {'nor', 'nand'})
        self.assertFalse(any(f['role'] == 'nand0' for r in records for f in r['files']))
        self.assertFalse(any(r['title'] in {'ambiguous', 'unrelated'} for r in records))

    def test_partitioned_indexes_are_bounded(self):
        for i in range(70):
            (self.programs / f'GvBasic/example-{i}.bas').write_bytes(str(i).encode())
        with contextlib.redirect_stdout(io.StringIO()):
            resources.intake(SimpleNamespace(roms=str(self.roms), collection=str(self.programs)))
        records = list(resources.iter_records(resources.LOCAL, resources.LOCAL / 'inventory.json'))
        self.assertEqual(len(records), 73)
        for p in (resources.LOCAL / 'inventory').rglob('pages/*.json'):
            self.assertLessEqual(len(resources.read(p)['resources']), 25)
        self.assertNotIn('resources', resources.read(resources.LOCAL / 'inventory.json'))

    def approval(self):
        c = list(resources.iter_records(resources.LOCAL, resources.LOCAL / 'inventory.json'))[0]
        f = c['files'][0]
        evidence = 'licenses/evidence/synthetic.md'
        path = resources.ROOT / evidence
        path.parent.mkdir(parents=True)
        path.write_text('Synthetic test evidence only')
        return {'status': 'approved', 'candidateId': c['id'], 'id': 'synthetic-resource',
                'title': 'Synthetic', 'version': '1', 'author': 'Test', 'license': 'MIT',
                'evidence': evidence, 'models': ['nc1020'], 'compatibilityNotes': 'test',
                'usage': 'test', 'description': '示例简介', 'logo': 'previews/example.webp',
                'screenshots': ['previews/screen.webp'], 'files': [{'sha256': f['sha256'],
                'path': 'releases/download/resources-current/' + f['sha256'] + '.' + f['role']}]}

    def test_approved_export_has_no_local_paths(self):
        a = self.approval()
        resources.write(resources.ROOT / 'review/entries/firmware/synthetic.json', a)
        with contextlib.redirect_stdout(io.StringIO()):
            resources.build(SimpleNamespace(export=True))
        catalog = (resources.ROOT / 'catalog.json').read_text()
        self.assertNotIn(self.temp.name, catalog)
        self.assertNotIn('candidateId', catalog)
        self.assertNotIn('.local', catalog)
        c = list(resources.iter_records(resources.ROOT, resources.ROOT / 'catalog.json'))[0]
        self.assertEqual(len(c['files']), 1)
        self.assertEqual(c['description'], '示例简介')
        self.assertEqual(c['logo'], 'previews/example.webp')
        self.assertNotIn('url', c['files'][0])
        payloads = [p for p in (resources.ROOT / 'dist/payloads').rglob('*') if p.is_file()]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(resources.digest(payloads[0]), c['files'][0]['sha256'])

    def test_unverified_publication_is_not_authorization(self):
        a = self.approval()
        a.update(status='maintainer-published-unverified', rightsStatus='unverified',
                 publicationDecision='Synthetic test maintainer decision', models=[],
                 license='授权未确认', evidence='docs/DISCLAIMER.md')
        resources.write(resources.ROOT / 'review/entries/firmware/synthetic.json', a)
        with self.assertRaises(ValueError):
            resources.build(SimpleNamespace(export=False))
        p = resources.ROOT / 'docs/DISCLAIMER.md'
        p.parent.mkdir(); p.write_text('Synthetic disclaimer; not authorization')
        with contextlib.redirect_stdout(io.StringIO()):
            resources.build(SimpleNamespace(export=False))
        record = list(resources.iter_records(resources.ROOT, resources.ROOT / 'catalog.json'))[0]
        self.assertEqual(record['rightsStatus'], 'unverified')
        self.assertEqual(record['license'], '授权未确认')
        self.assertEqual(record['models'], [])

    def test_absolute_and_traversal_paths_are_rejected(self):
        for path in ['https://example.org/a.bin', '../a.bin', '/a.bin', 'a/%2e%2e/b', 'a\\b']:
            with self.assertRaises(ValueError):
                resources.relative_path(path)
        self.assertEqual(resources.relative_path('assets/中文.bin'), 'assets/中文.bin')

    def test_missing_evidence_or_tampering_blocks_publication(self):
        a = self.approval()
        resources.write(resources.ROOT / 'review/entries/firmware/synthetic.json', a)
        evidence = resources.ROOT / a['evidence']
        evidence.unlink()
        with self.assertRaises(ValueError):
            resources.build(SimpleNamespace(export=True))
        self.assertFalse((resources.ROOT / 'dist').exists())
        evidence.write_text('Synthetic evidence')
        c = list(resources.iter_records(resources.LOCAL, resources.LOCAL / 'inventory.json'))[0]
        (resources.ROOT / c['files'][0]['object']).write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            resources.build(SimpleNamespace(export=True))
        self.assertFalse((resources.ROOT / 'dist').exists())


if __name__ == '__main__':
    unittest.main()
