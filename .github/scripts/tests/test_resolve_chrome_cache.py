import importlib.util
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "resolve-chrome-cache.py"
SPEC = importlib.util.spec_from_file_location("resolve_chrome_cache", SOURCE)
assert SPEC and SPEC.loader
resolver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resolver)


class ChromeCacheFaultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "setup-chrome/chromium" / resolver.VERSION / "arm64"
        self.marker = self.cache.with_name("arm64.complete")
        self.probe = patch.object(resolver.subprocess, "run")
        self.mock_probe = self.probe.start()
        self.addCleanup(self.probe.stop)
        self.architecture = patch.object(resolver.platform, "machine", return_value="arm64")
        self.architecture.start()
        self.addCleanup(self.architecture.stop)

    def fixture(self, version=None, executable=False):
        self.cache.mkdir(parents=True)
        self.marker.touch()
        info = self.cache / resolver.APP / "Contents/Info.plist"
        info.parent.mkdir(parents=True)
        info.write_bytes(plistlib.dumps({"CFBundleShortVersionString": version or resolver.VERSION}))
        if executable:
            binary = self.cache / resolver.BINARY
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"Negative-test placeholder; never executed")
            binary.chmod(0o700)

    def rejected(self, message):
        with self.assertRaisesRegex(resolver.CacheError, message):
            resolver.resolve_cache(self.root)
        self.mock_probe.assert_not_called()

    def test_cold_miss_does_not_claim_a_cache_hit(self):
        self.assertIsNone(resolver.resolve_cache(self.root))
        self.mock_probe.assert_not_called()

    def test_existing_directory_without_marker_fails_closed(self):
        self.cache.mkdir(parents=True)
        self.rejected("incomplete")

    def test_marker_without_directory_fails_closed(self):
        self.marker.parent.mkdir(parents=True)
        self.marker.touch()
        self.rejected("incomplete")

    def test_missing_binary_fails_closed(self):
        self.fixture()
        self.rejected("incomplete")

    def test_non_executable_binary_fails_closed(self):
        self.fixture(executable=True)
        (self.cache / resolver.BINARY).chmod(0o600)
        self.rejected("not executable")

    def test_wrong_bundle_version_fails_before_execution(self):
        self.fixture(version="132.0.0.0", executable=True)
        self.rejected("bundle version")

    def test_missing_bundle_metadata_fails_closed(self):
        self.fixture()
        (self.cache / resolver.APP / "Contents/Info.plist").unlink()
        self.rejected("incomplete")

    def test_non_dictionary_bundle_metadata_fails_closed(self):
        self.fixture()
        (self.cache / resolver.APP / "Contents/Info.plist").write_bytes(plistlib.dumps(["invalid structure"]))
        self.rejected("must be a dictionary")

    def test_application_symlink_escape_fails_closed(self):
        self.cache.mkdir(parents=True)
        self.marker.touch()
        outside = self.root / "outside"
        outside.mkdir()
        (self.cache / resolver.APP).symlink_to(outside, target_is_directory=True)
        self.rejected("symbolic link")

    def test_marker_symlink_fails_closed(self):
        self.cache.mkdir(parents=True)
        outside = self.root / "outside-marker"
        outside.touch()
        self.marker.symlink_to(outside)
        self.rejected("symbolic link")

    def test_wrong_actual_version_fails_closed(self):
        self.fixture(executable=True)
        self.mock_probe.return_value = subprocess.CompletedProcess([], 0, "Google Chrome for Testing 132.0.0.0\n", "")
        with self.assertRaisesRegex(resolver.CacheError, "Actual cached Chrome version"):
            resolver.resolve_cache(self.root)

    def test_probe_failure_fails_closed(self):
        self.fixture(executable=True)
        self.mock_probe.side_effect = subprocess.CalledProcessError(1, [])
        with self.assertRaisesRegex(resolver.CacheError, "version probe failed"):
            resolver.resolve_cache(self.root)


if __name__ == "__main__":
    unittest.main()
