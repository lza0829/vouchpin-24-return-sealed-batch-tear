import os
import sys
import tempfile
from pathlib import Path

# 必须在任何 app 模块导入前钉死数据目录（config 在 import 时定型 DB_PATH）
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="vouchpin-test-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
