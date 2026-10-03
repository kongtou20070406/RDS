"""Exercise updater acceptance with a real Windows 8.3 temporary root."""
import ctypes
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_update_lean_toolchain as toolchain_tests


@unittest.skipUnless(os.name == "nt", "Windows short-path aliases only")
class WindowsUpdaterFixtureTests(unittest.TestCase):
    def test_apply_acceptance_under_native_short_temp_root(self):
        with tempfile.TemporaryDirectory(prefix="RDS Lean long temporary root ") as parent:
            get_short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
            get_short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
            get_short_path.restype = ctypes.c_uint32
            size = get_short_path(parent, None, 0)
            if not size:
                self.skipTest("Native short path unavailable on this volume")
            buffer = ctypes.create_unicode_buffer(size)
            written = get_short_path(parent, buffer, size)
            self.assertTrue(0 < written < size)
            alias = Path(buffer.value)
            if alias == alias.resolve():
                self.skipTest("8.3 alias creation disabled on this volume")
            self.assertEqual(alias.resolve(), Path(parent).resolve())
            # Keep the actual alias in TemporaryDirectory's returned path, just
            # like RUNNER~1 in the original CI. Run the unchanged apply checks.
            with mock.patch.object(tempfile, "tempdir", str(alias)):
                result = unittest.TestResult()
                case = toolchain_tests.ToolchainUpgradeTests(
                    "test_apply_updates_all_four_bindings_without_build_commit_or_push")
                case.run(result)
            self.assertEqual(result.testsRun, 1)
            self.assertEqual(result.skipped, [])
            self.assertEqual(result.errors, [])
            self.assertEqual(result.failures, [])


if __name__ == "__main__":
    unittest.main()
