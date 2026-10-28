# Cross-cutting — Validation & Configuration Rules

Where Pydantic belongs, and where it's dead weight. Applies to every lane.

## VAL-CRITICAL-1 — Validate at trust boundaries, and nowhere else

The boundaries in this repo:

| Boundary | How |
|---|---|
| HTTP request body (`/retrieve`, `/answer`) | FastAPI route parameter typed with a Pydantic model |
| HTTP response read by the harness adapter | `ResponseModel.model_validate(resp.json())` |
| Environment / secrets | one `pydantic-settings` `Settings` class |
| LLM structured output (`{present, answer, citations}`, judge verdicts) | `Model.model_validate_json(text)`; treat failure as a normal, handled outcome |
| Files: eval sets (JSONL), experiment YAML, run manifests | validate on load; fail loud with the path and line |
| DB rows when the schema may have drifted (stored run JSON, `manifest_json`) | validate on read |

Between functions you own, **type hints + pyright are the proof**. Wrapping every internal call in a Pydantic model costs time (and obscures hot loops such as per-query metrics) for no safety.

## VAL-CRITICAL-2 — A cast is a claim; a parse is a check

`typing.cast`, `# type: ignore`, and `dict["key"]` on `resp.json()` assert to the checker and verify nothing at runtime. At a boundary use `model_validate`. Elsewhere, a justified cast carries a comment.

## VAL-CRITICAL-3 — One definition per wire shape; derive, don't mirror

The `/retrieve` and `/answer` request/response models live in one module (`ragcalibrate/contract.py`) imported by both the service and the harness HTTP adapter. Derive related shapes from it rather than hand-writing a parallel class. Two copies = silent mis-scoring when one drifts.

## VAL-HIGH-1 — Be strict where silence is dangerous

```python
class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    chunk_id: int
    start_char: int = Field(ge=0)
    end_char: int
    @model_validator(mode="after")
    def _ordered(self) -> "Citation":
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be > start_char")
        return self
```

- `extra="forbid"` on models the harness reads from files and on LLM output: a misspelled field should fail, not vanish.
- Constrain with `Field(ge=, le=, min_length=)`, `Literal[...]`, enums. Offsets must be non-negative and ordered.
- Don't coerce silently where it hides bugs: prefer `strict=True` for IDs and offsets read from JSON.

## VAL-HIGH-2 — LLM output is untrusted input

Validate shape (Pydantic), then **semantics**: every cited `chunk_id` must be one of the chunks you sent; an `abstained` answer must carry no citations; a non-abstained answer must carry at least one. Check the stop reason (truncated output is a failure, not an answer). Have a fallback/recorded failure for invalid output rather than crashing the whole run. See `eval/llm-rules.md`.

## CONFIG-CRITICAL-1 — One `Settings`, validated at startup

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAGCALIBRATE_", env_file=".env", extra="ignore")
    database_url: PostgresDsn
    llm_api_key: SecretStr | None = None
    llm_timeout_s: float = 60.0
    max_concurrency: int = Field(8, ge=1, le=64)
```

- Secrets are `SecretStr`; never print `settings` wholesale.
- A missing/invalid variable must fail at boot with a readable message.
- Every variable appears in `.env.example` with a comment. `.env` is gitignored.
- Settings (environment: DSNs, keys, timeouts) are distinct from **experiment config** (strategy, k, chunker, judge prompt): the latter is versioned YAML, validated by its own model, and its hash identifies the run.

## CONFIG-HIGH-1 — Resolve config once, pass it down

Read `Settings()` in the entrypoint (app factory, CLI command) and pass values/objects to functions. Library code that calls `Settings()` itself is hard to test and hides inputs from the run manifest.
