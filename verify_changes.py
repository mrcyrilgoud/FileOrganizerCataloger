import os
import sys

# Add backend to sys.path to allow imports
sys.path.append(os.path.abspath("backend"))

from backend.analyzer import FileAnalyzer
from backend.actions import delete_file_safely

# Setup
test_dir = "test_verification"
os.makedirs(test_dir, exist_ok=True)

# 1. Verify Backup Codes
print("\n--- Testing Backup Code Detection ---")
analyzer = FileAnalyzer()
backup_file = os.path.join(test_dir, "carta-backup-codes.txt")
with open(backup_file, "w") as f:
    f.write("test content")

res = analyzer.analyze_file(backup_file)
print(f"File: {res['filename']}")
print(f"Importance: {res['importance']}")
print(f"Reasons: {res['reasons']}")
# New Check: Size
print(f"Size Bytes: {res.get('size_bytes')}")

if res['importance'] == "Very Important" and "Filename indicates backup codes" in res['reasons']:
    print("✅ Analyzer Check Passed")
else:
    print("❌ Analyzer Check Failed")

if 'size_bytes' in res and res['size_bytes'] > 0:
     print("✅ Size Check Passed")
else:
     print("❌ Size Check Failed")


# 2. Verify Safe Deletion
print("\n--- Testing Safe Deletion ---")
delete_file_path = os.path.join(test_dir, "to_be_deleted.txt")
with open(delete_file_path, "w") as f:
    f.write("delete me")

print(f"File created at: {delete_file_path}")
success, msg = delete_file_safely(delete_file_path)
print(f"Deletion result: {success}, {msg}")

if not os.path.exists(delete_file_path):
    print("✅ File removed from location (Assumed moved to trash)")
else:
    print("❌ File still exists at location")

# 3. Verify Open Endpoint Logic (Mocking open)
# We can't easily test subprocess.call('open') without actually opening a window,
# but we can verify the function exists and validates path.
print("\n--- Testing Open Endpoint Logic ---")
from backend.main import open_file, OpenRequest
from fastapi import HTTPException
try:
    # Test non-existent
    try:
        open_file(OpenRequest(file_path="non_existent_file.txt"))
        print("❌ Should have raised 404")
    except HTTPException as e:
        if e.status_code == 404:
            print("✅ Correctly returned 404 for missing file")
        else:
            print(f"❌ Wrong status code: {e.status_code}")
except Exception as e:
    print(f"❌ Error during open test: {e}")

# Cleanup
try:
    os.remove(backup_file)
    os.rmdir(test_dir)
except:
    pass
