"""SkyScope starts here. The program itself is in src/ (since 1.12.0); this file only starts src/skyscope.py, so
every way SkyScope was already started keeps working: the Raspberry Pi's autostart (skyscope.desktop), the Mac's
launch agent and the Windows runner all name this file, as does "python3 skyscope.py" by hand.
Designed and Created by Project Moon Pi.
"""
import runpy
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))
sys.argv[0] = str(SRC / "skyscope.py")
runpy.run_path(str(SRC / "skyscope.py"), run_name="__main__")
