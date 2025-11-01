import os
import sys
import runpy


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ui_path = os.path.join(here, "modules", "UI-Sam.py")
    if not os.path.exists(ui_path):
        sys.stderr.write("UI file not found: modules/UI-Sam.py\n")
        sys.exit(1)

    # Ensure project root is on import path for `modules` package imports
    if here not in sys.path:
        sys.path.insert(0, here)

    # Execute the UI script as the main module
    runpy.run_path(ui_path, run_name="__main__")


if __name__ == "__main__":
    main()
