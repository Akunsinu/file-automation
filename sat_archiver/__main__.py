"""Allow running as: python -m sat_archiver"""
import sys

if "--gui" in sys.argv:
    from .gui import run_gui
    run_gui()
else:
    from .main import main
    sys.exit(main())
