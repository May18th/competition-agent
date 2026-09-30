import json, io, sys

p = "static/demo_sample.json"
d = json.load(open(p, encoding="utf-8"))

print("TOP_KEYS", list(d.keys()))
print()
print("DATA_FIELDS", list(d["data"].keys()))
print()
for k, v in d["data"].items():
    t = type(v).__name__
    if isinstance(v, str):
        print("  %-28s str  len=%d" % (k, len(v)))
    elif isinstance(v, (int, float)):
        print("  %-28s num  %s" % (k, v))
    elif isinstance(v, list):
        print("  %-28s list n=%d" % (k, len(v)))
    elif isinstance(v, dict):
        print("  %-28s dict keys=%s" % (k, list(v.keys())))
    else:
        print("  %-28s %s" % (k, t))
print()
print("RATING_KEYS", list(d.get("rating", {}).keys()) if isinstance(d.get("rating"), dict) else type(d.get("rating")).__name__)
print("RICH_DECK_KEYS", list(d.get("rich_deck", {}).keys()))
print("RICH_CHARTS_N", len(d.get("rich_charts", [])))
print("RICH_TABLES_N", len(d.get("rich_tables", [])))
print("_DEMO", d.get("_demo"))
print("_DEMO_NOTE", d.get("_demo_note"))
print("SUCCESS", d.get("success"))
print()

# rich_charts detail
rc = d.get("rich_charts", [])
for i, c in enumerate(rc):
    print("CHART[%d] keys=%s" % (i, list(c.keys())))
    print("   ", json.dumps(c, ensure_ascii=False)[:400])
print()
rt = d.get("rich_tables", [])
for i, t in enumerate(rt):
    print("TABLE[%d] keys=%s" % (i, list(t.keys())))
    print("   ", json.dumps(t, ensure_ascii=False)[:400])
print()
rd = d.get("rich_deck", {})
for k, v in rd.items():
    if isinstance(v, list):
        print("DECK.%s list n=%d" % (k, len(v)))
        if v:
            print("    item0:", json.dumps(v[0], ensure_ascii=False)[:600])
    elif isinstance(v, dict):
        print("DECK.%s dict keys=%s" % (k, list(v.keys())))
        print("    ", json.dumps(v, ensure_ascii=False)[:600])
    else:
        print("DECK.%s = %r" % (k, v))
print()
print("RATING_DUMP:")
print(json.dumps(d.get("rating"), ensure_ascii=False)[:3000])
