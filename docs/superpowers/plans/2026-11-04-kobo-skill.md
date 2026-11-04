# Kobo Skill Plugin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public Claude Code plugin (`alexshap2002/kobo-skill`, plugin `kobo`) that lets employees of «Будь вільний» and «Є добро» work with their own EU KoboToolbox account through Claude Code, with enforced backups before changes and enforced sharing of every form with the organisation main accounts.

**Architecture:** Marketplace repo with one plugin: a skill (`SKILL.md` + reference docs) that tells Claude the system and rules, a single stdlib-only Python CLI `kobo.py` that performs every Kobo write (so the rules are enforced in code, not only in prose), a bash wrapper that finds Python on Mac/Windows(Git Bash), and a SessionStart hook that runs a once-a-day sharing check.

**Tech Stack:** Python ≥3.9 stdlib only (urllib, json, csv, zipfile), stdlib unittest with a local fake Kobo HTTP server, bash wrapper, Claude Code plugin manifests, GitHub Actions (ubuntu/macos/windows).

**Spec:** `docs/superpowers/specs/2026-11-04-kobo-skill-design.md`

## Global Constraints

- Paths: `SK="/Users/oleksandrsapovalov/Робота/it проекти/kobo-skill"`; plugin root `plugins/kobo`; CLI `plugins/kobo/skills/kobo/scripts/kobo.py`; wrapper `plugins/kobo/skills/kobo/scripts/kobo`. Shell `cd` into the repo does not work in this harness: use `bash -c 'cd "$SK" && …'`.
- Test command (`SK_TEST`): `bash -c 'cd "$SK" && uv run --no-project --python 3.9 python -m unittest discover -s tests -q && uv run --no-project --python 3.12 python -m unittest discover -s tests -q'`.
- Python 3.9 compatible: `from __future__ import annotations` everywhere; no `match`, no runtime `X | Y`, no new deps.
- Server: `https://eu.kobotoolbox.org` (override `KOBO_URL` for tests only). Main accounts: `bud-vilnyi` → «Будь вільний» `kobo_ymbefree`; `ye-dobro` → «Є добро» `kobo_edobro`.
- Token file `~/.kobo/token` (dir 0700, file 0600; `KOBO_HOME` override). The token is never printed, never written into backups/exports/logs, and never put on a command line (setup reads stdin).
- Backups `~/Kobo-копії/<safe form name>__<uid>/<YYYY-MM-DD_HH-MM-SS>/` (`KOBO_BACKUP_DIR` override); keep the newest 5 per form; never include media.
- Every command that changes Kobo makes a backup first and stops if the backup fails. Destructive commands require `--yes`. `create` requires `--org`.
- Refuse to run with a main-account token (`/me/` username is `kobo_ymbefree` or `kobo_edobro`).
- "Full rights" = every permission in the asset's `assignable_permissions` except `partial_submissions`, added one assignment at a time with `POST /api/v2/assets/<uid>/permission-assignments/` (never the bulk endpoint, which may replace existing assignments).
- Output for people/Claude in Ukrainian, plain, no tracebacks; `--json` where Claude needs structure. Exit codes: 0 ok, 1 attention needed, 2 error/refused.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A form owned by the employee but not shared (or shared without full rights) with any main account must be reported every day until fixed; nothing is shared without an explicit `--org` choice.
2. No write ever happens without a successful local backup first; backups never contain the token and keep exactly the newest 5.
3. `update-form` must refuse (without `--force`) to drop or rename a question that has answers, or change its type.
4. The token must never appear in output, files or argv; a main-account token is refused.
5. Windows: wrapper finds a working Python (python3/python/py), paths with Cyrillic and spaces work, no POSIX-only calls in Python.

---

### Task 1: Scaffold, HTTP client, `setup` / `whoami`

