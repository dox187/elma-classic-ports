"""Content-based Play menu layout, matching GYUJTEM.CPP and PLAY.CPP.

Reads only the supplied game resource. It does not infer a layout from a
filename, file size or release name. Navigation starts on a fresh player's
Play menu (or after selecting an internal level in state.dat).
"""
import struct

from phys_levels import INTERNAL_LEVELS, Resource, SHAREWARE_LAST


COLLECTIONS = (
    ("Tutorial", "tutorial"),
    ("Stolen Internals by Sla", "stolen"),
    ("Quick & Easy by Sla", "easy"),
    ("Quick & Hard by Sla", "hard"),
)


def resource_layout(path):
    resource = Resource(path)
    counts = []
    for title, prefix in COLLECTIONS:
        count = 0
        while count < 99 and "%s%02d.lev" % (prefix, count + 1) in resource:
            count += 1
        counts.append(count)
    internal = list(INTERNAL_LEVELS)
    if "a17.leb" not in resource and SHAREWARE_LAST in resource:
        internal[internal.index("a17.leb")] = SHAREWARE_LAST
    internal_count = 0
    for name in internal:
        if name not in resource:
            break
        internal_count += 1
    rows = []
    if counts[0]:
        rows.append(COLLECTIONS[0][0])
    rows.append("Original Levels")
    rows.extend(title for (title, _), count in zip(COLLECTIONS[1:], counts[1:]) if count)
    rows.append("External Levels")
    collections = any(counts)
    return {
        "collections": collections,
        "collection_counts": counts,
        "collection_rows": rows if collections else [],
        "internal_count": internal_count,
        "descriptor_slots": next(slots for slots in (150, 3000)
                                 if struct.unpack_from("<i", resource.data, 4 + slots * 24)[0] == Resource.MAGIC),
        "external_down_count": len(rows) - 1 if collections else 0,
        "external_steps": (["DOWN"] * (len(rows) - 1) if collections else ["UP"]) + ["CROSS", "CROSS"],
        "internal_steps": (["DOWN"] * rows.index("Original Levels") + ["CROSS", "CROSS"]
                           if collections else ["CROSS"]),
    }
