try:
    import src.main

    src.main.run()
except Exception as e:
    print("Error in main.py")
    import sys

    sys.print_exception(e)  # type: ignore[attr-defined]
