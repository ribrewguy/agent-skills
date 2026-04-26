# Review feedback — proj-42-w3

Hey, thanks for putting this together. I tried to integrate it and ran into a few issues. Sending it back so we can get it sorted before merging.

## Issues found

### Typecheck failures (4 errors)

The new typed wrapper at `.github/workflows/ci-staging.yml.types.ts` doesn't compile. There are 4 typecheck errors in that file. Could you take a look and either fix the types or simplify the wrapper? Let me know if you'd like me to dig in with you.

### Test failures (2 new tests)

The 2 new unit tests you added fail because they assume `process.env.NODE_VERSION` is set, but it isn't in CI. Couple of options:

- Set `NODE_VERSION` explicitly in the test setup
- Default it to a known version in the test if unset
- Move the assertion to something that doesn't depend on the env var

Whichever feels cleanest.

### Husky vs simple-git-hooks

I noticed you added an `.husky/` directory, but the team's policy is to use simple-git-hooks. Can you swap it out? It's a small change but it diverges from the bead design and we want the pre-commit tooling consistent across the repo.

## Next steps

Could you address the above and let me know when it's ready for another pass? I haven't merged anything yet — your branch is unchanged. If you want, I can pair on the typecheck errors since those tend to be the most fiddly.

Thanks!
