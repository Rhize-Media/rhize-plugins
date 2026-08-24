#!/usr/bin/python3
# Regression fixture: a .sh file that is actually Python (like the real
# hooks/protect-files.sh). Doctor must check it with py_compile, not bash -n.
import sys
print("ok")
