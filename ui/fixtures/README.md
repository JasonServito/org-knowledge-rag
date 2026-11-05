# UI fixtures

Real API responses for the UI's tests (S17-R1 c14). `index.ts` types them with `lib/types.ts`, so `make ui-check`'s typecheck checks them. Copied once, from the repo root; free.

## answers.json

The 43 saved answers of the conflict eval run, keyed by question id: each row's `answer` is the API's `Answer` (`POST /query`'s 200).

```bash
uv run python -c "
import json
rows = [json.loads(line) for line in open('eval/results/conflict-20261012T171932Z/questions.jsonl')]
answers = {row['id']: row['answer'] for row in rows}
with open('ui/fixtures/answers.json', 'w') as f:
    json.dump(answers, f, indent=2, ensure_ascii=False)
    f.write('\n')
print(len(answers), 'answers')
"
```

## chains/kep-2572.json, chains/kep-3015.json

The 2 stored decision chains, as `GET /decisions/{canonical_id}` returns them from the local database (`make up`, after `make chains`). The test client is used without `with`, so the app's startup doesn't run: no API client or model is built, and nothing is paid. `kep:3015`'s decision step is missing (`no_link`).

```bash
uv run python -c "
import json
from fastapi.testclient import TestClient
from orgknow.api.app import create_app
client = TestClient(create_app())  # no 'with': no lifespan, so no client or model is built
for seed in ['kep:2572', 'kep:3015']:
    response = client.get(f'/decisions/{seed}')
    assert response.status_code == 200, (seed, response.status_code)
    with open(f\"ui/fixtures/chains/{seed.replace(':', '-')}.json\", 'w') as f:
        json.dump(response.json(), f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(seed, response.status_code)
"
```
