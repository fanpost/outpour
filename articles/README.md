# Hosted articles

This folder is the content queue for the GitHub Actions hosted run of
Outpour. The workflow in `.github/workflows/outpour-schedule.yml` wakes
up every 15 minutes, publishes whatever is due, and commits the
publishing state (`.crier/`) back to the repository.

## How to queue an article

1. Add your markdown file here, with frontmatter (title, tags,
   description, canonical_url).
2. Schedule it locally from the repository root:

   ```
   outpour publish articles/my-post.md --to devto --schedule "tomorrow 9am"
   ```

   This records the post in `.crier/schedule.yaml`. Commit both the
   article and `.crier/schedule.yaml`, then push.
3. When the scheduled time arrives, the workflow publishes the post and
   commits the updated state back. Check the Actions tab for the run
   log and `.crier/schedule.yaml` for the recorded live URLs.

To publish immediately instead, run `outpour publish` without
`--schedule`, or trigger the workflow manually from the Actions tab
after queueing a post as due.

## Secrets

The workflow reads platform keys from repository secrets
(Settings, then Secrets and variables, then Actions):

- `CRIER_DEVTO_API_KEY` for Dev.to
- `CRIER_MEDIUM_API_KEY` for Medium (optional)
- `CRIER_HASHNODE_API_KEY` for Hashnode (optional)

A platform with no secret is simply reported as not configured in the
run log; nothing is posted to it. Nostr keys are not stored as secrets
here yet; publish to Nostr from your own machine for now.
