"""Общий заголовок для предварительных запусков: версия кода, параметры, окружение."""
import sys, os, hashlib, platform
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def header(title, **params):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    md5 = lambda f: hashlib.md5(open(os.path.join(root, f), 'rb').read()).hexdigest()[:10]
    print("# " + title)
    print("# ПРЕДВАРИТЕЛЬНЫЙ ЗАПУСК (исследовательский, вне протокола v1.3). Сети seed 2026, уже использованные в основной серии.")
    print("# Python %s, NumPy %s | md5: engine.py %s, contagion.py %s" % (platform.python_version(), np.__version__, md5('engine.py'), md5('contagion.py')))
    print("# параметры: " + ", ".join("%s=%s" % kv for kv in params.items()))
