"""Identity overlap checks shared by batch selection and the update pipeline.

A registry sablename that contains a program-list name is very likely the same
physical project under its official business name, which the zone-token pair
detector cannot see. Such a candidate is quarantined, never merged automatically.
"""
from services.development_official import compact

MIN_PROGRAM_NAME = 3


def program_identities(projects):
    """(district, compacted name) published by a program list, not the registry."""
    return sorted({(p['location']['district'], compact(p['identity']['official_project_name']))
                   for p in projects if not p['classification']['official_registry_row']
                   and len(compact(p['identity']['official_project_name'])) >= MIN_PROGRAM_NAME})


def overlaps(district, project_name, identities):
    name = compact(project_name)
    return [{'district': other, 'program_name': program} for other, program in identities
            if other == district and program and program in name and program != name]


def latent_overlap(project, identities):
    return overlaps(project['location']['district'],
                    project['identity']['official_project_name'], identities)


def record_overlap(record, identities):
    """Same check against a raw collected record, before it is ever ingested."""
    return overlaps(record.get('sigungu'), record.get('project_name') or '', identities)
