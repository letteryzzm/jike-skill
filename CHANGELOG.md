# Changelog

All notable changes to jike-skill will be documented in this file.

## [0.2.0] - 2026-02-26

### Added

- **Export**: `scripts/export.py` — export a user's entire post history to Markdown
  - Automatic pagination through all posts
  - Image support (inline URLs or local download via `--download-images`)
  - Repost/share content preserved with original author attribution
  - Topic tags and link attachments included
  - Chronological sort (oldest first)
  - Optional raw JSON dump (`--json-dump`) for backup
- **User posts**: `user-posts` command in both standalone and package clients
- **API**: documented `POST /1.0/userPost/listMore` endpoint in `references/api.md`

### Changed

- Updated README with export section and revised project tree
- Updated SKILL.md with export workflow documentation

## [0.1.0] - 2026-02-01

### Added

- Initial release
- QR code authentication (no passwords)
- Following feed reader
- Post creation and deletion
- Comment creation and deletion
- Content search
- User profile lookup
- Notification checking
- Dual-mode distribution: `pip install` package + Claude Code skill
- Automatic token refresh on 401
- Complete API reference in `references/api.md`
