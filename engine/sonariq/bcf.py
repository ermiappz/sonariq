"""BCF 2.1 export: one topic per open finding or decision, with the IFC GlobalId selected in the viewpoint."""
from __future__ import annotations

import datetime as dt
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _topic(f: dict, now: str, author: str) -> tuple[str, str, str]:
    tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sonariq/{f['check_key']}/{f['revision']}"))
    vid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sonariq/vp/{tid}"))
    req, meas = f.get("required") or {}, f.get("measured") or {}
    desc = (f"{f['status_word']} · {f['ref']} · {f['location']['label']}. Required {req.get('value')} "
            f"{req.get('unit', '')}, measured {meas.get('value')} {meas.get('unit', '')}. {f.get('summary', '')}")
    if f.get("decision"):
        desc += f" Decision: {f['decision']}"
    markup = f"""<?xml version="1.0" encoding="UTF-8"?>
<Markup>
  <Topic Guid="{tid}" TopicType="Issue" TopicStatus="{escape('Open' if not f.get('decision') else 'Decision')}">
    <Title>{escape((f.get('id') or '') + ' ' + f['title'])}</Title>
    <Labels>{escape(f['discipline_label'])}</Labels>
    <CreationDate>{now}</CreationDate>
    <CreationAuthor>{escape(author)}</CreationAuthor>
    <Description>{escape(desc)}</Description>
    <ReferenceLink>{escape(f['ref'])}</ReferenceLink>
  </Topic>
  <Viewpoints Guid="{vid}"><Viewpoint>viewpoint.bcfv</Viewpoint></Viewpoints>
</Markup>
"""
    guids = (f.get("evidence") or {}).get("guids") or ([f["element"]["guid"]] if f.get("element") else [])
    comps = "".join(f'<Component IfcGuid="{g}"/>' for g in guids)
    vp = f"""<?xml version="1.0" encoding="UTF-8"?>
<VisualizationInfo Guid="{vid}">
  <Components><Selection>{comps}</Selection><Visibility DefaultVisibility="true"/></Components>
</VisualizationInfo>
"""
    return tid, markup, vp


def export_bcf(findings: list[dict], path: str | Path, project: str = "Demo ship", author: str = "SonarIQ") -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bcf.version", '<?xml version="1.0" encoding="UTF-8"?>\n'
                                  '<Version VersionId="2.1"><DetailedVersion>2.1</DetailedVersion></Version>\n')
        z.writestr("project.bcfp", f'<?xml version="1.0" encoding="UTF-8"?>\n<ProjectExtension><Project ProjectId="'
                                   f'{uuid.uuid5(uuid.NAMESPACE_URL, project)}"><Name>{escape(project)}</Name>'
                                   f'</Project><ExtensionSchema/></ProjectExtension>\n')
        for f in findings:
            tid, markup, vp = _topic(f, now, author)
            z.writestr(f"{tid}/markup.bcf", markup)
            z.writestr(f"{tid}/viewpoint.bcfv", vp)
    tmp.replace(path)   # nothing is sent half-way
    return {"path": str(path), "topics": len(findings)}
