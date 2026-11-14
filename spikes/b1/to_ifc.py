"""Spike B1, option 1 input: Fragments can only be made from IFC, and data/rcrv/rcrv_full.ifc carries boxes for
91 % of the ship. This writes one IFC4 per deck with the real triangles of every element (same GlobalIds as
scripts/rcrv_to_ifc.py, source id in Tag), as plain STEP text because ifcopenshell would hold 50 M triangles in RAM."""
import collections, json, sys, time
import numpy as np
import ifcopenshell, ifcopenshell.guid
from common import OUT, Ship

T0 = time.time()
ship = Ship()
schema = ifcopenshell.ifcopenshell_wrapper.schema_by_name("IFC4")
nattr = lambda c: len(schema.declaration_by_name(c).all_attributes())
new = ifcopenshell.guid.new
esc = lambda s: "".join(ch if 32 <= ord(ch) < 127 and ch not in "'\\" else "_" for ch in str(s))[:200]
lst = lambda a: str(a.tolist()).replace("[", "(").replace("]", ")").replace(" ", "")   # numpy -> STEP list, at C speed

by_deck = collections.defaultdict(list)
for e in ship.elements:
    by_deck[e["deck"]].append(e)
(OUT / "ifc").mkdir(exist_ok=True)
report = []
for deck, els in sorted(by_deck.items()):
    t = time.time()
    path = OUT / "ifc" / f"rcrv_deck_{deck}_full.ifc"
    tris = 0
    with open(path, "w") as f:
        w = f.write
        w("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [ReferenceView_V1.2]'),'2;1');\n"
          f"FILE_NAME('{path.name}','2026-11-13T00:00:00',(''),(''),'sonariq spike b1','','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
          "#1=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);\n#2=IFCUNITASSIGNMENT((#1));\n#3=IFCCARTESIANPOINT((0.,0.,0.));\n"
          "#4=IFCAXIS2PLACEMENT3D(#3,$,$);\n#5=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-5,#4,$);\n"
          "#6=IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,#5,$,.MODEL_VIEW.,$);\n"
          f"#7=IFCPROJECT('{new()}',$,'RCRV',$,$,$,$,(#5),#2);\n#8=IFCLOCALPLACEMENT($,#4);\n"
          f"#9=IFCSITE('{new()}',$,'RCRV',$,$,#8,$,$,.ELEMENT.,$,$,$,$,$);\n"
          f"#10=IFCBUILDING('{new()}',$,'RCRV',$,$,#8,$,$,.ELEMENT.,$,$,$);\n"
          f"#11=IFCBUILDINGSTOREY('{new()}',$,'Deck {deck}',$,$,#8,$,$,.ELEMENT.,0.);\n"
          f"#12=IFCRELAGGREGATES('{new()}',$,$,$,#7,(#9));\n#13=IFCRELAGGREGATES('{new()}',$,$,$,#9,(#10));\n"
          f"#14=IFCRELAGGREGATES('{new()}',$,$,$,#10,(#11));\n")
        n, styles, products = 15, {}, []
        for e in els:
            Vs, Fs, base = [], [], 0
            for ni in e["nodes"]:
                V, F = ship.node_mesh(ni)
                Vs.append(V); Fs.append(F.astype(np.int64) + base + 1); base += len(V)
            V = np.vstack(Vs).astype(np.float64).round(4); F = np.vstack(Fs)
            tris += len(F)
            col = tuple(round(c, 3) for c in ship.element_color(e)[:3])
            if col not in styles:
                w(f"#{n}=IFCCOLOURRGB($,{col[0]:.3f},{col[1]:.3f},{col[2]:.3f});\n#{n+1}=IFCSURFACESTYLESHADING(#{n},0.);\n"
                  f"#{n+2}=IFCSURFACESTYLE($,.BOTH.,(#{n+1}));\n")
                styles[col] = n + 2; n += 3
            cls = e["ifc"] or "IfcBuildingElementProxy"            # unmapped elements too: same geometry as the tiles
            w(f"#{n}=IFCCARTESIANPOINTLIST3D({lst(V)});\n#{n+1}=IFCTRIANGULATEDFACESET(#{n},$,$,{lst(F)},$);\n"
              f"#{n+2}=IFCSTYLEDITEM(#{n+1},(#{styles[col]}),$);\n#{n+3}=IFCSHAPEREPRESENTATION(#6,'Body','Tessellation',(#{n+1}));\n"
              f"#{n+4}=IFCPRODUCTDEFINITIONSHAPE($,$,(#{n+3}));\n"
              f"#{n+5}={cls.upper()}('{e['guid']}',$,'{esc(e['name'])}',$,$,#8,#{n+4},'{e['dbid']}'{',$' * (nattr(cls) - 8)});\n")
            products.append(n + 5); n += 6
        w(f"#{n}=IFCRELCONTAINEDINSPATIALSTRUCTURE('{new()}',$,$,$,({','.join('#%d' % p for p in products)}),#11);\nENDSEC;\nEND-ISO-10303-21;\n")
    report.append({"deck": deck, "file": path.name, "elements": len(els), "tris": tris, "bytes": path.stat().st_size,
                   "seconds": round(time.time() - t, 1)})
    print(report[-1], flush=True)
json.dump({"seconds": round(time.time() - T0, 1), "files": report}, open(OUT / "to_ifc.json", "w"), indent=1)
print("total", round(time.time() - T0, 1), "s", sum(r["bytes"] for r in report) / 1e9, "GB")
