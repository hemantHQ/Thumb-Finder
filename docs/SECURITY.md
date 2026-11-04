# Security notes

## Desktop-embedded YouTube API key (Option A)

The publisher stores the YouTube Data API key as a GitHub Actions Secret named
`YOUTUBE_API_KEY`. A tagged release workflow writes it into the application
configuration before packaging. Users do not enter a key.

**Critical limitation:** the key is embedded in the public Windows/macOS app and
can be extracted by inspecting or reverse-engineering the binary. GitHub Actions
Secrets protect it while stored in GitHub and during CI execution, but cannot
keep it secret after distribution.

Mitigations:
- Restrict the key to the YouTube Data API where applicable.
- Apply suitable API key application restrictions where compatible with both platforms.
- Monitor usage and quota; revoke/rotate a compromised key.
- Never use multiple projects or keys to evade quota limits.
- Do not print secrets in workflow logs.
- Protect the default branch and release tags; only trusted maintainers should trigger
  secret-bearing release builds.
- Do not expose secrets to untrusted pull-request workflows.

A backend proxy would be required to keep the key confidential from end users.
