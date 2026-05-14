## Modal Version Release

Most PRs do not need Modal release configuration.

A Modal version release updates the stable Modal gateway's `current` and
`frontier` worker apps. Add a `modal_release` YAML block only when this PR
changes Modal release behavior or needs a non-default current/frontier rollout.
See `docs/engineering/skills/modal-release-prs.md` for the supported fields.

## Summary


## Testing

