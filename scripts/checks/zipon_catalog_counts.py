"""패키지된 공식 단계 카탈로그의 건수. DB·네트워크 접근 없음(읽기 전용)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.development_stage import catalog, stage_view  # noqa: E402

projects = catalog()
usable = [pid for pid, entry in projects.items() if stage_view(entry)]
with_milestones = [pid for pid, entry in projects.items() if entry.get('milestones')]
print(f'catalog_projects={len(projects)} usable_stage_view={len(usable)} with_milestones={len(with_milestones)}')
