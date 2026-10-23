#!/usr/bin/env python3
"""Exercise harness durability/signal cleanup with real disposable children, no emulator."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from game_smoke import HarnessInterrupted, recorded_run

class RunRecordingTest(unittest.TestCase):
    def test_normal_exit_and_peak_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            with recorded_run(base, {'eboot_sha256':'fixture','resolution':'1280x720'}) as run:
                child=subprocess.Popen([sys.executable,'-c','pass'],start_new_session=True)
                run.processes.append(child);run.proc=child
                run.peak=123456
                run.checkpoint()
                progress=json.loads((base/'run-progress.json').read_text())
                self.assertEqual(progress['peak_rss_bytes'],123456)
                self.assertEqual(progress['eboot_sha256'],'fixture')
                child.wait(timeout=5)
            result=json.loads((base/'run.json').read_text())
            self.assertEqual(result['exit_code'],0)
            self.assertFalse(result['interrupted'])
            self.assertFalse(result['timed_out'])
            self.assertEqual(result['cleanup_errors'],[])

    def test_sigterm_unknown_guest_exit_and_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            # An unrelated session must survive cleanup of our registered child.
            unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
            try:
                with self.assertRaises(HarnessInterrupted):
                    with recorded_run(base, {'eboot_sha256':'interrupted'}) as run:
                        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
                        run.processes.append(child);run.proc=child
                        run.peak=456789;run.checkpoint()
                        os.kill(os.getpid(),signal.SIGTERM)
                        run.check_interrupted()
                result=json.loads((base/'run.json').read_text())
                self.assertTrue(result['interrupted'])
                self.assertEqual(result['interrupt_signal'],signal.SIGTERM)
                self.assertIsNone(result['exit_code'])
                self.assertFalse(result['timed_out'])
                self.assertEqual(result['peak_rss_bytes'],456789)
                self.assertEqual(child.poll(),-signal.SIGTERM)
                self.assertEqual(result['cleanup_exit_code'],-signal.SIGTERM)
                self.assertEqual(json.loads((base/'run-progress.json').read_text()),result)
                self.assertIsNone(unrelated.poll())
                self.assertFalse((base/'run.json.tmp').exists())
            finally:
                unrelated.terminate();unrelated.wait(timeout=5)

if __name__=='__main__':unittest.main()
