"""Exercise the same layout/state helper compiled into the GPU renderer."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PreviewLayoutTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'C++ compiler unavailable')
    def test_native_layout_and_state(self):
        here = Path(__file__).parent
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary)/'preview_test'
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(here.parents[1]/'kernels/srv/gpu/3dsrv'),
                            str(here/'test_preview.cpp'), '-o', str(binary)], check=True)
            subprocess.run([str(binary), str(Path(temporary)/'preview.state')], check=True)