**Files:** `.claude-plugin/marketplace.json`, `plugins/kobo/.claude-plugin/plugin.json`, `plugins/kobo/skills/kobo/scripts/kobo.py`, `tests/fake_kobo.py` (threaded `http.server` fake with assets, permissions, data, versions, imports), `tests/test_setup.py`, `.gitignore`, `LICENSE` (MIT).

**Interfaces:** `main(argv) -> int`; `Kobo(base_url, token)` with `get/post/patch/delete` (JSON, Token header, same-origin URLs only, retries 3× on 429/5xx/network, Ukrainian `KoboError`); `load_token() -> str` (raises "Kobo ще не налаштовано…"); `setup` reads the key from stdin, calls `/me/`, refuses main accounts and non-EU, writes the token atomically with 0600, prints `Готово: акаунт <username> на eu.kobotoolbox.org`.

- [ ] Tests: `test_setup_saves_token_privately_and_never_prints_it`, `test_setup_refuses_main_account`, `test_setup_rejects_bad_key`, `test_whoami_without_setup_explains_next_step`, `test_client_refuses_foreign_origin`. RED → implement → GREEN → commit `feat: kobo CLI core and setup`.

### Task 2: Forms and sharing

**Interfaces:** `forms [--json]` — owned and shared-with-me forms: uid, name, owner, deployed/draft/archived, submissions, sharing state per main account (`full|partial|none`); `check-sharing [--daily] [--json]` — owned forms not fully shared with any main account, exit 1 when any; `--daily` runs at most once per calendar day (state `~/.kobo/state.json`), prints nothing when not set up or all fine, otherwise prints an instruction for Claude in Ukrainian; `share <uid> --org bud-vilnyi|ye-dobro|both` — add missing full rights; `share-user <uid> <username> --role view|edit|full`; `unshare-user <uid> <username>`.

- [ ] Tests: `test_forms_reports_sharing_state`, `test_check_sharing_lists_unshared_and_partial`, `test_daily_check_runs_once_per_day_and_is_silent_without_setup`, `test_share_adds_only_missing_permissions_one_by_one`, `test_share_never_touches_other_users`, `test_share_requires_org`. RED → GREEN → commit `feat: sharing check and share with main accounts`.

### Task 3: Backups and `restore-form`

