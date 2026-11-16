import os
import sys
from pathlib import Path

os.environ.setdefault("OSL_API_TOKEN", "test-token-with-at-least-32-characters")
os.environ.setdefault("COLLECTOR_API_TOKEN", "test-collector-token-with-at-least-32-chars")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

sys.path.insert(0, str(Path(__file__).parents[1] / "apps" / "api"))
