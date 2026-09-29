## [v18.7.16.5] - 2026-07-06 (Qwen Post-Training: Prompt v2 + SFT/DPO Pipeline)

### Added
- **Hardened prompt v2** (`llm_assistant/prompts/agent_v2.json`):
  5-layer defense (role / scope / vocab / schema / anti-pattern), 3 few-shot
  examples (case4gs / case14 / finish_report call), network metadata injection
  template (bus_count, max_bus_id whitelist, etc.), pinyin-with-English-fallback
  encoding to avoid GBK mojibake. `temperature: 0.2` (vs v1's 0.3). 3695-char
  system prompt + 1018-char user template.
- **SFT synthesizer** (`llm_assistant/sft_synth.py`):
  Extracts (system, user, assistant) triples from `output/llm_calls/*.jsonl`
  filtered by IG score and success. CLI bug fix: `_load_prompts_safe()` now
  uses `spec_from_file_location` so the script works when invoked as
  `py llm_assistant/sft_synth.py` (where `llm_assistant` is not on sys.path).
- **DPO pair miner** (`llm_assistant/dpo_pairs.py`):
  Builds (prompt, chosen, rejected) triples by grouping audit records by
  (network_name|caller|source, schema_name). Group key now falls back to
  `caller` then `source` so bench cases (case4gs/case5/etc.) group correctly.
  Thresholds: chosen IG>=95 success, rejected IG<=80 or fallback/failed.
- **LoRA fine-tuner** (`llm_assistant/finetune_lora.py`):
  Wraps transformers + peft + trl + datasets. r=16, alpha=32, dropout=0.05,
  3 epochs SFT @ lr=2e-5 then optional DPO @ lr/5 with beta=0.1. bf16.
  Targets attention + MLP projections (q/k/v/o + gate/up/down). Saves to
  `output/lora_qwen3.5-4b_v2/{sft_adapter,dpo_adapter,final/}`.
- **Eval harness** (`llm_assistant/eval_harness.py`):
  Runs each prompt version against case4gs/5/6/9/14, summarizes deploy vs
  fallback counts, IG, gate pass rates, vocab/injection hits. `--dry-run` mode
  summarizes existing audit data by `stack` field (A=v1, B=v2). Writes
  JSON + Markdown verdict to `output/audit_daily/eval_v1_vs_v2.{json,md}`.

### Fixed
- **sft_synth.py CLI bug** (resumed from v18.7.16.5 handoff):
  Symptom: `py -3.11 llm_assistant/sft_synth.py --limit 10` wrote 0 samples
  while importing the module and calling `main()` worked. Root cause:
  `from llm_assistant.prompts import load_prompts` failed at script runtime
  because `llm_assistant` is not a known package when the script is run
  standalone (the script lives *inside* that package). Replaced with a
  file-relative `spec_from_file_location("_local_prompts_for_sft", ...)`
  pattern. Result: 37 SFT samples produced from 499 IG>=70 audit records.
- **dpo_pairs.py group key** (no pairs initially built):
  Audit records rarely populate `network_name` (only postprocess self-tests
  do). Switched the pair-key to derive from `caller` (e.g. `real-model:case5`)
  then `source` (e.g. `bench_gate_triggers_51.case5`). Now groups bench cases
  correctly and produces 5 valid DPO pairs spanning case4gs/case6/case9/test.

### Changed
- `llm_assistant/agent.py` now reads prompt version from `DIANLI_PROMPT_VERSION`
  env var (default: v1). Module exports `_PROMPT_VERSION` for debugging.
  Set `DIANLI_PROMPT_VERSION=v2` to enable hardened prompts at runtime.

### Test Suite
- 107/107 pass: test_gate8_injection (12), test_llm_postprocess (30),
  test_industrial_gates_v18_7_13 (36), test_v18_7_16_2_fixes (24),
  test_v18_7_16_3 (10). Suite runtime: 1.30s.

### Notes
- SFT data: 37 samples, IG 80-100, all from postprocess module's self-tests
  (stack="?"). Real-model bench (case4gs/5/6/9/14, stack="A") was excluded
  by the IG>=70 + tokens_out>=200 + success + not-fallback filter because
  the underlying audit log does not record `tokens_out` for bench runs.
  Future: capture `tokens_out` from llama-server response in next audit hook.
- DPO data: 5 pairs (postprocess, case4gs, case6, case9, test_v18_7_16_3).
- Fine-tune ready to run on user command: `py -3.11 llm_assistant/finetune_lora.py`
  (requires `pip install transformers peft trl accelerate datasets torch`).
- Eval harness can re-run with `py -3.11 llm_assistant/eval_harness.py --dry-run`
  for retrospective comparison, or without `--dry-run` to do real model calls.
- `eval_v1_vs_v2.md` dry-run output: v1 has 469 records (deploy=438, fb=21,
  IG=6.4); v2 has 170 records (deploy=61, fb=109, IG=24.7). Note: stack='B'
  coverage in audit is sparse (mostly test runs); full v2 retest pending.
