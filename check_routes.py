from app import create_app

app = create_app()

print("=== ЗАРЕГИСТРИРОВАННЫЕ МАРШРУТЫ В StroyBase ===")
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    print(f"{rule.rule:50}  →  {rule.endpoint}")
print("\n=== КОНЕЦ СПИСКА ===")