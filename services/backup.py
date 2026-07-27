import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from config import settings

def run_backup(project_id: str):
    try:
        data_dir = Path(settings.DATA_DIR)
        backup_dir = data_dir / "backups" / project_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. Zip living_docs for this project
        living_docs_dir = Path(settings.LIVING_DOCS_DIR) / project_id
        if living_docs_dir.exists():
            zip_path = backup_dir / f"living_docs_backup_{timestamp}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(living_docs_dir):
                    # Only backup living docs, skip versions or backups directory if nested
                    if "versions" in root or "backups" in root:
                        continue
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(living_docs_dir)
                        zipf.write(file_path, arcname)
                        
            # Keep only the last 5 backup zip files to save disk space
            zip_files = sorted(backup_dir.glob("*.zip"), key=lambda x: x.stat().st_mtime)
            while len(zip_files) > 5:
                zip_files[0].unlink()
                zip_files.pop(0)
                
            print(f"[Backup] Successfully created backup living_docs_backup_{timestamp}.zip for project {project_id}")
            return True
    except Exception as e:
        print(f"[Backup ERROR] Backup failed for project {project_id}: {e}")
        return False
