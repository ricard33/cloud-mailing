import os
import sys

CUR_DIR = os.path.dirname(os.path.realpath(__file__))
CM_DIR = os.path.realpath(os.path.join(CUR_DIR, '..'))

if CM_DIR not in sys.path:
    sys.path.append(CM_DIR)
