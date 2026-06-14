## Summary

Describe the user-visible behavior and why the change is needed.

## Verification

- [ ] `tox -e lint,type`
- [ ] Relevant tests were added or updated
- [ ] Database mutations remain atomic and run outside Tk's UI thread
- [ ] Documentation and `CHANGELOG.md` were updated when behavior changed

## Database impact

Note schema, transaction, conflict, retry, paging, or migration implications. Write "None" when not applicable.

