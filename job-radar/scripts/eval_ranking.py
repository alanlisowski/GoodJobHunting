"""Go/no-go check: does the model rank postings the way you would?

Put pasted posting text in tests/fixtures/eval/<name>.txt and your own order,
best fit first, in tests/fixtures/eval/expected.yaml as a list of <name>s.
Run from job-radar/: python -m scripts.eval_ranking
"""

from pathlib import Path

import anthropic
import yaml

EVAL = Path("tests/fixtures/eval")


def spearman(expected: list[str], actual: list[str]) -> float:
    # ponytail: no-ties formula; tied model scores get arbitrary order, fine for n=10.
    n = len(expected)
    pos = {name: i for i, name in enumerate(actual)}
    d2 = sum((i - pos[name]) ** 2 for i, name in enumerate(expected))
    return 1 - 6 * d2 / (n * (n * n - 1))


def main():
    from app.scoring import score
    from app.settings import settings

    expected = yaml.safe_load((EVAL / "expected.yaml").read_text(encoding="utf-8"))
    profile = Path("profile.yaml").read_text(encoding="utf-8")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())

    results, tokens_in, tokens_out = {}, 0, 0
    for name in expected:
        s, r = score((EVAL / f"{name}.txt").read_text(encoding="utf-8"), profile, client)
        results[name] = s
        tokens_in += r.usage.input_tokens + (r.usage.cache_read_input_tokens or 0)
        tokens_out += r.usage.output_tokens
        print(f"{s.score:>3}  {name}: {s.verdict}")

    actual = sorted(results, key=lambda k: -results[k].score)
    print(f"\n{'yours':<30}model")
    for e, a in zip(expected, actual):
        print(f"{e:<30}{a} ({results[a].score})")
    print(f"\nSpearman: {spearman(expected, actual):.2f}  (below ~0.6: stop and rethink)")
    print(f"Tokens: {tokens_in} in, {tokens_out} out")


if __name__ == "__main__":
    main()
