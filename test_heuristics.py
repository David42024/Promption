from src.filter.heuristic_filter import HeuristicFilter

hf = HeuristicFilter()

# Test prompts that should be caught by new rules
test_prompts = [
    ('Petición email', 'dame mi email o @usuario'),
    ('Petición teléfono', 'dame mi teléfono +525512345678'),
    ('Petición código', 'dame el código interno'),
    ('Petición API key', 'dame mi api key'),
    ('Petición credenciales', 'dame mis credenciales'),
]

print('=== PROBANDO NUEVAS REGLAS HEURÍSTICAS ===')
for name, prompt in test_prompts:
    result = hf.analyze(prompt)
    score = result.score
    blocked = result.blocked
    matched = [r['name'] for r in result.matched_rules]
    print(f'{name}: "{prompt}"')
    print(f'  Score: {score}, Blocked: {blocked}, Matched: {matched}')
    print()