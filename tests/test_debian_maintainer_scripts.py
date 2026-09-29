import grp
import os
import pwd
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'Richiede permessi POSIX')
class DebianMaintainerScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_dir = self.root / 'etc' / 'qc-inspector'
        self.var_root = self.root / 'var' / 'qc-inspector'
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.group = grp.getgrgid(os.getgid()).gr_name

    def script(self, name):
        source = (PROJECT_ROOT / 'build_deb.sh').read_text()
        match = re.search(
            rf'cat > "\$PKG_DIR/DEBIAN/{name}" <<\'EOF\'\n(.*?)\nEOF',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match, f'Script {name} non trovato')
        script = match.group(1)
        replacements = {
            'CONFIG_DIR="/etc/qc-inspector"':
                f'CONFIG_DIR="{self.config_dir}"',
            'PDF_DIR="/var/qc-inspector/pdf"':
                f'PDF_DIR="{self.var_root / "pdf"}"',
            'VAR_ROOT="/var/qc-inspector"':
                f'VAR_ROOT="{self.var_root}"',
            'GROUP_NAME="qc-inspector"':
                f'GROUP_NAME="{self.group}"',
            '== "0"': f'== "{os.getuid()}"',
            'root:root': f'{self.user}:{self.group}',
            '-o root': f'-o {self.user}',
            '-g root': f'-g {self.group}',
        }
        for old, new in replacements.items():
            script = script.replace(old, new)
        path = self.root / name
        path.write_text(script)
        path.chmod(0o700)
        return path

    def run_script(self, name, *args):
        return subprocess.run(
            [str(self.script(name)), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_preinst_rejects_config_symlink_without_touching_target(self):
        self.config_dir.mkdir(parents=True)
        self.config_dir.chmod(0o2775)
        target = self.root / 'foreign-config'
        target.write_text('unchanged')
        target.chmod(0o600)
        (self.config_dir / 'qc_inspector.conf').symlink_to(target)

        result = self.run_script('preinst', 'upgrade')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('percorso non sicuro', result.stderr)
        self.assertEqual(target.read_text(), 'unchanged')
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_postinst_rejects_db_symlink_without_touching_target(self):
        self.config_dir.mkdir(parents=True)
        self.var_root.mkdir(parents=True)
        (self.var_root / 'pdf').mkdir()
        target = self.root / 'foreign-database'
        target.write_text('unchanged')
        target.chmod(0o600)
        (self.var_root / 'qc_database.sqlite').symlink_to(target)

        result = self.run_script('postinst', 'configure', '1.3.5')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('percorso non sicuro', result.stderr)
        self.assertEqual(target.read_text(), 'unchanged')
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.var_root.stat().st_mode), 0o2775)

    def test_postinst_rejects_pdf_directory_symlink_without_recursion(self):
        self.config_dir.mkdir(parents=True)
        self.var_root.mkdir(parents=True)
        target_dir = self.root / 'foreign-directory'
        target_dir.mkdir()
        target_file = target_dir / 'private'
        target_file.write_text('unchanged')
        target_file.chmod(0o600)
        (self.var_root / 'pdf').symlink_to(target_dir, target_is_directory=True)

        result = self.run_script('postinst', 'configure', '1.3.5')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('percorso non sicuro', result.stderr)
        self.assertEqual(target_file.read_text(), 'unchanged')
        self.assertEqual(stat.S_IMODE(target_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.var_root.stat().st_mode), 0o2775)

    def test_regular_upgrade_preserves_database_and_creates_options(self):
        self.config_dir.mkdir(parents=True)
        config = self.config_dir / 'qc_inspector.conf'
        config.write_text('db_path = /var/qc-inspector/qc_database.sqlite\n')
        self.var_root.mkdir(parents=True)
        (self.var_root / 'pdf').mkdir()
        database = self.var_root / 'qc_database.sqlite'
        database.write_bytes(b'original database')
        database.chmod(0o660)

        preinst = self.run_script('preinst', 'upgrade')
        postinst = self.run_script('postinst', 'configure', '1.3.5')

        self.assertEqual(preinst.returncode, 0, preinst.stderr)
        self.assertEqual(postinst.returncode, 0, postinst.stderr)
        self.assertEqual(database.read_bytes(), b'original database')
        self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o660)
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o644)
        options = self.var_root / 'qc_inspector.options.conf'
        self.assertTrue(options.is_file())
        self.assertEqual(stat.S_IMODE(options.stat().st_mode), 0o664)
