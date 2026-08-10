### Skill Resolution Feedback

After every delegation that returns a result, check the `skill_resolution` field:

- `paths-injected` -> all good; exact skill paths were passed and loaded
- `fallback-registry`, `fallback-path`, or `none` -> skill cache was lost; re-read the registry immediately and pass skill paths in subsequent delegations