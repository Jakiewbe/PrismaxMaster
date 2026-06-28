# PrismaX VLA Auto Judge

Production-safe defaults:

- `runtime.mode` defaults to `dry_run`.
- Supported modes: `dry_run`, `assist_preview`, `assist_fill`, `auto`, `auto_limited`.
- `auto_limited` still uses submit safety checks, and also respects the daily VLA workflow quota.
- `vlm.enabled` defaults to `false`.
- `safety.allow_auto_fail_submit` defaults to `false`.
- Text-only providers are blocked as primary VLA scorers unless explicitly allowed.

## Provider Choices

Use a multimodal provider for primary scoring. The provider must be able to inspect frame images.

```yaml
vlm:
  enabled: true
  provider: "openai_compatible"
  model: "gpt-4o-mini"
```

Set the API key in the environment:

```powershell
$env:OPENAI_API_KEY="..."
```

For an OpenAI-compatible Xiaomi endpoint, configure the endpoint and model:

```yaml
vlm:
  enabled: true
  provider: "xiaomi_compatible"
  provider_profiles:
    xiaomi_compatible:
      base_url: "https://YOUR_XIAOMI_COMPATIBLE_ENDPOINT/chat/completions"
      api_key_env: "XIAOMI_API_KEY"
      model: "YOUR_MULTIMODAL_MODEL"
```

DeepSeek is text-only in this implementation. It is intentionally blocked as a primary scorer:

```yaml
vlm:
  provider: "deepseek_text"
  allow_text_only_primary: false
```

Only set `allow_text_only_primary: true` if you knowingly want a text-only review of already-generated visual summaries. It cannot inspect image frames directly.

## Dry Run

```powershell
python .\prismax_auto_judge\main.py
```

Outputs:

- JSONL scoring logs: `data/logs/scoring_log.jsonl`
- VLM request packages: `data/logs/vlm_requests`
- VLM raw responses: `data/logs/vlm_responses`

## Live Test Steps

Run these one by one. They are ordered from safe to risky.

```powershell
# 1. Only check whether control has reached the configured threshold.
python .\prismax_auto_judge\main.py --live-step workflow

# 2. Connect to Chrome and open the VLA review list. No filling, no submit.
python .\prismax_auto_judge\main.py --live-step open-review

# 3. Open the first Review & Earn item. No filling, no submit.
python .\prismax_auto_judge\main.py --live-step open-first

# 4. Capture key frames from the current VLA video page. No filling, no submit.
# It prints capture_summary with frame counts and black_or_not_ready errors.
python .\prismax_auto_judge\main.py --live-step capture

# 5. Capture and ask the configured VLM for a score. No filling, no submit.
python .\prismax_auto_judge\main.py --live-step score

# 6. Fill the form only. Set runtime.mode to assist_fill first. No submit.
python .\prismax_auto_judge\main.py --live-step fill

# 7. Test returning to the configured arm queue. This does not need the control threshold.
python .\prismax_auto_judge\main.py --live-step return-arm

# 8. Submit only when runtime.mode is auto_limited and dry runs look correct.
python .\prismax_auto_judge\main.py --live-step submit
```

Default workflow now requires `min_control_operations_before_vla: 6`. Missing control state blocks VLA instead of silently continuing.
Live capture waits for videos to become ready, warms playback briefly, samples 13 timeline points, and filters black frames. Auto-PASS/FAIL now requires `confidence >= 0.90`.

## Safety Rule

Do not use `auto` or `auto_limited` until a real dry-run batch has been reviewed. Normal videos without a valid VLM result remain `UNCERTAIN` and are not submitted.
