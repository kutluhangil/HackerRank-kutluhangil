<div align="center">

<img src="docs/media/hero.svg" alt="Ghost Data Audit Agent — HackerRank Orchestrate, October 2026" width="100%">

<p>
  <a href="https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists/leaderboard"><img alt="Rank" src="https://img.shields.io/badge/global%20rank-%23529-00e6b8?style=for-the-badge&labelColor=050c12"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-deterministic%20core-ffb547?style=for-the-badge&labelColor=050c12">
  <img alt="Contract" src="https://img.shields.io/badge/contract%20violations-0-7aa7ff?style=for-the-badge&labelColor=050c12">
  <img alt="Cost" src="https://img.shields.io/badge/run%20cost-~%240.60-00e6b8?style=for-the-badge&labelColor=050c12">
</p>

<p><em>An autonomous data-deletion audit agent built for the "Ghost Data Still Exists" challenge.<br>
Deterministic parsing for everything structured, a language model only where pixels and natural language demand it.</em></p>

<img src="assets/leaderboard.png" alt="The official leaderboard showing rank #529" width="100%">

</div>

<img src="docs/media/divider.svg" width="100%" alt="">

## The problem

A customer of a fictional e-commerce platform believes their account was deleted. Weeks later they try to sign up again and get *"This email is already registered."* Internal dashboards say the deletion request is **Complete**; underneath, personal data still lives on in backups, logs and side systems.

For **518 deletion requests**, the agent has to:

1. **Detect intent**: is this really a deletion request, and is it `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE`?
2. **Resolve identity**: every current and past email, phone, username and SHA-256 email hash.
3. **Establish truth at `audit_at`**: reported statuses are claims; only concrete evidence counts.
4. **Write ordered steps**: a finding, a remediation and a verification for every piece of data left behind, following the deletion policy.

<img src="docs/media/divider.svg" width="100%" alt="">

## The approach: deterministic core, LLM at the edges

<img src="assets/pipeline.svg" alt="Pipeline architecture" width="100%">

| Principle | |
|---|---|
| **94 evidence files, split** | 79 structured files (SQL snapshots, JSON, five log dialects, handover notes) are parsed by plain Python: deterministic, zero tokens. |
| **LLM only where needed** | The model reads multilingual requests, 11 screenshots and 4 PDFs, and nothing else. |
| **Claims are not evidence** | `reported_status = COMPLETE` is never taken as truth; only observation records decide. |
| **Time cut-off** | Nothing that happened after `audit_at` may justify a verdict. |
| **Reproducible** | Model answers are cached on disk, so `python3 code/main.py` reproduces the output without an API key. |

<img src="docs/media/divider.svg" width="100%" alt="">

## Türkçe özet

Bu proje, **HackerRank Orchestrate (Ekim 2026)** yarışmasındaki "Ghost Data Still Exists" görevi için geliştirdiğim otonom bir veri silme denetim ajanı; global sıralamada **#529** oldu. 518 silme talebi için kullanıcının gerçekten silinip silinmediğini kanıtlardan çıkarıyor ve eksik kalan her veri için bulgu, düzeltme ve doğrulama adımları yazıyor. Yapısal dosyalar saf Python ile, sıfır token harcanarak okunuyor; dil modeli yalnızca çok dilli talepler, ekran görüntüleri ve PDF'ler için kullanılıyor. Tam çalıştırma yaklaşık 0,60 dolar tutuyor.

<img src="docs/media/divider.svg" width="100%" alt="">

## Running it

```sh
python3 code/main.py                 # reproduces output.csv from the cached model answers
python3 code/evaluation/validate_output.py   # output contract checks
python3 code/evaluation/main.py              # scoring against the sample set
```

```
code/main.py           CLI entry: atomic writes, cache checks
code/ghost_audit/      parsers, identity resolution, evidence timeline, policy engine, writers
code/evaluation/       metrics and contract validation
dataset/               the challenge data and evidence files
output.csv             the submitted answer
```

<div align="center">
<br>
<a href="https://github.com/kutluhangil"><img src="docs/media/signature.svg" width="100%" alt="Built by kutluhangil"></a>
<sub>HackerRank Orchestrate · October 2026 · score 67.2 · rank #529.</sub>
</div>
