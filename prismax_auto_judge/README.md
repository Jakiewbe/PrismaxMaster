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

## Safety Rule

Do not use `auto` or `auto_limited` until a real dry-run batch has been reviewed. Normal videos without a valid VLM result remain `UNCERTAIN` and are not submitted.
