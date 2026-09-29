import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from qc_inspector.main import _legal_document_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_main_file_imports_without_editable_install_path(self):
        entry = PROJECT_ROOT / 'src' / 'qc_inspector' / 'main.py'
        code = '''
import runpy
import sys
from pathlib import Path
entry = Path(sys.argv[1]).resolve()
sys.path = [p for p in sys.path if p and Path(p).resolve() not in
            (entry.parents[2], entry.parents[1])]
namespace = runpy.run_path(str(entry), run_name='direct_launch_probe')
assert callable(namespace['main'])
import qc_inspector
assert Path(qc_inspector.__file__).resolve().parent == entry.parent
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, '-c', code, str(entry)], cwd=directory,
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installed_distribution_exposes_legal_documents(self):
        paths = {
            name: Path(_legal_document_path(name))
            for name in ('LICENSE', 'NOTICE.md', 'THIRD_PARTY_NOTICES.md')
        }

        self.assertTrue(all(path.is_file() for path in paths.values()))
        self.assertIn('GNU AFFERO GENERAL PUBLIC LICENSE',
                      paths['LICENSE'].read_text(encoding='utf-8'))
        self.assertIn('PyMuPDF',
                      paths['THIRD_PARTY_NOTICES.md'].read_text(encoding='utf-8'))

    def test_installed_distribution_exposes_console_entry_point(self):
        distribution = importlib.metadata.distribution('qc-inspector')
        scripts = {
            entry.name: entry.value
            for entry in distribution.entry_points
            if entry.group == 'console_scripts'
        }
        self.assertEqual(scripts['qc-inspector'], 'qc_inspector.main:main')

    def test_distribution_contains_third_party_license_texts(self):
        distribution = importlib.metadata.distribution('qc-inspector')
        license_names = {
            entry.name
            for entry in distribution.files or ()
            if 'licenses' in entry.parts
        }

        self.assertTrue({
            'PyQt5-GPL-3.0.txt',
            'Qt-LGPL-3.0.txt',
            'PyQt5-sip-BSD-2-Clause.txt',
            'PyMuPDF-AGPL-3.0.txt',
            'ReportLab-BSD-3-Clause.txt',
            'Pillow-and-bundled-libraries.txt',
            'charset-normalizer-MIT.txt',
            'PyInstaller-GPL-2.0-or-later-with-bootloader-exception.txt',
        }.issubset(license_names))

    def test_renamed_source_tree_imports_and_uses_user_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'qc-inspector-release-archive-1.3.5'
            shutil.copytree(PROJECT_ROOT / 'src', checkout / 'src')
            xdg_config = root / 'config'
            xdg_data = root / 'data'
            environment = dict(os.environ)
            environment.update({
                'PYTHONPATH': str(checkout / 'src'),
                'XDG_CONFIG_HOME': str(xdg_config),
                'XDG_DATA_HOME': str(xdg_data),
            })
            code = (
                'import json; '
                'from qc_inspector.core.app_config import '
                'load_or_create_config, get_config_path; '
                'cfg = load_or_create_config(); '
                'print(json.dumps({"config": get_config_path(), '
                '"db": cfg["db_path"], "pdf": cfg["pdf_dir"]}))'
            )

            result = subprocess.run(
                [sys.executable, '-c', code],
                cwd=checkout,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            paths = json.loads(result.stdout)
            self.assertEqual(
                paths['config'],
                str(xdg_config / 'qc-inspector' / 'qc_inspector.conf'),
            )
            self.assertEqual(
                paths['db'],
                str(xdg_data / 'qc-inspector' / 'qc_database.sqlite'),
            )
            self.assertEqual(
                paths['pdf'],
                str(xdg_data / 'qc-inspector' / 'pdf'),
            )
