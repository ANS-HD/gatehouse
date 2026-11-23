import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class BackupTests(unittest.TestCase):
    def test_backup_preserves_following_commands_on_ssh_stdin(self) -> None:
        script = Path(__file__).resolve().parents[2] / "deploy" / "backup.sh"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            (project / ".env").write_text("SESSION_SECRET=test-only\n")
            binaries = root / "bin"
            binaries.mkdir()
            docker = binaries / "docker"
            docker.write_text(
                f"#!{sys.executable}\n" + textwrap.dedent("""\
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                if args[:2] == ['compose', 'exec']:
                    # Compose exec without -i=false reads from its caller,
                    # even when the command itself does not use stdin.
                    sys.stdin.read()
                elif args[:2] == ['compose', 'cp']:
                    Path(args[-1]).write_bytes(b'test database backup')
                else:
                    raise SystemExit('Unexpected Docker command')
                """)
            )
            docker.chmod(0o700)
            environment = {**os.environ, "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}"}
            result = subprocess.run(
                ["sh", "-s"],
                input=f'set -eu\n"{script}" "{project}" "{root / "backups"}"\n'
                'printf "DEPLOYMENT_CONTINUES\\n"\n',
                capture_output=True,
                text=True,
                env=environment,
                timeout=10,
                check=True,
            )
            self.assertIn("DEPLOYMENT_CONTINUES", result.stdout)
            self.assertEqual(len(list((root / "backups").glob("*.db"))), 1)
