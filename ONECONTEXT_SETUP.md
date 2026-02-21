# OneContext Setup (JSR Hydra)

This project is scoped to a dedicated OneContext agent:

- Agent name: `jsr-hydra`
- Agent id: `bfec591c-8350-4837-8ef3-ff2d0210a5fc`
- Context title: `JSR Hydra Context`

## One-time setup

```bash
cd /Users/thuanle/Documents/JSR/JSRAlgoMac/jsr-hydra
onecontext doctor -v
onecontext config set dashboard_only false
```

## Per-terminal setup

Use the project helper:

```bash
cd /Users/thuanle/Documents/JSR/JSRAlgoMac/jsr-hydra
source scripts/onecontext_hydra.sh
```

Or export manually:

```bash
export ALINE_AGENT_ID=bfec591c-8350-4837-8ef3-ff2d0210a5fc
```

## Validate context + search

```bash
onecontext context show
onecontext search "brain|llm|regime|price|hydra" -t content --count
```

## Notes

- In this machine state, cloud login is not active. LLM summaries are stored as
  `LLM API Error` markers, but session/turn content is still imported and searchable.
- To enable watcher daemon and cloud summaries:

```bash
onecontext login
onecontext watcher fresh
```

