from pathlib import Path
import os
import sys

from utils import semantic_layer

SCHEMA_PATH = os.environ.get('SEMANTIC_SCHEMA_PATH', 'metricmind_schema.json')
try:
    p = Path(SCHEMA_PATH)
    resolved = p.resolve()
except Exception:
    p = Path(SCHEMA_PATH)
    resolved = p

print(f"Resolved semantic schema path: {resolved}")
parent = resolved.parent
print(f"Parent directory: {parent}")

# Attempt to create parent dir if it doesn't exist
try:
    parent.mkdir(parents=True, exist_ok=True)
    print(f"Ensured parent dir exists: {parent}")
except Exception as e:
    print(f"Failed to ensure parent dir: {e}")

# Attempt a safe write (do not overwrite existing schema file)
test_file = resolved.with_suffix(resolved.suffix + '.testwrite') if resolved.suffix else Path(str(resolved) + '.testwrite')
try:
    test_file.write_text('{"ok": true}', encoding='utf-8')
    print(f"Wrote test file: {test_file}")
    # cleanup
    test_file.unlink()
    print("Test file removed.")
except Exception as e:
    print(f"Failed to write test file at {test_file}: {e}")
    sys.exit(2)

print('Test complete.')
