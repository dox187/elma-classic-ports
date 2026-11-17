"""Reject linked images that place code or startup outside ROM windows."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build import validate_linked_layout


class LinkedLayout(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'layout.noi'
        # All startup bytes fit, with the final byte at 0x3fff.
        self.areas={'_CODE':(0x200,0x3000),'_HOME':(0x3200,0xdf1),
                    '_INITIALIZER':(0x3ff1,2),'_GSINIT':(0x3ff3,12),
                    '_GSFINAL':(0x3fff,1),'_CODE_5':(0x54000,0x4000)}

    def check(self,mib=8):
        self.path.write_text(''.join(f'DEF s_{name} 0x{start:x}\nDEF l_{name} 0x{size:x}\n'
                                    for name,(start,size) in self.areas.items()))
        return validate_linked_layout(self.path,mib)

    def test_exact_fixed_boundary(self):
        self.assertEqual(self.check(),{'rom0_end':0x4000,'rom0_free_bytes':0})

    def test_startup_byte_beyond_boundary(self):
        self.areas['_GSFINAL']=(0x3fff,2)
        with self.assertRaisesRegex(ValueError,'ROM0 overflow'):self.check()

    def test_observed_library_overflow(self):
        self.areas.update(_CODE=(0x200,0x33b4),_HOME=(0x35b4,0xaaa),
                          _INITIALIZER=(0x405e,2),_GSINIT=(0x4060,12),_GSFINAL=(0x406c,1))
        with self.assertRaisesRegex(ValueError,'ROM0 overflow'):self.check()

    def test_banked_window_overflow(self):
        self.areas['_CODE_5']=(0x54000,0x4001)
        with self.assertRaisesRegex(ValueError,'bank 5'):self.check()

    def test_bank_number_matches_profile(self):
        self.areas['_CODE_256']=(0x1004000,1)
        self.check(8)
        with self.assertRaisesRegex(ValueError,'bank 256'):self.check(4)

    def test_misaddressed_bank(self):
        self.areas['_CODE_5']=(0x44000,1)
        with self.assertRaisesRegex(ValueError,'bank 5'):self.check()

    def test_missing_startup_area(self):
        del self.areas['_GSINIT']
        with self.assertRaisesRegex(ValueError,'Missing linked ROM area'):self.check()


if __name__=='__main__':unittest.main()
