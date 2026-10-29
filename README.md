# Outpour

## Write one article in Markdown. Publish it to Dev.to, Medium, Hashnode, WordPress, Ghost, and Nostr.

You wrote the article once. Then you paste it into four different editors, fix the formatting four times, re-upload the images, and re-type the tags. Outpour removes that tax. One Markdown file with frontmatter is the source of truth, and one command publishes or schedules it everywhere, with a ledger that remembers what went where, so a re-run updates your posts instead of duplicating them.

**For:** developer-writers, indie bloggers, docs and content teams, and small agencies that publish the same article in several places.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/fanpost/outpour)](https://github.com/fanpost/outpour/releases)
[![Stars](https://img.shields.io/github/stars/fanpost/outpour)](https://github.com/fanpost/outpour/stargazers)

**[Install in about 2 minutes](#quick-start)** · [See the web UI](https://fanpost.github.io/outpour/) · [Want it hosted? Join the waitlist](https://docs.google.com/forms/d/e/1FAIpQLSe3qMXj-idw8vcJe9swefxvUgUjifLGqTiIwkvAi188b6Nc2g/viewform)

## See it work

```console
$ outpour publish post.md --to devto --to nostr-longform --draft --dry-run

Dry Run Preview
No changes will be made

 File     post.md
 Title    How I stopped copy-pasting my own articles
 Status   Draft

              Target Platforms
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Platform       ┃ Status  ┃ Notes         ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ devto          │ ✓ Ready │ Would publish │
│ nostr-longform │ ✓ Ready │ Would publish │
└────────────────┴─────────┴───────────────┘
```

Drop the `--dry-run` and the same article goes out for real: a Dev.to draft plus a signed Nostr long-form event (NIP-23) on your relays. Run the command again after an edit and Outpour updates those exact posts. It never creates a second copy.

## Why Outpour

- **Nostr, natively.** Long-form publishing to Nostr (NIP-23, kind 30023) with your own key and your own relays. No other scheduler in this class does Nostr at all.
- **No duplicates, ever.** A local ledger stores every platform post id. Retries, re-runs, and scheduled jobs update or skip instead of re-posting, and a publish that succeeded but failed to record itself is recovered from a receipt, not posted twice.
- **Free to run, including the scheduler.** MIT-licensed and self-hosted. There is no account and no meter. The scheduler can even run entirely on GitHub Actions, so scheduled posting costs you zero servers.
- **CLI and a local web UI.** Same engine, your choice: script it from the terminal, or click through Articles, Editor, Schedule, and Platforms screens in the browser.
- **Built for AI agents too.** An MCP server and a bundled skill let Claude Code and other agents query the ledger and publish on request.
- **Your keys stay yours.** Platform keys live in your config file or environment variables, on your machine. Outpour sends them only to the platforms themselves.

## Quick start

Prerequisites: Python 3.10 or newer, and Git.

```bash
git clone https://github.com/fanpost/outpour
cd outpour
python3 -m venv .venv
.venv/bin/pip install -e ".[nostr,ui]"
```

Add the platforms you use to `~/.config/crier/config.yaml` (yes, the config directory still carries the upstream Crier name):

```yaml
platforms:
  devto:
    api_key: "your-devto-key"        # dev.to/settings/extensions
  nostr-longform:
    api_key: "nsec1...|wss://relay.damus.io,wss://nos.lol"
  medium:
    api_key: "manual"                # copy-paste mode, no token needed
```

Then publish, always with a dry run first:

```bash
.venv/bin/outpour publish post.md --to devto --to nostr-longform --draft --dry-run
.venv/bin/outpour publish post.md --to devto --to nostr-longform --draft
```

You should see a Dry Run Preview with "✓ Ready" for each configured platform before anything goes out. To schedule instead of publishing now:

```bash
.venv/bin/outpour publish post.md --to devto --schedule "tomorrow 9am"
.venv/bin/outpour schedule run        # run this from cron, or use the Actions setup below
```

Prefer clicking? The web UI runs locally:

```bash
.venv/bin/outpour serve               # http://127.0.0.1:8000
```

## Prefer not to install anything?

- **Click through the UI first:** the [project site](https://fanpost.github.io/outpour/) carries a clickable preview of all four screens.
- **Run the whole scheduler on GitHub Actions, free:** fork this repo, add one secret, and commit a schedule file. Step-by-step: [articles/README.md](articles/README.md).

## Platforms at a glance

- **Long-form:** Dev.to, Hashnode, Medium, Ghost, WordPress, Buttondown (newsletters), Nostr long-form (NIP-23)
- **Announcements:** Bluesky, Mastodon, Pleroma, Threads, Telegram, Discord, plus LinkedIn and X in manual copy-paste mode
- Full per-platform details, key formats, and notes are in the [reference](#reference) below.

## How it works

1. **Your Markdown is the source of truth.** YAML or TOML frontmatter carries the title, description, tags, and canonical URL.
2. **The ledger remembers.** A small SQLite database records which article went to which platform, with the remote post id and URL.
3. **The scheduler fires on time.** `outpour schedule run` publishes whatever is due, from cron, from the web UI host, or from a GitHub Actions workflow in this repo.

## Honest limitations

- **Not on PyPI yet.** Install from this repo with the quick start above.
- **Medium is publish-only.** Medium's API cannot edit or list posts, so edits happen on Medium itself.
- **LinkedIn and X have no article API** available to apps like this one, so Outpour handles them in manual mode: it formats the post, copies it to your clipboard, and records it only when you confirm you posted.
- **The web UI has no login.** It binds to 127.0.0.1 and is meant for your own machine. Put authentication in front of it before exposing it to any network.
- **Nostr means holding a private key.** Your nsec is a password. Store it like one.

## FAQ

**Is it free?**
Yes. Outpour is MIT-licensed and self-hosting is free forever. We are currently validating a paid hosted version (we run the scheduler and UI, you just write). If that is what you want, [join the waitlist](https://docs.google.com/forms/d/e/1FAIpQLSe3qMXj-idw8vcJe9swefxvUgUjifLGqTiIwkvAi188b6Nc2g/viewform). The form also asks which price point works for you.

**How is this different from Typefully, Narrareach, or Postiz?**
Those are hosted, closed products, and most are social-first. Outpour is open source, runs on your machine or your own Actions minutes, is long-form first, and is the only one that publishes natively to Nostr.

**What happens if a publish fails halfway?**
Each platform result is recorded independently. The successful ones stay published; the failed ones can be retried, and the retry updates or completes them instead of duplicating the successes.

**Can my AI agent use it?**
Yes. `outpour mcp` starts an MCP server over the ledger, the package ships a skill file, and every command supports `--json` output and a non-interactive `--batch` mode.

**Who should not use Outpour?**
If you publish to exactly one platform, its own editor is simpler. If you need native LinkedIn articles or X articles posted through an API, no third-party tool can do that today, including this one.

## Your next step

Pick a track:

- **Self-host it, free:** run the [quick start](#quick-start) and publish your first article as a draft today.
- **Hosted, no install:** [join the waitlist](https://docs.google.com/forms/d/e/1FAIpQLSe3qMXj-idw8vcJe9swefxvUgUjifLGqTiIwkvAi188b6Nc2g/viewform) and tell us which platform you miss most.

If Outpour saves you an hour of copy-pasting, a star helps the next writer find it.

## Credits

Outpour, by Fanpost, is a fork of [Crier](https://github.com/queelius/crier) by Alexander Richard Towell, kept under the MIT license (see LICENSE). Outpour adds the Nostr long-form platform, idempotent re-publishing guarantees, the local web UI, the GitHub Actions scheduler, and the Fanpost packaging. The internal Python package is still named `crier`, so both `outpour` and `crier` commands work.

---

# Reference

Everything below is the full manual: platform details, configuration, every command, automation, and the reliability model.

## Supported Platforms

| Platform | API Key Format | Notes |
|----------|---------------|-------|
| **dev.to** | `api_key` | Full article support |
| **Hashnode** | `token` or `token:publication_id` | Full article support |
| **Medium** | `integration_token` | Publish only (no edit/list) |
| **Ghost** | `https://site.com:key_id:key_secret` | Full article support |
| **WordPress** | `site.wordpress.com:token` or `https://site.com:user:app_pass` | Full article support |
| **Buttondown** | `api_key` | Newsletter publishing |
| **Bluesky** | `handle:app_password` | Short posts with link cards |
| **Mastodon** | `instance:access_token` | Toots with hashtags |
| **Pleroma** | `instance:access_token` | Mastodon-compatible API; also works for Akkoma |
| **Nostr** | `nsec1...` or hex key, optionally `nsec1...\|wss://relay.a,wss://relay.b` | Signed notes to relays; needs `pip install 'crier[nostr]'` |
| **Threads** | `user_id:access_token` | Short posts (no edit support) |
| **Telegram** | `bot_token:chat_id` | Channel/group posts |
| **Discord** | `webhook_url` | Server announcements |
| **LinkedIn** | `access_token` | Requires API access |
| **Twitter/X** | `any` (copy-paste mode) | Generates tweet for manual posting |

### Platform Notes

**Blog Platforms** (dev.to, Hashnode, Medium, Ghost, WordPress):
- Full markdown article publishing
- Preserves front matter (title, description, tags, canonical_url)
- Best for long-form content

**Newsletter Platforms** (Buttondown):
- Publishes to email subscribers
- Full markdown support
- Great for content repurposing

**Social Platforms** (Bluesky, Mastodon, LinkedIn, Twitter, Threads):
- Creates short posts with link to canonical URL
- Uses title + description + hashtags from tags
- Best for announcing new content

**Announcement Channels** (Telegram, Discord):
- Posts to channels/servers
- Good for community announcements
- Discord uses webhook embeds

### Manual Mode

For platforms with restrictive API access (Medium, LinkedIn, Twitter/X), you can use manual (copy-paste) mode:

```bash
# Explicit manual mode with --manual flag
crier publish post.md --to medium --manual
crier publish post.md --to linkedin --manual

# Skip auto-opening browser
crier publish post.md --to twitter --manual --no-browser
```

**Auto-manual mode**: If you configure a platform's API key to `"manual"`, crier automatically uses manual mode:

```bash
# Configure platform for manual mode (no API key needed)
crier config set twitter.api_key manual
crier config set linkedin.api_key manual

# Now these automatically use manual mode without --manual flag
crier publish post.md --to twitter
crier publish post.md --to linkedin
```

Manual mode workflow:
1. Formats content for the platform
2. Copies it to your clipboard
3. Opens the compose page in your browser
4. Asks if you successfully posted
5. Records to registry only if you confirm

This ensures the registry accurately reflects what's actually published.

## Configuration

All configuration lives in a single global file: `~/.config/crier/config.yaml`.
The registry (publication state) is a SQLite database at `~/.config/crier/crier.db`.

### Example config

```yaml
# Points crier at your content project (e.g., a Hugo site)
site_root: ~/github/repos/my-blog
site_base_url: https://example.com

# Directories to scan for markdown files (relative to site_root)
content_paths:
  - content/post
  - content/note

# File extensions to scan (default: .md)
file_extensions:
  - .md
  - .mdx

# Filename patterns to skip
exclude_patterns:
  - _drafts/*
  - _index.md

# Default platforms when --to / --profile not given
default_profile: everything

# Default author for AI-generated rewrites
rewrite_author: claude-code

platforms:
  devto:
    api_key: your_key_here
  bluesky:
    api_key: "handle.bsky.social:app-password"
  mastodon:
    api_key: "mastodon.social:access-token"
  twitter:
    api_key: manual    # Copy-paste mode
  medium:
    api_key: import    # URL import mode

profiles:
  blogs:
    - devto
    - hashnode
    - medium
  social:
    - bluesky
    - mastodon
  everything:
    - blogs           # Profiles can reference other profiles
    - social
```

| Option | Purpose |
|--------|---------|
| `site_root` | Content project directory (where `content/` lives) |
| `site_base_url` | For inferring canonical URLs |
| `content_paths` | Directories to scan for content (resolved against `site_root`) |
| `exclude_patterns` | Filename patterns to skip |
| `file_extensions` | Extensions to scan (default: `.md`) |
| `default_profile` | Default platforms when none specified |
| `rewrite_author` | Default `--rewrite-author` value |

### Environment Variables

Environment variables override config files:

```bash
export CRIER_DEVTO_API_KEY=your_key_here
export CRIER_BLUESKY_API_KEY="handle.bsky.social:app-password"
```

## Markdown Format

Crier reads standard markdown with YAML or TOML front matter:

```markdown
---
title: "My Amazing Post"
description: "A brief description"
tags: [python, programming]
canonical_url: https://myblog.com/my-post
published: true
---

Your content here...
```

TOML front matter is also supported (delimited by `+++`):

```markdown
+++
title = "My Amazing Post"
description = "A brief description"
tags = ["python", "programming"]

[extra]
canonical_url = "https://myblog.com/my-post"
+++

Your content here...
```

Date and tag filters support both front matter formats. When `site_base_url` is
configured, Crier resolves relative links and images against the article's
canonical URL, including an explicitly supplied `canonical_url`. Root-relative
links use the site's origin. Markdown references and HTML `href`/`src` attributes
are supported; code examples and surrounding formatting are preserved.

## Commands

```bash
# Publishing
crier init                              # Interactive setup wizard
crier publish FILE --to PLATFORM        # Publish to platform(s)
crier publish FILE --to PLATFORM --manual  # Manual copy-paste mode
crier publish FILE --to bluesky --thread   # Publish as thread
crier audit                             # See what's missing/changed
crier audit --publish                   # Bulk publish interactively
crier audit --publish --yes             # Bulk publish without prompting

# Content Management
crier search                            # List all content
crier search --tag python --since 1w    # Filter by tag and date
crier status [FILE]                     # Show publication status
crier list PLATFORM                     # List your articles
crier delete FILE --from PLATFORM       # Delete from platform
crier archive FILE                      # Archive (exclude from audit)
crier unarchive FILE                    # Unarchive

# Scheduling
crier schedule list                     # List scheduled posts
crier schedule show ID                  # Show scheduled post details
crier schedule cancel ID                # Cancel scheduled post
crier schedule run                      # Publish due posts

# Analytics
crier stats                             # Show stats for all content
crier stats FILE                        # Show stats for specific file
crier stats --top 10                    # Top 10 by engagement
crier stats --refresh                   # Refresh from platforms

# Configuration
crier config show                       # Show configuration
crier config set KEY VALUE              # Set configuration
crier config llm show                   # Show LLM configuration
crier config llm test                   # Test LLM connection
crier doctor                            # Verify API keys work
crier mcp                               # Start MCP server (for Claude Code)
```

## Automation

### Batch Mode

Use `--batch` for fully automated, non-interactive publishing (CI/CD):

```bash
# Batch mode implies --yes --json, skips manual/import platforms
crier publish post.md --to devto --to bluesky --batch
crier audit --publish --batch --long-form
```

Batch mode behavior:
- Implies `--yes` (no confirmation prompts)
- Implies `--json` (structured output for parsing)
- Implies `--only-api` (skips manual/import platforms that require user interaction)

### JSON Output

Use `--json` for machine-readable output:

```bash
crier publish post.md --to devto --json
crier audit --json
```

JSON output structure:
```json
{
  "command": "publish",
  "file": "post.md",
  "results": [{"platform": "devto", "success": true, "url": "..."}],
  "summary": {"succeeded": 1, "failed": 0, "skipped": 0}
}
```

### Auto-Rewrite

Use `--auto-rewrite` to generate short-form content using an LLM:

```bash
crier publish post.md --to bluesky --auto-rewrite
```

**Simplest setup:** If you have `OPENAI_API_KEY` set, it just works (defaults to gpt-4o-mini).

**Or configure in `~/.config/crier/config.yaml`:**

```yaml
# Minimal - just the API key (defaults to OpenAI + gpt-4o-mini)
llm:
  api_key: sk-...

# Or full config for Ollama/other providers
llm:
  base_url: http://localhost:11434/v1  # Ollama
  model: llama3
  # api_key: not needed for local Ollama
```

**Environment variables** (override config):
- `OPENAI_API_KEY`: API key (auto-defaults to OpenAI endpoint + gpt-4o-mini)
- `OPENAI_BASE_URL`: Custom endpoint (e.g., `http://localhost:11434/v1` for Ollama)

## Bulk Operations

The `audit` command supports powerful filtering for targeted bulk operations:

```bash
# Post to API platforms only (skip manual/import)
crier audit --publish --yes --only-api

# Long-form only (skip bluesky, mastodon, twitter, threads)
crier audit --publish --yes --long-form

# Random sample of 5 articles
crier audit --publish --yes --sample 5

# Filter by path
crier audit content/post --publish --yes --only-api

# Filter by date (relative)
crier audit --since 1w --publish --yes              # Last week
crier audit --since 1m --publish --yes              # Last month
crier audit --since 7d --until 1d --publish --yes   # 7 days ago to yesterday

# Filter by date (absolute)
crier audit --since 2025-12-01 --until 2025-12-31 --publish --yes

# Combine filters
crier audit content/post --since 1m --only-api --long-form --sample 10 --publish --yes
```

### Filter Reference

| Filter | Description |
|--------|-------------|
| `[PATH]` | Only scan specific directory |
| `--since` | Only content from this date (`1d`, `1w`, `1m`, `1y`, or `YYYY-MM-DD`) |
| `--until` | Only content until this date |
| `--only-api` | Skip manual/import/paste platforms |
| `--long-form` | Skip short-form platforms (bluesky, mastodon, twitter, threads) |
| `--sample N` | Random sample of N items |
| `--date-source` | Filter by `frontmatter` (default) or `mtime` |
| `--batch` | Non-interactive mode (implies `--yes --json`, skips manual platforms) |
| `--json` | Output results as JSON |

Filters are applied in order: path → date → platform mode → content type → tag → sampling

## Delete & Archive

### Deleting Content

Remove published content from platforms:

```bash
# Delete from specific platform
crier delete post.md --from devto

# Delete from all platforms
crier delete post.md --all

# Preview what would be deleted
crier delete post.md --all --dry-run
```

Deletion records are preserved in the registry (marked as deleted) to prevent accidental re-publishing.

### Archiving Content

Archive content to exclude it from `audit --publish`:

```bash
# Archive (exclude from bulk publishing)
crier archive post.md

# Unarchive (include again)
crier unarchive post.md

# Include archived in audit
crier audit --include-archived
```

## Scheduling

Schedule posts for future publication:

```bash
# Schedule a post
crier publish post.md --to devto --schedule "tomorrow 9am"
crier publish post.md --to bluesky --schedule "2025-02-01 14:00"

# View scheduled posts
crier schedule list

# Show details
crier schedule show abc123

# Cancel a scheduled post
crier schedule cancel abc123

# Publish all due posts
crier schedule run
```

Supports natural language times ("tomorrow", "next monday 9am") and ISO format.

## Analytics

Track engagement across platforms:

```bash
# Show stats for all content
crier stats

# Stats for specific file
crier stats post.md

# Top articles by engagement
crier stats --top 10

# Filter by date
crier stats --since 1m

# Refresh from platforms (ignore cache)
crier stats --refresh

# JSON output
crier stats --json
```

Stats are cached for 1 hour. Supported platforms: dev.to, Bluesky, Mastodon.

## Threading

Split long content into threads for social platforms:

```bash
# Auto-split into thread
crier publish post.md --to bluesky --thread

# Choose thread style
crier publish post.md --to mastodon --thread --thread-style numbered  # 1/5, 2/5...
crier publish post.md --to bluesky --thread --thread-style emoji      # 🧵 1/5...
crier publish post.md --to mastodon --thread --thread-style simple    # No prefix
```

Thread splitting priority:
1. Manual markers: `<!-- thread -->` in content
2. Paragraph boundaries (double newline)
3. Sentence boundaries (if paragraph too long)

Supported platforms: Bluesky, Mastodon.

## Pre-Publish Validation

Validate content before publishing with `crier check`:

```bash
# Check a single file
crier check post.md

# Check with platform context (validates platform-specific limits)
crier check post.md --to bluesky --to devto

# Check all content
crier check --all

# Strict mode: warnings become errors
crier check post.md --strict

# Check external links (opt-in, makes HTTP requests)
crier check post.md --check-links

# JSON output
crier check post.md --json
```

**Checks performed:**
| Check | Severity | Description |
|-------|----------|-------------|
| `missing-title` | error | No title in front matter |
| `empty-body` | error | No content body |
| `missing-date` | warning | No date field |
| `missing-tags` | warning | No tags defined |
| `title-length` | warning | Title exceeds recommended length |
| `short-body` | warning | Very short content body |
| `bluesky-length` | warning | Content exceeds Bluesky character limit |
| `mastodon-length` | warning | Content exceeds Mastodon character limit |
| `missing-description` | info | No description field |
| `devto-canonical` | info | No canonical URL for dev.to |

**Publish integration:** Pre-publish checks run automatically before publishing. Use `--no-check` to skip, `--strict` to block on warnings.

**Severity overrides** in `~/.config/crier/config.yaml`:
```yaml
checks:
  missing-tags: disabled    # Don't care about tags
  missing-date: error       # Promote to error
  short-body: disabled      # Allow short posts
```

## Quiet Mode

Suppress non-essential output for scripting:

```bash
crier publish post.md --to devto --quiet
crier audit --publish --yes --quiet
crier search --tag python --quiet
```

Quiet mode only shows errors and final results. Combine with `--json` for fully parseable output.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success: all operations completed |
| `1` | Failure: operation failed or validation error |
| `2` | Partial: some operations succeeded, some failed |

```bash
# Check exit code in scripts
crier publish post.md --to devto --batch
if [ $? -eq 2 ]; then
  echo "Some platforms failed, retrying..."
fi
```

## Getting API Keys

### dev.to
1. Go to https://dev.to/settings/extensions
2. Generate API key

### Hashnode
1. Go to https://hashnode.com/settings/developer
2. Generate Personal Access Token

### Medium
1. Go to https://medium.com/me/settings/security
2. Generate Integration Token

### Bluesky
1. Go to Settings → App Passwords
2. Create an app password
3. Use format: `yourhandle.bsky.social:xxxx-xxxx-xxxx-xxxx`

### Mastodon
1. Go to Settings → Development → New Application
2. Create app with `write:statuses` scope
3. Use format: `instance.social:your-access-token`

### Twitter/X
Uses copy-paste mode - generates formatted tweet text for manual posting.
No API setup required. Just set any placeholder value:
```bash
crier config set twitter.api_key manual
```

### Ghost
1. Go to Settings → Integrations → Add custom integration
2. Copy the Admin API Key (format: `key_id:key_secret`)
3. Use format: `https://yourblog.com:key_id:key_secret`

### WordPress
**WordPress.com:**
1. Go to https://developer.wordpress.com/apps/
2. Create an app and get OAuth token
3. Use format: `yoursite.wordpress.com:access_token`

**Self-hosted WordPress:**
1. Go to Users → Profile → Application Passwords
2. Create a new application password
3. Use format: `https://yoursite.com:username:app_password`

### Buttondown
1. Go to https://buttondown.com/requests
2. Copy your API key
3. Use format: `api_key`

### Threads
1. Create a Meta Developer account at https://developers.facebook.com/
2. Create an app with Threads API access
3. Get your user_id and access_token
4. Use format: `user_id:access_token`

### Telegram
1. Message @BotFather to create a bot and get the bot token
2. Add your bot as admin to your channel
3. Get your channel's chat_id (e.g., `@yourchannel` or numeric ID)
4. Use format: `bot_token:chat_id`

### Discord
1. Go to Server Settings → Integrations → Webhooks
2. Create a new webhook for your announcement channel
3. Copy the webhook URL
4. Use the full URL as the API key

## Publishing reliability

API publishing shares preparation, execution, and registry recording across the
CLI, MCP, campaigns, audit/retry, and scheduled dispatch. Articles without a
canonical URL can be tracked using their source file and title-derived identity.

`crier reconcile --apply` backfills observed remote posts. It only marks a
publication deleted when the adapter explicitly reports a complete listing;
limited or legacy listings report unmatched entries as `unverified`. Increasing
`--limit` alone does not establish completeness.

New schedules store absolute source paths. Legacy relative paths resolve from
`site_root` (or the schedule's project directory), not the runner's working
directory. Correct old paths if their original creation directory differed.

If a remote publish succeeds but registry recording fails, results include the
remote ID/URL and `remote_published: true` where available. A recovery receipt beside the registry database retains the prepared article
and remote result without credentials. All normal publishing entry points check
for an existing receipt and repair recording instead of posting again;
unreadable receipts block publication. When retrying a recorded failure,
`audit --retry` ignores receipts older than that failure. The MCP `crier_publish` tool's
preview reports the live post as `unrecorded_publication`, and confirming records
it from the receipt (`recovered: true`) rather than publishing a duplicate. Schedules remain terminal `published` with an
error; campaign cells become `published_unrecorded` and subsequent runs skip them.

MCP publish confirmation retains the prepared article in memory for the token's
five-minute lifetime. Edits to the source after preview do not change the post
that will be sent; request a new preview to publish those edits. Campaign tokens
also retain prepared posts and reject confirmation if the manifest has changed,
so newly added targets or rewrites require a new preview.

The MCP `crier_sql` tool runs queries on a separate read-only connection.
SQLite's authorizer allows reads and ordinary query functions while rejecting
writes, database attachment, extension loading, and connection-changing commands.
Publication listings exclude failed attempts that have no remote post ID.

## Custom Platforms

Extend crier with your own platforms by dropping a `.py` file in `~/.config/crier/platforms/`:

```python
# ~/.config/crier/platforms/myblog.py
from crier.platforms.base import Article, Platform, PublishResult


class MyBlog(Platform):
    name = "myblog"
    description = "Publish to my self-hosted blog API"
    max_content_length = None  # set an int (and is_short_form = True) for short-form limits
    supports_delete = False

    base_url = "https://blog.example.com/api"

    def publish(self, article: Article) -> PublishResult:
        # retry_request adds timeouts and backoff for 429/5xx responses
        resp = self.retry_request(
            "post",
            f"{self.base_url}/posts",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "title": article.title,
                "body": article.body,
                "canonical_url": article.canonical_url,
            },
        )
        if resp.status_code not in (200, 201):
            return PublishResult(
                success=False, platform=self.name, error=f"{resp.status_code}: {resp.text}"
            )
        data = resp.json()
        return PublishResult(
            success=True, platform=self.name, article_id=str(data["id"]), url=data["url"]
        )

    def update(self, article_id: str, article: Article) -> PublishResult:
        return PublishResult(success=False, platform=self.name, error="update not supported")

    def list_articles(self, limit: int = 10) -> list[dict]:
        return []

    def get_article(self, article_id: str) -> dict | None:
        return None
```

Then configure your API key:

```bash
crier config set platforms.myblog.api_key <your-key>
crier publish article.md --to myblog
```

Pick a `name` that does not collide with a built-in platform (`crier platforms` lists them): a user plugin with the same name as a built-in replaces it. Files starting with `_` are skipped. Broken plugins emit a warning but don't crash crier.

## License

MIT