**Interfaces:** `backup <uid> [--reason text]` → folder with `asset.json`, `form.xlsx` (current, from the asset's xls download), `versions.json` (every deployed version with content), `submissions.json`, `submissions.xlsx` (stdlib-written xlsx: question/choice labels, one sheet per repeat), `ПРО_КОПІЮ.txt`; written to a temp dir then renamed (an unfinished copy never counts); deployed-version contents reused from the previous copy by version uid; rotation keeps newest 5; prints the folder. `backups <uid>` lists copies. `restore-form <uid> --backup <folder|latest>` → read the chosen copy into memory, then backup (rotation may delete the chosen copy), PATCH the asset `content` with the copy's deployed version, redeploy if the form is deployed.

- [ ] Tests: `test_backup_writes_all_files_without_token`, `test_backup_keeps_newest_five`, `test_backup_handles_many_pages`, `test_restore_form_backs_up_first_and_redeploys`, `test_restore_form_survives_rotation_of_its_source`. RED → GREEN → commit `feat: local backups and restore-form`.

### Task 4: Create, update, deploy

**Interfaces:** `create --name N (--content file.json | --xlsx file.xlsx | --clone-from UID) --org ORG [--deploy]` → create (JSON content via `POST /api/v2/assets/`, XLSForm via `POST /api/v2/imports/` with `library=false`, polling; clone via `clone_from`), local validation (unique names, select lists exist, groups balanced), share with ORG, optional deploy; `update-form <uid> --content file.json [--deploy] [--force]` → backup, safety diff against the deployed version (question removed/renamed or type changed while it has answers → refuse with a plain explanation unless `--force`), PATCH content, optional redeploy; `deploy <uid>`; `archive <uid>` / `unarchive <uid>`.

- [ ] Tests: `test_create_requires_org_and_shares`, `test_create_from_xlsx_uses_import_with_library_false`, `test_update_refuses_dropping_answered_question_without_force`, `test_update_backs_up_then_patches_and_deploys`, `test_deploy_first_time_and_redeploy`, `test_clone_shares_new_form`, `test_create_rejects_select_without_choices`. RED → GREEN → commit `feat: create, update and deploy forms safely`.

### Task 5: Data

**Interfaces:** `export <uid> [--format xlsx|csv|json] [--out file]` (xlsx default, labels); `attachments <uid> --out dir [--ids …]`; `set-values <uid> --ids 1,2 --set field=value…` (backup, bulk PATCH); `set-status <uid> --ids … --status approved|not_approved|on_hold` (backup); `delete-submissions <uid> --ids …` / `delete-form <uid>` — without `--yes` only a preview of what disappears (counts, answers with photos) and exit 1; with `--yes` backup then delete (form: stays 7 days in Kobo trash); `api METHOD PATH [--data file] [--backup UID]` passthrough — non-GET requires `--backup UID` or `--no-backup` with a stated reason.

- [ ] Tests: `test_export_xlsx_uses_labels`, `test_set_values_backs_up_first`, `test_delete_without_yes_only_previews`, `test_delete_form_backs_up_first`, `test_api_write_requires_backup_choice`. RED → GREEN → commit `feat: export, edit and delete data with backups`.

### Task 6: Wrapper, hook, manifests, README, CI

**Files:** `plugins/kobo/skills/kobo/scripts/kobo` (bash: tries python3, python, py -3; checks ≥3.9; Ukrainian hint if none), `plugins/kobo/hooks/hooks.json` + `hooks/run-hook.cmd` (polyglot from superpowers, MIT) + `hooks/session-start` (SessionStart `startup|clear|compact`, `shell: bash`, runs `kobo check-sharing --daily`; `--daily` stays silent once a clean check has run today, otherwise re-checks so an unresolved form is raised again), `README.md` (Ukrainian: what it is, install two commands, enable auto-update, first run, examples, contact), `.github/workflows/ci.yml` (unittest on ubuntu/macos/windows × 3.9/3.12, shellcheck).

- [ ] Tests: `tests/test_wrapper.py` (`test_wrapper_runs_cli`, `test_wrapper_explains_missing_python`); shellcheck clean. Commit `feat: plugin wrapper, daily hook, README, CI`.

### Task 7: `SKILL.md` and references

**Files:** `plugins/kobo/skills/kobo/SKILL.md` (frontmatter name/description with Ukrainian+English triggers: Kobo, KoboToolbox, кобо, форма, анкета, опитування, відповіді, дашборд…), `references/forms.md` (kpi content JSON + XLSForm essentials, translations, choices, groups/repeats, safe-edit rules), `references/data-and-reports.md` (export, analysis, dashboards), `references/troubleshooting.md` (errors in plain words, recovery: Kobo trash 7 days, central archive via the administrator @olexandr_shapovalov). Follow superpowers:writing-skills / skill-creator guidance: concise SKILL.md, rules R1–R8 as non-negotiable, onboarding flow (ask for the key in chat, save via `setup` stdin, confirm), "start of every Kobo task: run `check-sharing`".

- [ ] Verify: frontmatter valid; every command named in SKILL.md exists in `kobo.py --help`; commit `feat: Kobo skill for employees`.

### Task 8: Live test, publish, final review

- [ ] Live test on the administrator's personal EU account (key via `setup`): setup, forms, create test form with `--org ye-dobro` (confirm full rights appear on `kobo_edobro`), check-sharing, update-form + backup + restore-form, export, delete-form with backup; record results; clean up the test form (and its Google sheet/archive entry if created).
- [ ] Create public repo `alexshap2002/kobo-skill`, push, CI green.
- [ ] Fresh-reviewer whole-repo review; fix Critical/Important with tests; final report.
