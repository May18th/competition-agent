import json

d = json.load(open("static/demo_sample.json", encoding="utf-8"))
D = d["data"]

def show(name):
    print("=" * 20, name, "=" * 20)
    print(json.dumps(D[name], ensure_ascii=False, indent=1))
    print()

for k in ["dims", "judge_scores", "scores", "expert_review", "similarity",
          "completeness", "theme_drift", "keywords", "disclaimer",
          "project_summary", "one_liner", "proposal_selfcheck", "theme"]:
    show(k)

print("=" * 20, "proposal head 1200", "=" * 20)
print(D["proposal"][:1200])
print()
print("=" * 20, "proposal tail 600", "=" * 20)
print(D["proposal"][-600:])
print()
print("=" * 20, "proposal_outline", "=" * 20)
print(D["proposal_outline"])
print()
print("=" * 20, "ppt_outline head 1500", "=" * 20)
print(D["ppt_outline"][:1500])
print()
print("=" * 20, "speech_script head 800", "=" * 20)
print(D["speech_script"][:800])
print()
print("=" * 20, "defense_questions head 800", "=" * 20)
print(D["defense_questions"][:800])
print()
print("=" * 20, "judge_feedback head 600", "=" * 20)
print(D["judge_feedback"][:600])
print()
print("=" * 20, "parsed_rules head 900", "=" * 20)
print(D["parsed_rules"][:900])
print()
print("=" * 20, "similarity_report head 700", "=" * 20)
print(D["similarity_report"][:700])
print()
print("=" * 20, "proposal_analysis head 700", "=" * 20)
print(D["proposal_analysis"][:700])
print()
print("=" * 20, "rich_deck slides[0..3]", "=" * 20)
print(json.dumps(d["rich_deck"]["slides"][:3], ensure_ascii=False, indent=1))
print()
print("deck slide types:", [s.get("type") for s in d["rich_deck"]["slides"]])
print()
print("=" * 20, "idea_feedback head 500", "=" * 20)
print(D["idea_feedback"][:500])
