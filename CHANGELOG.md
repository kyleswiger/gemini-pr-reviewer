# Changelog

## [1.0.1](https://github.com/kyleswiger/gemini-pr-reviewer/compare/v1.0.0...v1.0.1) (2026-08-29)


### Bug Fixes

* **ci:** let claude-review run on dependabot PRs ([adc11a1](https://github.com/kyleswiger/gemini-pr-reviewer/commit/adc11a1868f2f7e94125c6274feb4d569dc19508))
* **ci:** let claude-review run on dependabot PRs ([602925b](https://github.com/kyleswiger/gemini-pr-reviewer/commit/602925be9a0dddcd3c4f1b815b062a9298c9b128))

## 1.0.0 (2026-08-27)


### Features

* complete Phase 2 & 3 PR review pipeline with Gemini 2.5 and async Lambda execution ([299e14a](https://github.com/kyleswiger/gemini-pr-reviewer/commit/299e14aa3351f966341f46b0f23ebcff1d837b55))
* implement Phase 1 scaffolding (Terraform + Python Lambda) and deployment instructions ([5d54e77](https://github.com/kyleswiger/gemini-pr-reviewer/commit/5d54e77d9cbd2818ebf3958d5c45a5437a9ba484))


### Bug Fixes

* async self-invocations never reached the review pipeline (Mangum can't route them) ([291c409](https://github.com/kyleswiger/gemini-pr-reviewer/commit/291c40914fd481a403a729aa4f1b6626c2ddd5d9))
* dispatch async self-invocations past Mangum to the review pipeline ([58ef348](https://github.com/kyleswiger/gemini-pr-reviewer/commit/58ef348ca6023377197e3337f70a765ca29f6884))
* Gemini API key leaks into CloudWatch via the request URL ([5cd4ccd](https://github.com/kyleswiger/gemini-pr-reviewer/commit/5cd4ccdfdb5158711855151d02689ff3a485a909))
* **gemini:** survive free-tier quota with pinned models and honest retries ([03fc640](https://github.com/kyleswiger/gemini-pr-reviewer/commit/03fc640d508978c9b3f7008fb503bedb1b6f537e))
* **gemini:** survive free-tier quota with pinned models and honest retries ([91b4569](https://github.com/kyleswiger/gemini-pr-reviewer/commit/91b45699f00c649901d38da4ee767e53e2b0ff6a))
* keep a persistent event loop so warm webhook requests survive ([8fb337d](https://github.com/kyleswiger/gemini-pr-reviewer/commit/8fb337dadf740ad3e7cb62e642d9c0936234f67e))
* retry Gemini API 429/5xx with backoff instead of failing the review ([9cc96ca](https://github.com/kyleswiger/gemini-pr-reviewer/commit/9cc96ca73492cff6f67a975fff459ef873fe541c))
* retry transient Gemini API errors (429/5xx) with backoff ([853d317](https://github.com/kyleswiger/gemini-pr-reviewer/commit/853d3175cfa7afdfcb49b5a469324c6a2a99b456))
* send the Gemini API key via header, not the request URL ([c19e0fd](https://github.com/kyleswiger/gemini-pr-reviewer/commit/c19e0fd55656cc86464f655978eaf6b73c04e900))
* update default model to gemini-flash-latest ([57f3fde](https://github.com/kyleswiger/gemini-pr-reviewer/commit/57f3fde2942681de3df6071963a28418fa1c7613))
* warm-container webhook requests crash after an async review (event loop closed) ([bacd2f3](https://github.com/kyleswiger/gemini-pr-reviewer/commit/bacd2f35c92797186bbc870ff79a5013e7ee9524))
